"""Busca textual livre no PNCP (API usada pelo próprio portal).

Diferente da API de consulta, aceita qualquer palavra-chave e devolve
editais do Brasil inteiro. Exige cabeçalhos de navegador (WAF).
"""
import requests

URL = "https://pncp.gov.br/api/search/"
TIMEOUT = 30
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Referer": "https://pncp.gov.br/app/editais",
}

STATUS = {
    "abertas": "recebendo_proposta",
    "encerradas": "encerradas",
    "todas": "",
}


def pesquisar(q="", ufs=None, status="abertas", pagina=1, tam_pagina=20):
    params = {
        "tipos_documento": "edital",
        "ordenacao": "-data",
        "pagina": pagina,
        "tam_pagina": tam_pagina,
    }
    if q:
        params["q"] = q
    st = STATUS.get(status, "recebendo_proposta")
    if st:
        params["status"] = st
    if ufs:
        params["ufs"] = ",".join(ufs) if isinstance(ufs, (list, tuple)) else ufs
    resp = requests.get(URL, params=params, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    dados = resp.json()
    return {
        "total": dados.get("total", 0),
        "itens": [_mapear(i) for i in dados.get("items") or []],
    }


def _mapear(i):
    link = None
    if i.get("orgao_cnpj") and i.get("ano") and i.get("numero_sequencial"):
        link = (f"https://pncp.gov.br/app/editais/{i['orgao_cnpj']}"
                f"/{i['ano']}/{int(i['numero_sequencial'])}")
    return {
        "fonte": "pncp",
        "id_fonte": i.get("numero_controle_pncp"),
        "orgao": i.get("orgao_nome"),
        "municipio": i.get("municipio_nome"),
        "uf": i.get("uf"),
        "modalidade": i.get("modalidade_licitacao_nome"),
        "objeto": (i.get("description") or "").strip(),
        "valor_estimado": i.get("valor_global"),
        "data_publicacao": (i.get("data_publicacao_pncp") or "")[:10],
        "data_abertura": (i.get("data_inicio_vigencia") or "")[:16],
        "data_encerramento": (i.get("data_fim_vigencia") or "")[:16],
        "situacao": i.get("situacao_nome"),
        "link": link,
    }
