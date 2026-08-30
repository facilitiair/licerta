"""Alerta diário via Telegram + e-mail opcional (SPEC §6)."""
import html
import logging
import smtplib
from datetime import date
from email.mime.text import MIMEText

import requests

from .config import config
from .db import PerfilBusca, PerfilMatch, Sessao
from .matcher import ordenar_licitacoes

log = logging.getLogger("radar.alerta")

LIMITE_POR_PERFIL = 10
LIMITE_OBJETO = 180
LIMITE_TELEGRAM = 4096


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


def montar_mensagem(sessao_db, host="http://localhost:8000"):
    """Monta o texto do alerta e devolve (texto, matches_incluidos)."""
    hoje = date.today().strftime("%d/%m/%Y")
    partes = [f"📡 Radar de Licitações — {hoje}\n"]
    todos_matches = []
    perfis = (sessao_db.query(PerfilBusca)
              .filter_by(ativo=True, notificar=True).all())
    for perfil in perfis:
        pendentes = (sessao_db.query(PerfilMatch)
                     .filter_by(perfil_id=perfil.id, notificado=False).all())
        if not pendentes:
            continue
        por_lic = {m.licitacao_id: m for m in pendentes}
        lics = ordenar_licitacoes([m.licitacao for m in pendentes],
                                  perfil.ordenacao)
        partes.append(f"🔹 PERFIL: {perfil.nome} ({len(pendentes)} nova"
                      f"{'s' if len(pendentes) != 1 else ''})\n")
        for i, lic in enumerate(lics[:LIMITE_POR_PERFIL], 1):
            m = por_lic.get(lic.id)
            partes.append(_bloco_licitacao(
                i, lic,
                termos=m.termos if m else "",
                link_download=_link_download_edital(sessao_db, lic)) + "\n")
        if len(lics) > LIMITE_POR_PERFIL:
            partes.append(f"   ... e mais {len(lics) - LIMITE_POR_PERFIL} — "
                          "veja no painel.\n")
        todos_matches.extend(pendentes)
    if not todos_matches:
        return (f"📡 Radar de Licitações — {hoje}\n"
                "Nenhuma novidade hoje. Sistema funcionando normalmente. ✅",
                [])
    partes.append(f"Ver todas: {host}/")
    return "\n".join(partes), todos_matches


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


def enviar_alerta_diario(host="http://localhost:8000"):
    """Job das HORA_ALERTA: envia o resumo e marca os matches como notificados."""
    sessao_db = Sessao()
    try:
        texto, matches = montar_mensagem(sessao_db, host)
        ok_telegram = enviar_telegram(texto)
        ok_email = enviar_email(texto)
        if ok_telegram or ok_email:
            for m in matches:
                m.notificado = True
            sessao_db.commit()
            log.info("Alerta enviado (telegram=%s, email=%s): %s matches",
                     ok_telegram, ok_email, len(matches))
    except Exception:  # noqa: BLE001 — o agendador nunca pode cair
        log.exception("Erro ao enviar alerta diário")
    finally:
        sessao_db.close()
