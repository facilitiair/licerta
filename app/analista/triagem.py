"""Triagem sugerida por IA (camada 1 — modelo barato, alto volume).

Pedido do primeiro usuário real: "a própria IA deveria relacionar nossa
documentação com os editais e sugerir participar". Aqui a IA barata lê o
objeto de cada match novo contra o retrato da empresa (tirado do dossiê e
dos perfis) e grava uma SUGESTÃO no cartão do funil — participar,
analisar ou descartar. Mover o cartão continua sendo gesto humano.

Custo sob controle: só matches novos recentes, em lotes, no modelo de
triagem (centavos por centena).
"""
import json
import logging
from datetime import timedelta

from ia import camadas, cliente

from ..config import agora as agora_local
from ..db import (DocumentoEmpresa, Licitacao, PerfilBusca, PerfilMatch)

log = logging.getLogger("radar.triagem")

LOTE = 30
TETO = 150
HORAS_RECENTES = 96
SUGESTOES_VALIDAS = {"participar", "analisar", "descartar"}


def _retrato_da_empresa(sessao_db, usuario_id):
    """O que a empresa é, deduzido do que ela tem: dossiê + perfis."""
    docs = (sessao_db.query(DocumentoEmpresa)
            .filter_by(arquivado=False).all())
    atestados = [d.nome for d in docs
                 if d.tipo in ("Atestado de Capacidade", "CAT")]
    perfis = (sessao_db.query(PerfilBusca)
              .filter_by(usuario_id=usuario_id, ativo=True).all())
    palavras = sorted({p for perfil in perfis
                       for p in (perfil.palavras_incluir or [])})
    return {
        "atestados_e_cats": atestados or ["(dossiê ainda sem atestados)"],
        "tipos_de_documento_no_dossie": sorted({d.tipo for d in docs}),
        "palavras_dos_perfis_de_busca": palavras,
    }


def _pendentes(sessao_db, usuario_id, agora_):
    corte = (agora_ - timedelta(hours=HORAS_RECENTES))
    hoje = agora_.strftime("%Y-%m-%d")
    return (sessao_db.query(PerfilMatch).join(Licitacao).join(PerfilBusca)
            .filter(PerfilBusca.usuario_id == usuario_id,
                    PerfilMatch.status == "novo",
                    PerfilMatch.sugestao == "",
                    PerfilMatch.data_match >= corte,
                    Licitacao.data_encerramento_proposta >= hoje)
            .order_by(Licitacao.data_encerramento_proposta)
            .limit(TETO).all())


def sugerir_triagem(sessao_db, usuario_id, agora_=None):
    """Roda a triagem nos matches novos recentes. Devolve contagens.

    Sugestão inválida ou id desconhecido são ignorados em silêncio — a
    IA barata erra formato de vez em quando e isso não pode travar nada.
    """
    cliente.exigir_chave()
    agora_ = agora_ or agora_local()
    pendentes = _pendentes(sessao_db, usuario_id, agora_)
    if not pendentes:
        return {}
    retrato = _retrato_da_empresa(sessao_db, usuario_id)
    contagem = {"participar": 0, "analisar": 0, "descartar": 0}
    for inicio in range(0, len(pendentes), LOTE):
        lote = pendentes[inicio:inicio + LOTE]
        itens = [{"id": m.id,
                  "objeto": (m.licitacao.objeto or "")[:400],
                  "valor": m.licitacao.valor_total_estimado,
                  "local": f"{m.licitacao.municipio_nome or ''}/"
                           f"{m.licitacao.uf or ''}"} for m in lote]
        try:
            resposta = cliente.chamar(
                job="triagem_matches",
                prompt_sistema=cliente.carregar_prompt("triagem-matches"),
                mensagem=json.dumps({"empresa": retrato, "itens": itens},
                                    ensure_ascii=False),
                modelo=camadas.TRIAGEM, max_tokens=4000, json_estrito=True)
            sugestoes = json.loads(resposta).get("sugestoes") or []
        except Exception:  # noqa: BLE001 — um lote ruim não trava os demais
            log.exception("Lote de triagem falhou; seguindo para o próximo")
            continue
        por_id = {m.id: m for m in lote}
        for s in sugestoes:
            m = por_id.get(s.get("id"))
            sugestao = (s.get("sugestao") or "").strip().lower()
            if m is None or sugestao not in SUGESTOES_VALIDAS:
                continue
            m.sugestao = sugestao
            m.sugestao_motivo = (s.get("motivo") or "")[:200]
            contagem[sugestao] += 1
        sessao_db.commit()
    log.info("Triagem sugerida: %s", contagem)
    return contagem
