"""Busca textual ao vivo no PNCP — a mesma API que o portal usa.

Diferente da API de consulta (que exige modalidade e não filtra por texto),
esta aceita qualquer palavra-chave, qualquer estado, e devolve na hora.
Exige cabeçalhos de navegador (o WAF derruba clientes sem User-Agent real).
"""
import requests

from .matcher import normalizar
from .pncp import montar_link_pncp

URL = "https://pncp.gov.br/api/search/"
TIMEOUT = 30
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Referer": "https://pncp.gov.br/app/editais",
}
STATUS = {"abertas": "recebendo_proposta", "encerradas": "encerradas", "todas": ""}


def pesquisar(q="", uf="", status="abertas", pagina=1, tam_pagina=20):
    params = {"tipos_documento": "edital", "ordenacao": "-data",
              "pagina": pagina, "tam_pagina": tam_pagina}
    if q:
        params["q"] = q
    if uf:
        params["ufs"] = uf
    st = STATUS.get(status, "recebendo_proposta")
    if st:
        params["status"] = st
    resp = requests.get(URL, params=params, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    dados = resp.json()
    return {"total": dados.get("total", 0),
            "itens": [_mapear(i) for i in dados.get("items") or []]}


def _mapear(i):
    objeto = (i.get("description") or "").strip()
    return {
        "numero_controle_pncp": i.get("numero_controle_pncp"),
        "fonte": "pncp",
        "objeto": objeto,
        "objeto_norm": normalizar(objeto),
        "modalidade_codigo": int(i["modalidade_licitacao_id"])
            if i.get("modalidade_licitacao_id") else None,
        "modalidade_nome": i.get("modalidade_licitacao_nome"),
        "orgao_cnpj": i.get("orgao_cnpj"),
        "orgao_nome": i.get("orgao_nome"),
        "unidade_nome": i.get("unidade_nome"),
        "municipio_nome": i.get("municipio_nome"),
        "uf": i.get("uf"),
        "municipio_ibge": None,
        "numero_compra": i.get("numero"),
        "ano_compra": int(i["ano"]) if i.get("ano") else None,
        "processo": None,
        "valor_total_estimado": i.get("valor_global"),
        "srp": False,
        "data_publicacao_pncp": i.get("data_publicacao_pncp"),
        "data_abertura_proposta": i.get("data_inicio_vigencia"),
        "data_encerramento_proposta": i.get("data_fim_vigencia"),
        "link_sistema_origem": None,
        "link_pncp": montar_link_pncp(i.get("numero_controle_pncp")),
        "situacao": i.get("situacao_nome"),
        "payload_json": None,
    }
