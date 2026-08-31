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
ORDENACOES = {"recentes": "-data", "antigas": "data", "relevancia": "relevancia"}

# Cache das opções de filtro do portal (municípios e órgãos com seus IDs)
_opcoes_cache = {"quando": 0.0, "municipios": [], "orgaos": []}
_OPCOES_TTL = 6 * 3600


def _carregar_opcoes():
    import time
    if time.time() - _opcoes_cache["quando"] < _OPCOES_TTL and \
            _opcoes_cache["municipios"]:
        return _opcoes_cache
    r = requests.get("https://pncp.gov.br/api/search/filters", headers=HEADERS,
                     params={"tipos_documento": "edital",
                             "status": "recebendo_proposta"}, timeout=40)
    r.raise_for_status()
    filtros = r.json().get("filters") or {}
    _opcoes_cache["municipios"] = [
        {"id": str(m["id"]), "nome": m["nome"],
         "nome_norm": normalizar(m["nome"])}
        for m in filtros.get("municipios") or [] if m.get("id")]
    _opcoes_cache["orgaos"] = [
        {"id": str(o["id"]), "nome": o["nome"], "cnpj": o.get("cnpj", ""),
         "nome_norm": normalizar(o["nome"])}
        for o in filtros.get("orgaos") or [] if o.get("id")]
    _opcoes_cache["quando"] = time.time()
    return _opcoes_cache


def buscar_opcoes(tipo, q, limite=12):
    """Busca por digitação nas opções do portal (municipios | orgaos)."""
    try:
        opcoes = _carregar_opcoes().get(tipo) or []
    except Exception:  # noqa: BLE001 — sem opções, o filtro só fica indisponível
        return []
    alvo = normalizar(q)
    return [o for o in opcoes if alvo in o["nome_norm"]][:limite]


def nome_opcao(tipo, id_):
    for o in _opcoes_cache.get(tipo) or []:
        if o["id"] == str(id_):
            return o["nome"]
    return str(id_)


def pesquisar(q="", uf="", status="abertas", pagina=1, tam_pagina=20,
              ufs=None, modalidades=None, esferas=None, ordenacao="recentes",
              municipios=None, orgaos=None):
    """Busca avançada. Listas (ufs/modalidades/esferas) usam o separador '|',
    formato aceito pela API do portal (validado ao vivo: os totais somam)."""
    params = {"tipos_documento": "edital",
              "ordenacao": ORDENACOES.get(ordenacao, "-data"),
              "pagina": pagina, "tam_pagina": tam_pagina}
    if q:
        params["q"] = q
    lista_ufs = list(ufs or ([] if not uf else [uf]))
    if lista_ufs:
        params["ufs"] = "|".join(lista_ufs)
    if modalidades:
        params["modalidades"] = "|".join(str(m) for m in modalidades)
    if esferas:
        params["esferas"] = "|".join(esferas)
    if municipios:
        params["municipios"] = "|".join(str(m) for m in municipios)
    if orgaos:
        params["orgaos"] = "|".join(str(o) for o in orgaos)
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
        # Mesma normalização do motor de coleta (pncp.py): a busca ao vivo
        # devolve "Divulgada no PNCP", que não bate com o filtro de situação
        # dos perfis. Salvar um resultado à mão gravava esse valor e o edital
        # salvo nunca virava alerta — ou pior, sobrescrevia o valor bom de uma
        # licitação que a coleta já tinha trazido, sumindo do filtro.
        "situacao": (i.get("situacao_nome") or "").replace(" no PNCP", "") or None,
        "payload_json": None,
    }
