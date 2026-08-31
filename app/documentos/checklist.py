"""Checklist de habilitação: exigência da ficha × documento do dossiê.

Cruzamento por CÓDIGO (palavras-chave → tipo de documento), apresentado
sempre como aproximação — quem bate o martelo é gente. Duas regras
periciais herdadas da prática:

1. Validade se afere na DATA DA SESSÃO, não na de hoje: certidão vigente
   hoje que vence antes da sessão é problema HOJE.
2. Exigência sem correspondência clara sai como "conferir manualmente" —
   nunca como "não tem". O mapa é mapa, não fonte.
"""
import unicodedata
from datetime import datetime

from .validades import dias_para_vencer

# Palavras (sem acento, minúsculas) -> tipo de documento do dossiê.
# A ORDEM importa: a primeira regra que casar decide, então as mais
# específicas vêm antes ("divida ativa da uniao" antes de "municipal").
REGRAS = [
    (("fgts", "crf"), "CRF do FGTS"),
    (("trabalhista", "cndt"), "CNDT Trabalhista"),
    (("federal", "receita federal", "divida ativa da uniao", "uniao",
      "rfb", "pgfn", "inss", "seguridade"), "CND Federal (RFB/PGFN)"),
    (("estadual", "fazenda estadual", "sefaz"), "CND Estadual"),
    (("municipal", "fazenda municipal", "iss"), "CND Municipal"),
    (("falencia", "concordata", "recuperacao judicial"),
     "Certidão de Falência"),
    (("contrato social", "ato constitutivo", "estatuto", "requerimento de "
      "empresario", "registro comercial"), "Contrato Social"),
    (("balanco", "demonstracoes contabeis", "indices contabeis",
      "patrimonio liquido", "capital social"), "Balanço Patrimonial"),
    (("atestado", "capacidade tecnica", "aptidao"),
     "Atestado de Capacidade"),
    (("cat", "acervo tecnico"), "CAT"),
    (("crea", "cau", "conselho regional"), "Registro CREA/CAU"),
    (("alvara", "licenca de funcionamento"), "Alvará"),
    (("procuracao", "credenciamento"), "Procuração"),
]


def _norm(texto):
    texto = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in texto if not unicodedata.combining(c))


def tipo_sugerido(exigencia):
    """Qual tipo de documento do dossiê esta exigência provavelmente pede."""
    plano = _norm(exigencia)
    for palavras, tipo in REGRAS:
        if any(p in plano for p in palavras):
            return tipo
    return None


def _data_sessao(ficha_dados, lic):
    """A data que vale para aferir validade: sessão da ficha, senão o
    encerramento de propostas do portal, senão hoje (pior aproximação)."""
    bruto = ((ficha_dados.get("datas") or {}).get("sessao_abertura")
             if ficha_dados else None) or \
        getattr(lic, "data_encerramento_proposta", None) or ""
    try:
        return datetime.strptime(bruto[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def avaliar(ficha_dados, lic, documentos, hoje=None):
    """Monta o checklist. Devolve (itens, data_sessao).

    Cada item: {exigencia, tipo, doc, veredito}, com veredito em:
    'ok' (documento vigente na data da sessão), 'vence_antes' (vigente hoje
    mas não chega à sessão), 'vencido', 'falta' (tipo mapeado e nenhum
    documento) e 'conferir' (exigência sem mapa — decide o humano).
    """
    from ..config import hoje as hoje_local
    hoje = hoje or hoje_local()
    sessao = _data_sessao(ficha_dados, lic)
    referencia = sessao or hoje
    por_tipo = {}
    for d in documentos:
        if not getattr(d, "arquivado", False):
            por_tipo.setdefault(d.tipo, []).append(d)
    exigencias = []
    habilitacao = (ficha_dados or {}).get("habilitacao") or {}
    for bloco in ("juridica", "fiscal_social_trabalhista", "tecnica",
                  "economico_financeira"):
        exigencias += habilitacao.get(bloco) or []
    itens = []
    for exigencia in exigencias:
        tipo = tipo_sugerido(exigencia)
        docs = por_tipo.get(tipo, []) if tipo else []
        if not tipo:
            itens.append({"exigencia": exigencia, "tipo": None, "doc": None,
                          "veredito": "conferir"})
            continue
        if not docs:
            itens.append({"exigencia": exigencia, "tipo": tipo, "doc": None,
                          "veredito": "falta"})
            continue
        # O melhor candidato é o de validade mais distante (o mais renovado)
        def _validade(d):
            return d.validade or "9999-12-31"   # sem validade = não vence
        doc = max(docs, key=_validade)
        dias_ate_sessao = None
        if doc.validade:
            try:
                validade = datetime.strptime(doc.validade, "%Y-%m-%d").date()
                dias_ate_sessao = (validade - referencia).days
            except ValueError:
                pass
        if dias_ate_sessao is not None and dias_ate_sessao < 0:
            venceu_ja = (dias_para_vencer(doc, hoje) or 0) < 0
            veredito = "vencido" if venceu_ja else "vence_antes"
        else:
            veredito = "ok"
        itens.append({"exigencia": exigencia, "tipo": tipo, "doc": doc,
                      "veredito": veredito})
    return itens, sessao
