"""Alerta diário via Telegram (SPEC §6): um resumo por dia, agrupado por perfil."""
import logging
from datetime import date

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


def _bloco_licitacao(n, lic):
    objeto = (lic.objeto or "").strip()
    if len(objeto) > LIMITE_OBJETO:
        objeto = objeto[:LIMITE_OBJETO].rstrip() + "..."
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
    if lic.link_pncp:
        linhas.append(f"   🔗 {lic.link_pncp}")
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
        lics = ordenar_licitacoes([m.licitacao for m in pendentes],
                                  perfil.ordenacao)
        partes.append(f"🔹 PERFIL: {perfil.nome} ({len(pendentes)} nova"
                      f"{'s' if len(pendentes) != 1 else ''})\n")
        for i, lic in enumerate(lics[:LIMITE_POR_PERFIL], 1):
            partes.append(_bloco_licitacao(i, lic) + "\n")
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


def enviar_alerta_diario(host="http://localhost:8000"):
    """Job das HORA_ALERTA: envia o resumo e marca os matches como notificados."""
    sessao_db = Sessao()
    try:
        texto, matches = montar_mensagem(sessao_db, host)
        if enviar_telegram(texto):
            for m in matches:
                m.notificado = True
            sessao_db.commit()
            log.info("Alerta enviado: %s matches notificados", len(matches))
    except Exception:  # noqa: BLE001 — o agendador nunca pode cair
        log.exception("Erro ao enviar alerta diário")
    finally:
        sessao_db.close()
