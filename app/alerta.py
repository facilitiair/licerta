"""Alertas via Telegram + e-mail opcional (SPEC §6).

Cada perfil é também um alerta: tem sua própria frequência (diária, semanal,
mensal ou anual), sua própria hora e seu próprio recorte de situação/prazo.
O despacho é feito por `enviar_alertas_devidos`, chamado de tempos em tempos
pelo agendador — é ele que decide de quem chegou a vez.
"""
import html
import logging
import smtplib
from datetime import date, datetime
from email.mime.text import MIMEText

import requests

from .config import config
from .db import PerfilBusca, PerfilMatch, Sessao
from .matcher import esta_vigente, ordenar_licitacoes

log = logging.getLogger("radar.alerta")

LIMITE_POR_PERFIL = 10
LIMITE_OBJETO = 180
LIMITE_TELEGRAM = 4096

FREQUENCIAS = {"diario": "Todo dia", "semanal": "Uma vez por semana",
               "mensal": "Uma vez por mês", "anual": "Uma vez por ano"}
DIAS_SEMANA = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
               "sexta-feira", "sábado", "domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]
# Depois de quantos dias sem enviar o alerta sai assim que puder, mesmo fora
# do dia marcado — evita perder o ciclo se o app estiver fora do ar no dia.
JANELA_ATRASO = {"diario": 1, "semanal": 7, "mensal": 31, "anual": 366}


def _fmt_valor(v):
    if v is None:
        return "não informado"
    return "R$ {:,.2f}".format(v).replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_data(d):
    if not d:
        return "—"
    try:
        dia, hora = d[:10], d[11:16]
        a, m, dd = dia.split("-")
        return f"{dd}/{m}/{a}" + (f" {hora}" if hora else "")
    except (ValueError, IndexError):
        return d


def _link_download_edital(sessao_db, lic):
    """Melhor link direto para baixar o edital: primeiro o que já baixamos,
    senão consulta a API de documentos na hora (melhor esforço)."""
    import re

    from .db import ArquivoEdital
    from .pncp import listar_arquivos_compra

    arq = (sessao_db.query(ArquivoEdital)
           .filter_by(licitacao_id=lic.id, tipo="Edital").first())
    if arq and arq.url_origem:
        return re.sub(r"^(https://pncp\.gov\.br):\d+", r"\1", arq.url_origem)
    if lic.fonte != "pncp" or not (lic.orgao_cnpj and lic.ano_compra):
        return None
    try:
        seq = int(lic.numero_controle_pncp.split("-")[2].split("/")[0])
        docs = listar_arquivos_compra(lic.orgao_cnpj, lic.ano_compra, seq)
        edital = next((d for d in docs
                       if (d.get("tipoDocumentoNome") or "") == "Edital"),
                      docs[0] if docs else None)
        if edital and (edital.get("url") or edital.get("uri")):
            return re.sub(r"^(https://pncp\.gov\.br):\d+", r"\1",
                          edital.get("url") or edital.get("uri"))
    except Exception:  # noqa: BLE001 — link é cortesia, nunca trava o alerta
        pass
    return None


def _bloco_licitacao(n, lic, termos="", link_download=None):
    objeto = (lic.objeto or "").strip()   # objeto completo, sem truncar
    linhas = [
        f"{n}. {lic.modalidade_nome or ''} {lic.numero_compra or ''}/"
        f"{lic.ano_compra or ''} — {lic.orgao_nome or ''} "
        f"({lic.municipio_nome or ''}/{lic.uf or ''})",
        f"   Objeto: {objeto}",
        f"   Valor estimado: {_fmt_valor(lic.valor_total_estimado)} · "
        f"SRP: {'sim' if lic.srp else 'não'}",
        f"   Abertura: {_fmt_data(lic.data_abertura_proposta)} · "
        f"Encerra: {_fmt_data(lic.data_encerramento_proposta)}",
    ]
    if termos:
        linhas.append(f"   🎯 Casou por: {termos}")
    if link_download:
        linhas.append(f"   ⬇️ Baixar edital: {link_download}")
    if lic.link_pncp:
        linhas.append(f"   🔗 Página no PNCP: {lic.link_pncp}")
    elif lic.link_sistema_origem:
        linhas.append(f"   🔗 {lic.link_sistema_origem}")
    return "\n".join(linhas)


def resumo_frequencia(perfil):
    """Frase curta descrevendo quando este alerta sai (usada na interface)."""
    freq = getattr(perfil, "frequencia", None) or "diario"
    hora = "%02d:%02d" % _hora_do_perfil(perfil)
    if freq == "semanal":
        return f"Toda {DIAS_SEMANA[(perfil.dia_semana or 0) % 7]}, às {hora}"
    if freq == "mensal":
        return f"Todo dia {perfil.dia_mes or 1} do mês, às {hora}"
    if freq == "anual":
        return (f"Todo dia {perfil.dia_mes or 1} de "
                f"{MESES[((perfil.mes_ano or 1) - 1) % 12]}, às {hora}")
    return f"Todo dia, às {hora}"


def _hora_do_perfil(perfil):
    """Hora própria do alerta; em branco, usa a HORA_ALERTA geral do .env."""
    texto = (getattr(perfil, "hora_envio", "") or "").strip()
    try:
        h, m = texto.split(":")
        return max(0, min(23, int(h))), max(0, min(59, int(m)))
    except ValueError:
        return config.HORA_ALERTA


def alerta_devido(perfil, agora=None, respeitar_hora=True):
    """Chegou a vez deste alerta? Respeita frequência, hora e último envio."""
    agora = agora or datetime.now()
    if not (perfil.ativo and perfil.notificar):
        return False
    if respeitar_hora and (agora.hour, agora.minute) < _hora_do_perfil(perfil):
        return False
    ultimo = getattr(perfil, "ultimo_envio", None)
    if ultimo and ultimo.date() == agora.date():
        return False                       # este alerta já saiu hoje
    freq = getattr(perfil, "frequencia", None) or "diario"
    if not ultimo or (agora.date() - ultimo.date()).days >= \
            JANELA_ATRASO.get(freq, 1):
        return True                        # nunca saiu, ou o ciclo já venceu
    if freq == "semanal":
        return agora.weekday() == (perfil.dia_semana or 0)
    if freq == "mensal":
        return agora.day == (perfil.dia_mes or 1)
    if freq == "anual":
        return (agora.month == (perfil.mes_ano or 1)
                and agora.day == (perfil.dia_mes or 1))
    return False


def separar_pendentes(perfil, pendentes, agora=None):
    """Divide os matches ainda não avisados em (enviáveis, vencidos, fora do
    recorte de situação).

    É a trava contra o problema que motivou este recorte: edital com o prazo
    de proposta já encerrado, ou cancelado/anulado, nunca vira alerta.
    """
    enviaveis, vencidos, fora_situacao = [], [], []
    situacoes = getattr(perfil, "situacoes", None) or []
    for m in pendentes:
        lic = m.licitacao
        if getattr(perfil, "somente_vigentes", True) and \
                not esta_vigente(lic, agora):
            vencidos.append(m)
        elif situacoes and (lic.situacao or "") not in situacoes:
            fora_situacao.append(m)
        else:
            enviaveis.append(m)
    return enviaveis, vencidos, fora_situacao


def montar_mensagem_perfil(sessao_db, perfil, matches, host=None):
    """Texto do alerta de UM perfil, já com os matches selecionados."""
    host = host or config.APP_URL
    hoje = date.today().strftime("%d/%m/%Y")
    por_lic = {m.licitacao_id: m for m in matches}
    lics = ordenar_licitacoes([m.licitacao for m in matches], perfil.ordenacao)
    partes = [f"📡 {perfil.nome} — {hoje}",
              f"{len(matches)} oportunidade"
              f"{'s' if len(matches) != 1 else ''} com proposta em aberto\n"]
    for i, lic in enumerate(lics[:LIMITE_POR_PERFIL], 1):
        m = por_lic.get(lic.id)
        partes.append(_bloco_licitacao(
            i, lic, termos=m.termos if m else "",
            link_download=_link_download_edital(sessao_db, lic)) + "\n")
    if len(lics) > LIMITE_POR_PERFIL:
        partes.append(f"   ... e mais {len(lics) - LIMITE_POR_PERFIL} — "
                      "veja no painel.\n")
    partes.append(f"Ver todas: {host}/")
    return "\n".join(partes)


def enviar_telegram(texto):
    """Envia pelo Bot API; mensagens longas são divididas em blocos de 4096."""
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        log.warning("Telegram não configurado (.env) — alerta não enviado")
        return False
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    while texto:
        pedaco, texto = texto[:LIMITE_TELEGRAM], texto[LIMITE_TELEGRAM:]
        r = requests.post(url, json={
            "chat_id": config.TELEGRAM_CHAT_ID,
            "text": pedaco,
            "disable_web_page_preview": True,
        }, timeout=30)
        if not r.ok:
            log.error("Telegram recusou o envio: %s", r.text[:300])
            return False
    return True


def _texto_para_html(texto):
    """Mesma estrutura do Telegram, em HTML simples para o e-mail."""
    corpo = html.escape(texto).replace("\n", "<br>\n")
    return (f'<html><body style="font-family:Segoe UI,Arial,sans-serif;'
            f'max-width:720px;font-size:14px;line-height:1.5">{corpo}'
            f"</body></html>")


def enviar_email(texto):
    """Envia o alerta por SMTP. Só age se EMAIL_ATIVO=true (SPEC §6)."""
    if not config.EMAIL_ATIVO:
        return False
    if not (config.SMTP_HOST and config.SMTP_USER and config.EMAIL_DESTINO):
        log.warning("EMAIL_ATIVO=true mas SMTP incompleto no .env")
        return False
    try:
        msg = MIMEText(_texto_para_html(texto), "html", "utf-8")
        msg["Subject"] = f"Radar de Licitações — {date.today().strftime('%d/%m/%Y')}"
        msg["From"] = config.SMTP_USER
        msg["To"] = config.EMAIL_DESTINO
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
            smtp.send_message(msg)
        return True
    except Exception:  # noqa: BLE001
        log.exception("Falha ao enviar alerta por e-mail")
        return False


def enviar_alerta_perfil(sessao_db, perfil, host=None, agora=None):
    """Envia o alerta de um perfil. Devolve (enviou?, quantidade enviada).

    Um ciclo sem nada novo não vira mensagem — silêncio é melhor que ruído.
    Os vencidos são marcados como avisados: o prazo não volta atrás, então
    não faz sentido reavaliá-los em todo ciclo.
    """
    agora = agora or datetime.now()
    pendentes = (sessao_db.query(PerfilMatch)
                 .filter_by(perfil_id=perfil.id, notificado=False).all())
    enviaveis, vencidos, fora = separar_pendentes(perfil, pendentes, agora)
    for m in vencidos:
        m.notificado = True
    if not enviaveis:
        perfil.ultimo_envio = agora        # ciclo cumprido, mesmo sem novidade
        sessao_db.commit()
        log.info("Alerta '%s': nada a enviar (%s vencidas, %s fora da situação)",
                 perfil.nome, len(vencidos), len(fora))
        return False, 0
    texto = montar_mensagem_perfil(sessao_db, perfil, enviaveis, host)
    ok_telegram = enviar_telegram(texto)
    ok_email = enviar_email(texto)
    if not (ok_telegram or ok_email):
        sessao_db.commit()                 # ao menos grava os vencidos
        return False, 0
    for m in enviaveis:
        m.notificado = True
    perfil.ultimo_envio = agora
    sessao_db.commit()
    log.info("Alerta '%s' enviado (telegram=%s, email=%s): %s novas, "
             "%s vencidas descartadas", perfil.nome, ok_telegram, ok_email,
             len(enviaveis), len(vencidos))
    return True, len(enviaveis)


def enviar_alertas_devidos(host=None, agora=None, respeitar_hora=True,
                           perfil_id=None):
    """Percorre os perfis e envia os alertas cuja vez chegou.

    `perfil_id` força o envio de um alerta só (botão 'Enviar agora').
    `respeitar_hora=False` para quem roda uma vez por dia em horário fixo
    (GitHub Actions), onde a hora exata do perfil não faz sentido.
    """
    agora = agora or datetime.now()
    sessao_db = Sessao()
    enviados = 0
    try:
        if perfil_id:
            perfis = [p for p in [sessao_db.get(PerfilBusca, perfil_id)] if p]
        else:
            perfis = (sessao_db.query(PerfilBusca)
                      .filter_by(ativo=True, notificar=True).all())
        for perfil in perfis:
            if not perfil_id and not alerta_devido(perfil, agora, respeitar_hora):
                continue
            try:
                enviou, _ = enviar_alerta_perfil(sessao_db, perfil, host, agora)
                enviados += 1 if enviou else 0
            except Exception:  # noqa: BLE001 — um alerta ruim não trava os outros
                sessao_db.rollback()
                log.exception("Erro ao enviar o alerta '%s'", perfil.nome)
    except Exception:  # noqa: BLE001 — o agendador nunca pode cair
        log.exception("Erro no despacho de alertas")
    finally:
        sessao_db.close()
    return enviados


def enviar_alerta_diario(host=None, respeitar_hora=True):
    """Compatibilidade: o job diário agora é o despacho por perfil."""
    return enviar_alertas_devidos(host=host, respeitar_hora=respeitar_hora)
