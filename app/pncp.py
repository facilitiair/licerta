"""Cliente da API de consulta do PNCP (SPEC §3).

Campos da resposta confirmados em chamadas reais à API nesta máquina
(objetoCompra, numeroControlePNCP, unidadeOrgao.*, orgaoEntidade.* etc.).
Rate limit tratado com pausa entre chamadas + retry com backoff.
"""
import json
import logging
import time
from datetime import date, timedelta

import requests

log = logging.getLogger("radar.pncp")

BASE = "https://pncp.gov.br/api/consulta"
TIMEOUT = 30
PAUSA = 0.3                 # ~300 ms entre chamadas (SPEC §3.2.4)
TENTATIVAS = 3
TAMANHO_PAGINA = 500        # máximo aceito pela API; cai para 50 se recusado

# Tabela de domínio do Manual de APIs de Consulta (SPEC §3.3)
MODALIDADES = {
    1: "Leilão eletrônico", 2: "Diálogo competitivo", 3: "Concurso",
    4: "Concorrência eletrônica", 5: "Concorrência presencial",
    6: "Pregão eletrônico", 7: "Pregão presencial", 8: "Dispensa de licitação",
    9: "Inexigibilidade", 10: "Manifestação de interesse",
    11: "Pré-qualificação", 12: "Credenciamento", 13: "Leilão presencial",
}


def _get(sessao, url, params):
    """GET com retry exponencial. Devolve a resposta ou levanta a última falha."""
    espera = 2.0
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            time.sleep(PAUSA)
            resp = sessao.get(url, params=params, timeout=TIMEOUT)
            if resp.status_code == 429:
                raise requests.HTTPError("429 rate limit", response=resp)
            return resp
        except (requests.RequestException, requests.HTTPError) as e:
            if tentativa == TENTATIVAS:
                raise
            log.warning("PNCP tentativa %s falhou (%s); aguardando %.0fs",
                        tentativa, e, espera)
            time.sleep(espera)
            espera *= 2
    raise RuntimeError("inalcançável")


def montar_link_pncp(numero_controle):
    """'CNPJ-1-SEQ/ANO' -> https://pncp.gov.br/app/editais/CNPJ/ANO/SEQ
    (formato verificado abrindo licitações reais no portal)."""
    try:
        cnpj, _, resto = numero_controle.split("-")
        seq, ano = resto.split("/")
        return f"https://pncp.gov.br/app/editais/{cnpj}/{ano}/{int(seq)}"
    except (ValueError, AttributeError):
        return None


def mapear_registro(r):
    """Converte um registro da API para o formato da tabela `licitacoes`."""
    org = r.get("unidadeOrgao") or {}
    ente = r.get("orgaoEntidade") or {}
    return {
        "numero_controle_pncp": r.get("numeroControlePNCP"),
        "objeto": r.get("objetoCompra"),
        "modalidade_codigo": r.get("modalidadeId"),
        "modalidade_nome": r.get("modalidadeNome"),
        "orgao_cnpj": ente.get("cnpj"),
        "orgao_nome": ente.get("razaoSocial"),
        "unidade_nome": org.get("nomeUnidade"),
        "municipio_nome": org.get("municipioNome"),
        "uf": org.get("ufSigla"),
        "municipio_ibge": str(org.get("codigoIbge") or ""),
        "numero_compra": r.get("numeroCompra"),
        "ano_compra": r.get("anoCompra"),
        "processo": r.get("processo"),
        "valor_total_estimado": r.get("valorTotalEstimado"),
        "srp": bool(r.get("srp")),
        "data_publicacao_pncp": r.get("dataPublicacaoPncp"),
        "data_abertura_proposta": r.get("dataAberturaProposta"),
        "data_encerramento_proposta": r.get("dataEncerramentoProposta"),
        "link_sistema_origem": r.get("linkSistemaOrigem"),
        "link_pncp": montar_link_pncp(r.get("numeroControlePNCP")),
        "payload_json": json.dumps(r, ensure_ascii=False),
    }


def propostas_abertas(modalidade, uf=None, dias_futuro=90, sessao=None):
    """Itera todas as páginas de /v1/contratacoes/proposta para uma combinação.

    ATENÇÃO (SPEC §3.1): este endpoint aceita SOMENTE dataFinal — nunca
    enviar dataInicial aqui.
    """
    sessao = sessao or requests.Session()
    data_final = (date.today() + timedelta(days=dias_futuro)).strftime("%Y%m%d")
    tamanho = TAMANHO_PAGINA
    pagina, total_paginas = 1, 1
    while pagina <= total_paginas:
        params = {
            "dataFinal": data_final,
            "codigoModalidadeContratacao": modalidade,
            "pagina": pagina,
            "tamanhoPagina": tamanho,
        }
        if uf:
            params["uf"] = uf
        resp = _get(sessao, f"{BASE}/v1/contratacoes/proposta", params)
        if resp.status_code == 204:      # sem resultados para a combinação
            return
        if resp.status_code == 400 and tamanho != 50:
            tamanho = 50                 # API recusou o tamanho; usa o padrão
            continue
        resp.raise_for_status()
        dados = resp.json()
        total_paginas = dados.get("totalPaginas") or 1
        for registro in dados.get("data") or []:
            yield mapear_registro(registro)
        pagina += 1


def _link_compra(numero_controle_compra):
    """A página da compra no portal também lista as atas vinculadas."""
    return montar_link_pncp(numero_controle_compra)


def mapear_ata(r):
    return {
        "numero_controle_ata": r.get("numeroControlePNCPAta"),
        "numero_controle_compra": r.get("numeroControlePNCPCompra"),
        "numero_ata": r.get("numeroAtaRegistroPreco"),
        "ano_ata": r.get("anoAta"),
        "objeto": r.get("objetoContratacao"),
        "orgao_cnpj": r.get("cnpjOrgao"),
        "orgao_nome": r.get("nomeOrgao"),
        "unidade_nome": r.get("nomeUnidadeOrgao"),
        "data_assinatura": r.get("dataAssinatura"),
        "vigencia_inicio": r.get("vigenciaInicio"),
        "vigencia_fim": r.get("vigenciaFim"),
        "possibilidade_adesao": bool(r.get("possibilidadeAdesao")),
        "cancelado": bool(r.get("cancelado")),
        "link_pncp": _link_compra(r.get("numeroControlePNCPCompra")),
        "payload_json": json.dumps(r, ensure_ascii=False),
    }


def atas_atualizadas(dias_retro=2, sessao=None):
    """Atas alteradas nos últimos N dias (varredura incremental diária).

    O endpoint /v1/atas não filtra por UF, então o recorte por interesse
    é feito localmente, pelas palavras dos perfis.
    """
    sessao = sessao or requests.Session()
    hoje = date.today()
    params_base = {
        "dataInicial": (hoje - timedelta(days=dias_retro)).strftime("%Y%m%d"),
        "dataFinal": hoje.strftime("%Y%m%d"),
        "tamanhoPagina": TAMANHO_PAGINA,
    }
    pagina, total_paginas = 1, 1
    while pagina <= total_paginas:
        resp = _get(sessao, f"{BASE}/v1/atas/atualizacao",
                    dict(params_base, pagina=pagina))
        if resp.status_code == 204:
            return
        resp.raise_for_status()
        dados = resp.json()
        total_paginas = dados.get("totalPaginas") or 1
        for registro in dados.get("data") or []:
            yield mapear_ata(registro)
        pagina += 1


def listar_arquivos_compra(cnpj, ano, sequencial, sessao=None):
    """Documentos publicados da compra (edital, anexos...) — API do portal."""
    sessao = sessao or requests.Session()
    url = (f"https://pncp.gov.br/pncp-api/v1/orgaos/{cnpj}"
           f"/compras/{ano}/{sequencial}/arquivos")
    resp = sessao.get(url, params={"pagina": 1, "tamanhoPagina": 20},
                      timeout=TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
    if not resp.ok:
        return []
    dados = resp.json()
    return dados if isinstance(dados, list) else []


def baixar_municipios_ibge():
    """Lista oficial de municípios do IBGE (SPEC §3.4). Uma vez, na instalação."""
    r = requests.get(
        "https://servicodados.ibge.gov.br/api/v1/localidades/municipios",
        params={"view": "nivelado"}, timeout=60)
    r.raise_for_status()
    municipios = []
    for m in r.json():
        # view=nivelado traz chaves planas; mantém fallback para o formato aninhado
        codigo = m.get("municipio-id") or m.get("id")
        nome = m.get("municipio-nome") or m.get("nome")
        uf = m.get("UF-sigla") or (((m.get("microrregiao") or {})
                                    .get("mesorregiao") or {})
                                   .get("UF") or {}).get("sigla")
        if codigo and nome and uf:
            municipios.append({"codigo_ibge": str(codigo), "nome": nome, "uf": uf})
    return municipios
