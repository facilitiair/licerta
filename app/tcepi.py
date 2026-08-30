"""Coletor complementar: Mural de Licitações do TCE-PI (Fase 3, melhor esforço).

O Mural é uma aplicação JSF/PrimeFaces sem API: simulamos o postback do
botão Pesquisar e a paginação AJAX do DataTable (técnica validada em
produção na versão anterior deste projeto). Se o TCE mudar o site, o
coletor falha com aviso no log e o PNCP segue normalmente.
"""
import json
import re
from datetime import date, timedelta

import requests

from .matcher import normalizar

URL = "https://sistemas.tce.pi.gov.br/muralic/index.xhtml"
TIMEOUT = 40
LINHAS_POR_PAGINA = 100

RE_VIEWSTATE = re.compile(r'name="javax\.faces\.ViewState"[^>]*value="([^"]+)"')
RE_LINHA = re.compile(r'<tr[^>]*data-ri[^>]*>(.*?)</tr>', re.S)
RE_CELULA = re.compile(r'<td[^>]*>(.*?)</td>', re.S)
RE_ROWCOUNT = re.compile(r'rowCount:(\d+)')
RE_DETALHE = re.compile(r'detalhelicitacao\.xhtml\?id=(\d+)')

# Mapeia o texto do Mural para os códigos de modalidade do PNCP
MODALIDADE_TCE = {
    ("concorrencia", "eletronica"): (4, "Concorrência eletrônica"),
    ("concorrencia", "presencial"): (5, "Concorrência presencial"),
    ("pregao", "eletronica"): (6, "Pregão eletrônico"),
    ("pregao", "presencial"): (7, "Pregão presencial"),
    ("dispensa", ""): (8, "Dispensa de licitação"),
    ("inexigibilidade", ""): (9, "Inexigibilidade"),
    ("credenciamento", ""): (12, "Credenciamento"),
    ("leilao", "eletronica"): (1, "Leilão eletrônico"),
    ("leilao", "presencial"): (13, "Leilão presencial"),
    ("concurso", ""): (3, "Concurso"),
}


def _modalidade(nome, forma):
    n, f = normalizar(nome), normalizar(forma)
    for (chave_n, chave_f), (codigo, rotulo) in MODALIDADE_TCE.items():
        if chave_n in n and (not chave_f or chave_f in f):
            return codigo, rotulo
    return None, f"{nome} {forma}".strip()


def _texto(html_bruto):
    txt = re.sub(r'<[^>]+>', ' ', html_bruto)
    txt = (txt.replace('&#39;', "'").replace('&amp;', '&')
              .replace('&lt;', '<').replace('&gt;', '>').replace('&nbsp;', ' '))
    return re.sub(r'\s+', ' ', txt).strip()


def _valor(txt):
    try:
        return float(txt.replace('.', '').replace(',', '.'))
    except ValueError:
        return None


def _data_iso(txt):
    m = re.match(r'(\d{2})/(\d{2})/(\d{4})(?:\s+(\d{2}:\d{2}))?', txt or '')
    if not m:
        return None
    iso = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return f"{iso}T{m.group(4)}:00" if m.group(4) else iso


def _mapear(linha_html):
    """Colunas do Mural (validadas em produção): 0 órgão · 2 código LW ·
    5 modalidade · 6 forma · 9 objeto · 10 abertura · 12 valor · 14 situação
    · 15 publicação."""
    c = [_texto(x) for x in RE_CELULA.findall(linha_html)]
    if len(c) < 16 or not c[2]:
        return None
    m_id = RE_DETALHE.search(linha_html)
    codigo, modalidade_nome = _modalidade(c[5], c[6])
    municipio = None
    m_pref = re.search(r'(?:PREFEITURA|C[ÂA]MARA)\s+MUNICIPAL\s+DE\s+(.+)',
                       c[0], re.I)
    if m_pref:
        municipio = m_pref.group(1).title()
    abertura = _data_iso(c[10])
    return {
        "numero_controle_pncp": f"TCEPI-{c[2]}",   # chave única própria
        "fonte": "tcepi",
        "objeto": c[9],
        "modalidade_codigo": codigo,
        "modalidade_nome": modalidade_nome,
        "orgao_cnpj": None,
        "orgao_nome": c[0],
        "unidade_nome": None,
        "municipio_nome": municipio,
        "uf": "PI",
        "municipio_ibge": None,
        "numero_compra": c[3] if len(c) > 3 else None,
        "ano_compra": None,
        "processo": None,
        "valor_total_estimado": _valor(c[12]),
        "srp": False,
        "data_publicacao_pncp": _data_iso(c[15]),
        "data_abertura_proposta": abertura,
        "data_encerramento_proposta": abertura,  # sessão = prazo das propostas
        "link_sistema_origem":
            (f"https://sistemas.tce.pi.gov.br/muralic/detalhelicitacao.xhtml"
             f"?id={m_id.group(1)}" if m_id else None),
        "link_pncp": None,
        "payload_json": json.dumps({"colunas": c}, ensure_ascii=False),
    }


def _post_ajax(sessao, viewstate, dados_extra):
    dados = {"javax.faces.partial.ajax": "true",
             "javax.faces.ViewState": viewstate}
    dados.update(dados_extra)
    resp = sessao.post(URL, data=dados, timeout=TIMEOUT, headers={
        "Faces-Request": "partial/ajax",
        "X-Requested-With": "XMLHttpRequest"})
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def coletar_mural(dias_retro=7, dias_futuro=90):
    """Gera licitações do Mural com abertura entre hoje-N e hoje+M."""
    hoje = date.today()
    d_ini = (hoje - timedelta(days=dias_retro)).strftime("%d/%m/%Y")
    d_fim = (hoje + timedelta(days=dias_futuro)).strftime("%d/%m/%Y")

    sessao = requests.Session()
    inicial = sessao.get(URL, timeout=TIMEOUT)
    inicial.raise_for_status()
    m = RE_VIEWSTATE.search(inicial.text)
    if not m:
        raise RuntimeError("Mural TCE-PI: ViewState não encontrado (site mudou?)")
    viewstate = m.group(1)

    xml = _post_ajax(sessao, viewstate, {
        "javax.faces.source": "btnPesquisar",
        "javax.faces.partial.execute": "j_idt20",
        "javax.faces.partial.render": "growl j_idt20 formListaLic:listaLic",
        "btnPesquisar": "btnPesquisar",
        "j_idt20": "j_idt20",
        "tvPrincipal_activeIndex": "0",
        "tvPrincipal:dataAberturaInicial_input": d_ini,
        "tvPrincipal:dataAberturaFinal_input": d_fim,
        "tvPrincipal:mod_input": "",
        "tvPrincipal:status_input": "",
        "tvPrincipal:ug_input": "",
    })
    m_total = RE_ROWCOUNT.search(xml)
    total = int(m_total.group(1)) if m_total else 0
    primeiro = 0
    while primeiro < total:
        xml_pag = _post_ajax(sessao, viewstate, {
            "javax.faces.source": "formListaLic:listaLic",
            "javax.faces.partial.execute": "formListaLic:listaLic",
            "javax.faces.partial.render": "formListaLic:listaLic",
            "formListaLic:listaLic": "formListaLic:listaLic",
            "formListaLic:listaLic_pagination": "true",
            "formListaLic:listaLic_first": str(primeiro),
            "formListaLic:listaLic_rows": str(LINHAS_POR_PAGINA),
            "formListaLic:listaLic_skipChildren": "true",
            "formListaLic:listaLic_encodeFeature": "true",
            "formListaLic": "formListaLic",
        })
        linhas = RE_LINHA.findall(xml_pag)
        if not linhas:
            break
        for linha in linhas:
            item = _mapear(linha)
            if item:
                yield item
        primeiro += LINHAS_POR_PAGINA
