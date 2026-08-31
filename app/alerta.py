"""Alertas via Telegram + e-mail opcional (SPEC §6).

Cada perfil é também um alerta: tem sua própria frequência (diária, semanal,
mensal ou anual), sua própria hora e seu próprio recorte de situação/prazo.
O despacho é feito por `enviar_alertas_devidos`, chamado de tempos em tempos
pelo agendador — é ele que decide de quem chegou a vez.
"""
import html
import logging
import smtplib
from datetime import timedelta
from email.mime.text import MIMEText

import requests

from .config import agora as agora_local
from .config import config
from .db import PerfilBusca, PerfilMatch, Sessao
from .matcher import esta_vigente, ordenar_licitacoes

log = logging.getLogger("radar.alerta")

LIMITE_POR_PERFIL = 10
LIMITE_OBJETO = 180
LIMITE_TELEGRAM = 4096

FREQUENCIAS = {"horas": "Várias vezes por dia", "diario": "Todo dia",
               "semanal": "Uma vez por semana", "mensal": "Uma vez por mês",
               "anual": "Uma vez por ano"}
DIAS_SEMANA = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
               "sexta-feira", "sábado", "domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]


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
    if freq == "horas":
        return f"A cada {_intervalo_horas(perfil)}h, a partir das {hora}"
    if freq == "semanal":
        return f"Toda {DIAS_SEMANA[(perfil.dia_semana or 0) % 7]}, às {hora}"
    if freq == "mensal":
        return f"Todo dia {perfil.dia_mes or 1} do mês, às {hora}"
    if freq == "anual":
        return (f"Todo dia {perfil.dia_mes or 1} de "
                f"{MESES[((perfil.mes_ano or 1) - 1) % 12]}, às {hora}")
    return f"Todo dia, às {hora}"


def _intervalo_horas(perfil):
    """De quantas em quantas horas repete, na frequência 'várias vezes/dia'."""
    try:
        return max(1, min(12, int(getattr(perfil, "intervalo_horas", 3) or 3)))
    except (TypeError, ValueError):
        return 3


def _hora_do_perfil(perfil):
    """Hora própria do alerta; em branco, usa a HORA_ALERTA geral do .env.

    Na frequência 'várias vezes por dia' é a hora do PRIMEIRO envio: nada
    de aviso às 3 da manhã.
    """
    texto = (getattr(perfil, "hora_envio", "") or "").strip()
    try:
        h, m = texto.split(":")
        return max(0, min(23, int(h))), max(0, min(59, int(m)))
    except ValueError:
        return config.HORA_ALERTA


def horario_previsto(perfil, agora, hora=None):
    """O instante marcado para este alerta que já passou, o mais recente.

    É a peça central do agendamento, e o motivo de não olharmos mais só para
    a hora do relógio. O agendador confere de 10 em 10 minutos numa grade cuja
    fase depende da hora em que o app subiu: com `hora_envio` às 23:55, podia
    não existir NENHUM tique entre 23:55 e a meia-noite, e a comparação
    "agora < hora marcada" barrava o alerta todos os dias, para sempre.

    Comparando `ultimo_envio` com este instante, o alerta atrasado sai assim
    que puder — inclusive depois da meia-noite — e nunca sai duas vezes pelo
    mesmo horário. Dispensa a antiga janela de atraso: o atraso é natural aqui.
    """
    h, m = hora or _hora_do_perfil(perfil)
    freq = getattr(perfil, "frequencia", None) or "diario"
    alvo = agora.replace(hour=h, minute=m, second=0, microsecond=0)
    if freq == "semanal":
        alvo -= timedelta(days=(agora.weekday() - (perfil.dia_semana or 0)) % 7)
        return alvo if alvo <= agora else alvo - timedelta(days=7)
    if freq == "mensal":
        alvo = alvo.replace(day=_dia_do_mes(perfil))
        if alvo > agora:                    # ainda não chegou: vale o mês passado
            mes_passado = agora.replace(day=1) - timedelta(days=1)
            alvo = alvo.replace(year=mes_passado.year, month=mes_passado.month)
        return alvo
    if freq == "anual":
        alvo = alvo.replace(month=(perfil.mes_ano or 1), day=_dia_do_mes(perfil))
        return alvo if alvo <= agora else alvo.replace(year=alvo.year - 1)
    return alvo if alvo <= agora else alvo - timedelta(days=1)   # diário


def _dia_do_mes(perfil):
    """1..28 — acima disso o alerta sumiria em fevereiro."""
    try:
        return max(1, min(28, int(perfil.dia_mes or 1)))
    except (TypeError, ValueError):
        return 1


def _ultimo_envio_confiavel(perfil, agora):
    """`ultimo_envio` no futuro é relógio bagunçado, não envio de verdade.

    Acontece de verdade: banco restaurado de outra máquina, correção de NTP
    para trás, ou um deploy em que o fuso não resolveu e a hora foi gravada
    3h à frente. Aceitá-lo calava o alerta diário por dias a fio.
    """
    ultimo = getattr(perfil, "ultimo_envio", None)
    if ultimo and ultimo > agora:
        log.warning("Alerta '%s' com último envio no futuro (%s); ignorando",
                    perfil.nome, ultimo)
        ultimo = None
    # Alerta que nunca saiu conta a partir da criação do perfil. Sem esse
    # piso, um perfil criado às 8h com envio marcado para as 10h disparava
    # na hora, ignorando o horário que o usuário acabou de escolher.
    return ultimo or getattr(perfil, "criado_em", None)


def alerta_devido(perfil, agora=None, respeitar_hora=True):
    """Chegou a vez deste alerta? Respeita frequência, hora e último envio."""
    agora = agora or agora_local()
    if not (perfil.ativo and perfil.notificar):
        return False
    ultimo = _ultimo_envio_confiavel(perfil, agora)
    if getattr(perfil, "frequencia", None) == "horas":
        # A única frequência que repete no mesmo dia: conta pelo relógio.
        # A hora do perfil é o primeiro envio do dia — sem isso, tocaria de
        # madrugada.
        if respeitar_hora and (agora.hour, agora.minute) < _hora_do_perfil(perfil):
            return False
        return (not ultimo or (agora - ultimo).total_seconds()
                >= _intervalo_horas(perfil) * 3600)
    if not respeitar_hora:
        # Quem roda uma vez por dia em horário fixo (GitHub Actions) não tem
        # como respeitar a hora do perfil; conta a frequência a partir da
        # meia-noite do dia marcado.
        return not ultimo or ultimo < horario_previsto(perfil, agora, hora=(0, 0))
    return not ultimo or ultimo < horario_previsto(perfil, agora)


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


def montar_mensagem_perfil(sessao_db, perfil, matches, host=None, urgente=False):
    """Texto do alerta de UM perfil. Devolve (texto, matches_incluídos).

    Devolver quem entrou de fato é essencial: só esses podem ser marcados
    como avisados. Antes a mensagem mostrava 10 e o código marcava TODOS —
    num perfil novo com 60 achados, 50 oportunidades com semanas de prazo
    eram queimadas de vez, sem nunca aparecer em alerta nenhum.
    """
    host = host or config.APP_URL
    hoje = agora_local().strftime("%d/%m/%Y")
    por_lic = {m.licitacao_id: m for m in matches}
    lics = ordenar_licitacoes([m.licitacao for m in matches], perfil.ordenacao)
    incluidas = lics[:LIMITE_POR_PERFIL]
    cabecalho = ("⏰ FECHA HOJE — " if urgente else "📡 ") + f"{perfil.nome} — {hoje}"
    partes = [cabecalho,
              f"{len(incluidas)} oportunidade"
              f"{'s' if len(incluidas) != 1 else ''} com proposta em aberto\n"]
    for i, lic in enumerate(incluidas, 1):
        m = por_lic.get(lic.id)
        partes.append(_bloco_licitacao(
            i, lic, termos=m.termos if m else "",
            link_download=_link_download_edital(sessao_db, lic)) + "\n")
    if len(lics) > LIMITE_POR_PERFIL:
        partes.append(f"   ... e mais {len(lics) - LIMITE_POR_PERFIL} no radar — "
                      "chegam no próximo alerta.\n")
    partes.append(f"Ver todas: {host}/")
    enviados = [por_lic[l.id] for l in incluidas if l.id in por_lic]
    return "\n".join(partes), enviados


def enviar_telegram(texto):
    """Envia pelo Bot API; mensagens longas são divididas em blocos de 4096."""
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        log.warning("Telegram não configurado (.env) — alerta não enviado")
        return False
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    for pedaco in dividir_mensagem(texto):
        r = requests.post(url, json={
            "chat_id": config.TELEGRAM_CHAT_ID,
            "text": pedaco,
            "disable_web_page_preview": True,
        }, timeout=30)
        if not r.ok:
            log.error("Telegram recusou o envio: %s", r.text[:300])
            return False
    return True


def _unidades_telegram(texto):
    """Tamanho como o Telegram conta: unidades UTF-16, onde emoji vale 2.

    Medir com len() do Python subestima — um pedaço de 4096 caracteres com os
    emojis do alerta dá 4107 para o Telegram e volta recusado.
    """
    return len(texto.encode("utf-16-le")) // 2


def dividir_mensagem(texto, limite=LIMITE_TELEGRAM):
    """Quebra a mensagem em pedaços aceitos pelo Telegram, sem cortar linha.

    Cortar no caractere exato deixava o link de download do edital partido
    entre duas mensagens, inutilizável — justamente o que o alerta existe
    para entregar. Aqui a quebra só acontece entre linhas; uma linha longa
    demais para caber sozinha (raro) é dividida na força, como último recurso.
    """
    pedacos, atual = [], ""
    for linha in texto.split("\n"):
        while _unidades_telegram(linha) > limite:
            corte = limite
            while corte > 1 and _unidades_telegram(linha[:corte]) > limite:
                corte -= 32
            if atual:
                pedacos.append(atual)
                atual = ""
            pedacos.append(linha[:corte])
            linha = linha[corte:]
        candidato = f"{atual}\n{linha}" if atual else linha
        if _unidades_telegram(candidato) > limite:
            pedacos.append(atual)
            atual = linha
        else:
            atual = candidato
    if atual:
        pedacos.append(atual)
    return pedacos or [""]


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
        msg["Subject"] = f"Radar de Licitações — {agora_local().strftime('%d/%m/%Y')}"
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


def proximo_horario_previsto(perfil, agora):
    """Quando este alerta sai da próxima vez, se nada o antecipar."""
    freq = getattr(perfil, "frequencia", None) or "diario"
    if freq == "horas":
        return agora + timedelta(hours=_intervalo_horas(perfil))
    anterior = horario_previsto(perfil, agora)
    if freq == "semanal":
        return anterior + timedelta(days=7)
    if freq == "mensal":
        proximo = (anterior.replace(day=28) + timedelta(days=7))
        return proximo.replace(day=_dia_do_mes(perfil))
    if freq == "anual":
        return anterior.replace(year=anterior.year + 1)
    return anterior + timedelta(days=1)


def tem_urgencia(perfil, enviaveis, agora):
    """Alguma destas oportunidades fecha antes do próximo alerta programado?

    Sem esta saída, um edital de prazo curto morria em silêncio: a coleta das
    9h achava uma dispensa que encerrava às 17h do mesmo dia, o alerta diário
    já tinha saído às 7h, e no dia seguinte ela era descartada como vencida e
    marcada como avisada — sem nunca ter sido enviada. A coleta de 3 em 3
    horas não adianta nada se o aviso só sai amanhã.
    """
    limite = proximo_horario_previsto(perfil, agora).strftime("%Y-%m-%dT%H:%M")
    for m in enviaveis:
        fim = (m.licitacao.data_encerramento_proposta or "").replace(" ", "T")
        if fim and (fim[:16] if len(fim) > 10 else fim + "T23:59") < limite:
            return True
    return False


def enviar_alerta_perfil(sessao_db, perfil, host=None, agora=None,
                         urgente=False):
    """Envia o alerta de um perfil. Devolve (enviou?, quantidade enviada).

    Um ciclo sem nada novo não vira mensagem — silêncio é melhor que ruído.
    Os vencidos são marcados como avisados: o prazo não volta atrás, então
    não faz sentido reavaliá-los em todo ciclo.
    """
    agora = agora or agora_local()
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
    texto, incluidos = montar_mensagem_perfil(sessao_db, perfil, enviaveis,
                                              host, urgente=urgente)
    ok_telegram = enviar_telegram(texto)
    ok_email = enviar_email(texto)
    if not (ok_telegram or ok_email):
        sessao_db.commit()                 # ao menos grava os vencidos
        return False, 0
    # Só quem entrou na mensagem é marcado. O excedente continua pendente e
    # entra no alerta seguinte, em vez de ser queimado sem ter sido mostrado.
    for m in incluidos:
        m.notificado = True
    if not urgente:
        perfil.ultimo_envio = agora
    sessao_db.commit()
    log.info("Alerta '%s'%s enviado (telegram=%s, email=%s): %s de %s novas, "
             "%s vencidas descartadas", perfil.nome, " URGENTE" if urgente else "",
             ok_telegram, ok_email, len(incluidos), len(enviaveis), len(vencidos))
    return True, len(incluidos)


def enviar_alertas_devidos(host=None, agora=None, respeitar_hora=True,
                           perfil_id=None):
    """Percorre os perfis e envia os alertas cuja vez chegou.

    `perfil_id` força o envio de um alerta só (botão 'Enviar agora').
    `respeitar_hora=False` para quem roda uma vez por dia em horário fixo
    (GitHub Actions), onde a hora exata do perfil não faz sentido.
    """
    agora = agora or agora_local()
    sessao_db = Sessao()
    enviados = 0
    try:
        if perfil_id:
            perfis = [p for p in [sessao_db.get(PerfilBusca, perfil_id)] if p]
        else:
            perfis = (sessao_db.query(PerfilBusca)
                      .filter_by(ativo=True, notificar=True).all())
        for perfil in perfis:
            urgente = False
            if not perfil_id and not alerta_devido(perfil, agora, respeitar_hora):
                # Fora da agenda, mas pode haver prazo fechando antes do
                # próximo alerta — nesse caso o aviso sai agora.
                pendentes = (sessao_db.query(PerfilMatch)
                             .filter_by(perfil_id=perfil.id, notificado=False)
                             .all())
                enviaveis, _, _ = separar_pendentes(perfil, pendentes, agora)
                if not (enviaveis and tem_urgencia(perfil, enviaveis, agora)):
                    continue
                urgente = True
            try:
                enviou, _ = enviar_alerta_perfil(sessao_db, perfil, host, agora,
                                                 urgente=urgente)
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
