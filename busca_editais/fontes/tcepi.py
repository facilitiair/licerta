"""Coletor do Mural de Licitações do TCE-PI (melhor esforço).

O Mural é uma aplicação JSF/PrimeFaces sem API pública: simulamos o
postback do botão Pesquisar e a paginação AJAX do DataTable. Se o TCE
alterar o site, este coletor falha com aviso — o PNCP segue funcionando.
"""
import re
from datetime import date, timedelta

import requests

URL = "https://sistemas.tce.pi.gov.br/muralic/index.xhtml"
TIMEOUT = 40
LINHAS_POR_PAGINA = 100

RE_VIEWSTATE = re.compile(r'name="javax\.faces\.ViewState"[^>]*value="([^"]+)"')
RE_UPDATE = re.compile(
    r'<update id="(?:j_idt\d+|formListaLic:listaLic)"><!\[CDATA\[(.*?)\]\]></update>', re.S)
RE_LINHA = re.compile(r'<tr[^>]*data-ri[^>]*>(.*?)</tr>', re.S)
RE_CELULA = re.compile(r'<td[^>]*>(.*?)</td>', re.S)
RE_ROWCOUNT = re.compile(r'rowCount:(\d+)')
RE_DETALHE = re.compile(r'detalhelicitacao\.xhtml\?id=(\d+)')


def _texto(html):
    txt = re.sub(r'<[^>]+>', ' ', html)
    txt = (txt.replace('&#39;', "'").replace('&amp;', '&')
              .replace('&lt;', '<').replace('&gt;', '>').replace('&nbsp;', ' '))
    return re.sub(r'\s+', ' ', txt).strip()


def _valor(txt):
    try:
        return float(txt.replace('.', '').replace(',', '.'))
    except ValueError:
        return None


def _data_iso(txt):
    # "15/09/2026 09:00" -> "2026-09-15T09:00" | "15/09/2026" -> "2026-09-15"
    m = re.match(r'(\d{2})/(\d{2})/(\d{4})(?:\s+(\d{2}:\d{2}))?', txt or '')
    if not m:
        return None
    iso = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return f"{iso}T{m.group(4)}" if m.group(4) else iso


def _mapear(linha_html):
    celulas = [_texto(c) for c in RE_CELULA.findall(linha_html)]
    if len(celulas) < 16:
        return None
    m_id = RE_DETALHE.search(linha_html)
    link = (f"https://sistemas.tce.pi.gov.br/muralic/detalhelicitacao.xhtml?id={m_id.group(1)}"
            if m_id else None)
    orgao = celulas[0]
    municipio = None
    m_pref = re.search(r'(?:PREFEITURA|C[ÂA]MARA)\s+MUNICIPAL\s+DE\s+(.+)', orgao, re.I)
    if m_pref:
        municipio = m_pref.group(1).title()
    abertura = _data_iso(celulas[10])
    return {
        "fonte": "tcepi",
        "id_fonte": celulas[2] or (m_id.group(1) if m_id else None),
        "orgao": orgao,
        "municipio": municipio,
        "uf": "PI",
        "modalidade": f"{celulas[5]} {celulas[6]}".strip(),
        "objeto": celulas[9],
        "valor_estimado": _valor(celulas[12]),
        "data_publicacao": _data_iso(celulas[15]),
        "data_abertura": abertura,
        "data_encerramento": abertura,  # sessão de abertura = prazo das propostas
        "situacao": celulas[14],
        "link": link,
    }


def _post_ajax(sessao, viewstate, dados_extra):
    base = {
        "javax.faces.partial.ajax": "true",
        "javax.faces.ViewState": viewstate,
    }
    base.update(dados_extra)
    resp = sessao.post(URL, data=base, timeout=TIMEOUT, headers={
        "Faces-Request": "partial/ajax",
        "X-Requested-With": "XMLHttpRequest",
    })
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def coletar(config, log=print):
    cfg = config.get("tcepi") or {}
    dias_retro = cfg.get("dias_retroativos", 7)
    horizonte = config.get("dias_horizonte", 90)
    hoje = date.today()
    d_ini = (hoje - timedelta(days=dias_retro)).strftime("%d/%m/%Y")
    d_fim = (hoje + timedelta(days=horizonte)).strftime("%d/%m/%Y")

    sessao = requests.Session()
    pagina_inicial = sessao.get(URL, timeout=TIMEOUT)
    pagina_inicial.raise_for_status()
    m = RE_VIEWSTATE.search(pagina_inicial.text)
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
    log(f"  TCE-PI Mural: {total} registros (aberturas {d_ini} a {d_fim})")
    if not total:
        return

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
            if item and item["id_fonte"]:
                yield item
        primeiro += LINHAS_POR_PAGINA
