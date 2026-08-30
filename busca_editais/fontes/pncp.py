"""Coletor do PNCP — API pública de consulta.

Endpoint: /v1/contratacoes/proposta = contratações com recebimento de
propostas em aberto. Exige dataFinal, modalidade e aceita filtro por UF.
"""
import time
from datetime import date, timedelta

import requests

BASE = "https://pncp.gov.br/api/consulta/v1/contratacoes/proposta"
TIMEOUT = 30
TAMANHO_PAGINA = 50  # mínimo aceito: 10
PAUSA_ENTRE_REQUISICOES = 1.2  # segundos; a API limita a frequência (HTTP 429)
MAX_TENTATIVAS = 5


def _get_com_backoff(sessao, params, log):
    espera = 5
    for tentativa in range(MAX_TENTATIVAS):
        resp = sessao.get(BASE, params=params, timeout=TIMEOUT)
        if resp.status_code != 429:
            return resp
        log(f"  PNCP: limite de requisições (429), aguardando {espera}s...")
        time.sleep(espera)
        espera *= 2
    return resp


def _link_edital(numero_controle):
    # "06553481000300-1-000018/2026" -> pncp.gov.br/app/editais/{cnpj}/{ano}/{seq}
    try:
        cnpj, _, resto = numero_controle.split("-")
        seq, ano = resto.split("/")
        return f"https://pncp.gov.br/app/editais/{cnpj}/{ano}/{int(seq)}"
    except (ValueError, AttributeError):
        return None


def _mapear(r):
    org = r.get("unidadeOrgao") or {}
    ente = r.get("orgaoEntidade") or {}
    return {
        "fonte": "pncp",
        "id_fonte": r.get("numeroControlePNCP"),
        "orgao": ente.get("razaoSocial") or org.get("nomeUnidade"),
        "municipio": org.get("municipioNome"),
        "uf": org.get("ufSigla"),
        "modalidade": r.get("modalidadeNome"),
        "objeto": r.get("objetoCompra"),
        "valor_estimado": r.get("valorTotalEstimado"),
        "data_publicacao": (r.get("dataPublicacaoPncp") or "")[:10],
        "data_abertura": (r.get("dataAberturaProposta") or "")[:16],
        "data_encerramento": (r.get("dataEncerramentoProposta") or "")[:16],
        "situacao": r.get("situacaoCompraNome"),
        "link": _link_edital(r.get("numeroControlePNCP")) or r.get("linkSistemaOrigem"),
    }


def coletar(config, log=print):
    """Gera dicts de licitações com proposta aberta nas UFs/modalidades da config."""
    data_final = (date.today() + timedelta(days=config.get("dias_horizonte", 90)))
    data_final = data_final.strftime("%Y%m%d")
    sessao = requests.Session()
    ufs = config.get("ufs") or [None]  # lista vazia = Brasil inteiro (sem filtro de UF)
    for uf in ufs:
        for modalidade in config.get("modalidades", [6]):
            pagina, total_paginas = 1, 1
            while pagina <= total_paginas:
                time.sleep(PAUSA_ENTRE_REQUISICOES)
                params = {
                    "dataFinal": data_final,
                    "codigoModalidadeContratacao": modalidade,
                    "pagina": pagina,
                    "tamanhoPagina": TAMANHO_PAGINA,
                }
                if uf:
                    params["uf"] = uf
                resp = _get_com_backoff(sessao, params, log)
                if resp.status_code == 204:
                    break
                resp.raise_for_status()
                dados = resp.json()
                total_paginas = dados.get("totalPaginas") or 1
                if pagina == 1:
                    log(f"  PNCP {uf or 'BR'} modalidade {modalidade}: "
                        f"{dados.get('totalRegistros', 0)} registros")
                for r in dados.get("data") or []:
                    yield _mapear(r)
                pagina += 1
