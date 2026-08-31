"""Republicação e alteração de edital (arquitetura §6, detectar_republicacao).

O upsert da coleta sempre atualizou o banco em silêncio: um edital marcado
"vou participar" podia ser SUSPENSO, ter o prazo prorrogado ou o valor
alterado, e ninguém ficava sabendo até abrir a tela. Aqui a mudança vira
registro (`licitacao_alteracoes`) e aviso imediato a quem acompanha.

Quem "acompanha": dono de perfil cujo match está em análise, marcado para
participar ou favoritado. Match ainda em 'novo' não conta — avisar mudança
de algo que a pessoa nem triou é ruído.
"""
import logging

from ..config import agora as agora_local
from ..config import config
from ..db import LicitacaoAlteracao, PerfilBusca, PerfilMatch, Sessao

log = logging.getLogger("radar.alteracoes")

# Campo vigiado -> rótulo humano no aviso. Fora desta lista, mudança não é
# notícia (coletado_em e payload_json mudam a cada coleta, por exemplo).
CAMPOS_VIGIADOS = {
    "situacao": "situação",
    "data_encerramento_proposta": "encerramento das propostas",
    "data_abertura_proposta": "abertura das propostas",
    "valor_total_estimado": "valor estimado",
    "objeto": "objeto",
}

STATUS_ACOMPANHANDO = ("analisando", "vou_participar")


def detectar(lic, item):
    """Compara a licitação gravada com o item recém-coletado.

    Devolve [(campo, valor_antigo, valor_novo)]. Segue a regra do upsert:
    valor None na origem não apaga (nem 'altera') o que já temos.
    """
    mudancas = []
    for campo in CAMPOS_VIGIADOS:
        if campo not in item:
            continue
        novo, atual = item[campo], getattr(lic, campo, None)
        if novo is None or atual is None:
            # Preenchimento de lacuna não é republicação: a busca ao vivo
            # devolve campos nulos e a coleta os completa depois.
            continue
        if campo == "valor_total_estimado":
            try:
                if abs(float(novo) - float(atual)) < 0.005:
                    continue
            except (TypeError, ValueError):
                continue
            mudancas.append((campo, f"{atual}", f"{novo}"))
        else:
            if str(novo).strip() == str(atual).strip():
                continue
            mudancas.append((campo, str(atual), str(novo)))
    return mudancas


def registrar(sessao_db, lic, item):
    """Grava as alterações detectadas. Chamado pelo upsert da coleta."""
    for campo, de, para in detectar(lic, item):
        sessao_db.add(LicitacaoAlteracao(
            licitacao_id=lic.id, campo=campo,
            valor_antigo=de[:2000], valor_novo=para[:2000]))
        log.info("Licitação %s mudou %s: %.60s -> %.60s",
                 lic.numero_controle_pncp, campo, de, para)


def _fmt(campo, valor):
    if campo == "valor_total_estimado":
        try:
            return "R$ {:,.2f}".format(float(valor)).replace(
                ",", "X").replace(".", ",").replace("X", ".")
        except (TypeError, ValueError):
            return valor
    if campo.startswith("data_"):
        try:
            dia, hora = valor[:10], valor[11:16]
            a, m, d = dia.split("-")
            return f"{d}/{m}/{a}" + (f" {hora}" if hora else "")
        except (ValueError, IndexError):
            return valor
    if campo == "objeto" and len(valor) > 160:
        return valor[:160] + "..."
    return valor


def _interessados(sessao_db, licitacao_ids):
    """Usuários que acompanham cada licitação: {usuario: {lic_id, ...}}."""
    consulta = (sessao_db.query(PerfilMatch)
                .join(PerfilBusca)
                .filter(PerfilMatch.licitacao_id.in_(licitacao_ids))
                .filter((PerfilMatch.status.in_(STATUS_ACOMPANHANDO))
                        | (PerfilMatch.favorito.is_(True))))
    por_usuario = {}
    for m in consulta:
        dono = getattr(m.perfil, "usuario", None)
        if dono is None or not dono.ativo:
            continue
        por_usuario.setdefault(dono, set()).add(m.licitacao_id)
    return por_usuario


def _montar_mensagem(alteracoes_por_lic, host=None):
    host = host or config.APP_URL
    partes = ["✏️ Licerta — edital que você acompanha MUDOU\n"]
    for n, (lic, alts) in enumerate(alteracoes_por_lic, 1):
        partes.append(
            f"{n}. {lic.modalidade_nome or ''} {lic.numero_compra or ''}/"
            f"{lic.ano_compra or ''} — {lic.orgao_nome or ''} "
            f"({lic.municipio_nome or ''}/{lic.uf or ''})")
        for a in alts:
            rotulo = CAMPOS_VIGIADOS.get(a.campo, a.campo)
            partes.append(f"   • {rotulo}: {_fmt(a.campo, a.valor_antigo)} → "
                          f"{_fmt(a.campo, a.valor_novo)}")
        if lic.link_pncp:
            partes.append(f"   🔗 {lic.link_pncp}")
        partes.append("")
    partes.append(f"Ver no radar: {host}/licitacoes")
    return "\n".join(partes)


def avisar_alteracoes(sessao_db=None, host=None):
    """Despacha as alterações pendentes a quem acompanha. Devolve nº de avisos.

    Toda alteração processada sai marcada como avisada — inclusive as de
    editais que ninguém acompanha (senão a varredura recomeça do zero a cada
    ciclo, para sempre). Falha de canal deixa as daquele usuário pendentes
    para o próximo ciclo.
    """
    from ..notificacoes import alerta, push
    sessao = sessao_db or Sessao()
    try:
        pendentes = (sessao.query(LicitacaoAlteracao)
                     .filter_by(avisada=False)
                     .order_by(LicitacaoAlteracao.licitacao_id).all())
        if not pendentes:
            return 0
        por_lic = {}
        for a in pendentes:
            por_lic.setdefault(a.licitacao_id, []).append(a)
        interessados = _interessados(sessao, list(por_lic))
        avisos = 0
        entregues = set()
        for usuario, lic_ids in interessados.items():
            grupo = [(por_lic[i][0].licitacao, por_lic[i])
                     for i in sorted(lic_ids) if i in por_lic]
            if not grupo:
                continue
            texto = _montar_mensagem(grupo, host)
            ok = False
            if usuario.receber_telegram and usuario.telegram_chat_id:
                ok |= alerta.enviar_telegram(texto,
                                             chat_id=usuario.telegram_chat_id)
            if usuario.receber_email and usuario.email_alertas:
                ok |= alerta.enviar_email(texto, destino=usuario.email_alertas)
            if usuario.receber_push:
                try:
                    ok |= push.enviar_push(
                        sessao, usuario, "✏️ Edital que você acompanha mudou",
                        f"{len(grupo)} edital(is) com alteração — toque para ver",
                        url=(host or config.APP_URL) + "/licitacoes") > 0
                except Exception:  # noqa: BLE001 — push nunca derruba o aviso
                    log.exception("Push de alteração falhou")
            if ok:
                avisos += 1
                entregues.update(lic_ids)
            else:
                log.warning("Aviso de alteração ao usuário %s falhou em todos "
                            "os canais; fica para o próximo ciclo",
                            usuario.email)
        agora_ = agora_local()
        sem_interessado = set(por_lic) - set().union(
            *interessados.values()) if interessados else set(por_lic)
        for lic_id, alts in por_lic.items():
            if lic_id in entregues or lic_id in sem_interessado:
                for a in alts:
                    a.avisada = True
                    a.detectada_em = a.detectada_em or agora_
        sessao.commit()
        return avisos
    except Exception:  # noqa: BLE001 — aviso nunca derruba a coleta
        sessao.rollback()
        log.exception("Erro no despacho de alterações")
        return 0
    finally:
        if sessao_db is None:
            sessao.close()
