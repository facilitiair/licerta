"""Checklist de habilitação: exigência da ficha × documento do dossiê.

Cruzamento por CÓDIGO (palavras-chave → tipo de documento), apresentado
sempre como aproximação — quem bate o martelo é gente. Duas regras
periciais herdadas da prática:

1. Validade se afere na DATA DA SESSÃO, não na de hoje: certidão vigente
   hoje que vence antes da sessão é problema HOJE.
2. Exigência sem correspondência clara sai como "conferir manualmente" —
   nunca como "não tem". O mapa é mapa, não fonte.
"""
import re
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


# Frases ESPECÍFICAS para reconhecer o tipo pelo CONTEÚDO do PDF — usadas
# quando o nome do arquivo não diz nada (celular que envia o nome sem as
# letras acentuadas: "Certido de Dvida Ativa"). Aqui palavra solta é
# proibida: todo PDF oficial carrega "SERVIÇO PÚBLICO FEDERAL" ou "ESTADO
# DO PIAUÍ" no cabeçalho, e um "federal" genérico marcaria a certidão do
# CREA como CND Federal. A ordem importa: a primeira que casar decide.
REGRAS_CONTEUDO = [
    (("certificado de regularidade do fgts",), "CRF do FGTS"),
    (("debitos trabalhistas", "justica do trabalho"), "CNDT Trabalhista"),
    (("registro e quitacao", "conselho regional de engenharia",
      "conselho de arquitetura"), "Registro CREA/CAU"),
    (("falencia", "concordata", "recuperacao judicial"),
     "Certidão de Falência"),
    (("receita federal", "divida ativa da uniao",
      "procuradoria-geral da fazenda nacional"), "CND Federal (RFB/PGFN)"),
    (("divida ativa do estado", "fazenda publica estadual", "sefaz",
      "secretaria da fazenda do estado",
      "secretaria de fazenda do estado"), "CND Estadual"),
    (("divida ativa do municipio", "fazenda publica municipal",
      "codigo tributario do municipio",
      "secretaria municipal de financas"), "CND Municipal"),
    (("balanco patrimonial",), "Balanço Patrimonial"),
    (("acervo tecnico",), "CAT"),
    (("atestado de capacidade",), "Atestado de Capacidade"),
    (("alvara de funcionamento", "alvara de localizacao"), "Alvará"),
]


def tipo_do_conteudo(texto):
    """Tipo lido do texto do PDF — só frases específicas, ordem decide."""
    plano = _norm(texto)
    for frases, tipo in REGRAS_CONTEUDO:
        if any(f in plano for f in frases):
            return tipo
    return None


def _tem_palavra(palavra, plano):
    """Casa por palavra inteira: "iss" não pode pegar "emissão", nem
    "cat" pegar "categoria", nem "uniao" pegar "reunião" — cada um
    virava veredito de um documento que não tinha nada a ver."""
    return re.search(rf"(?<![a-z0-9]){re.escape(palavra)}(?![a-z0-9])",
                     plano) is not None


def tipo_sugerido(exigencia):
    """Qual tipo de documento do dossiê esta exigência provavelmente pede."""
    plano = _norm(exigencia)
    for palavras, tipo in REGRAS:
        if any(_tem_palavra(p, plano) for p in palavras):
            return tipo
    return None


def _data(bruto):
    try:
        return datetime.strptime(str(bruto)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def data_da_sessao(ficha_dados, lic):
    """A data que vale para aferir validade: sessão da ficha, senão o
    encerramento de propostas do portal, senão None (o chamador usa hoje).

    Cada candidata é tentada por sua vez: uma data da ficha fora do ISO
    ("20/09/2026") não pode derrubar a do portal. E se o portal diz que as
    propostas fecham DEPOIS da sessão da ficha, a ficha envelheceu (prazo
    prorrogado) — vale o portal, senão o checklist dizia "sessão passou".
    """
    da_ficha = _data((ficha_dados.get("datas") or {}).get("sessao_abertura")
                     if ficha_dados else None)
    do_portal = _data(getattr(lic, "data_encerramento_proposta", None))
    if da_ficha and do_portal and do_portal > da_ficha:
        return do_portal
    return da_ficha or do_portal


def avaliar(ficha_dados, lic, documentos, hoje=None):
    """Monta o checklist. Devolve (itens, data_sessao).

    Cada item: {exigencia, tipo, doc, veredito}, com veredito em:
    'ok' (documento vigente na data da sessão), 'vence_antes' (vigente hoje
    mas não chega à sessão), 'vencido', 'falta' (tipo mapeado e nenhum
    documento) e 'conferir' (exigência sem mapa — decide o humano).
    """
    from ..config import hoje as hoje_local
    hoje = hoje or hoje_local()
    sessao = data_da_sessao(ficha_dados, lic)
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
