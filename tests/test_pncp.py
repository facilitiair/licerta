"""Teste do cliente da API com resposta mockada (SPEC §10)."""
import json

from app.ingestao.pncp import mapear_registro, montar_link_pncp, propostas_abertas

# Resposta real da API (capturada em chamada ao vivo), resumida
REGISTRO = {
    "numeroControlePNCP": "06553481000300-1-000018/2026",
    "objetoCompra": "Contratação de serviços de limpeza",
    "modalidadeId": 6,
    "modalidadeNome": "Pregão - Eletrônico",
    "srp": False,
    "anoCompra": 2026,
    "numeroCompra": "90008",
    "processo": "00201.000180/2025",
    "valorTotalEstimado": 935530.08,
    "dataPublicacaoPncp": "2026-06-29T07:12:40",
    "dataAberturaProposta": "2026-08-13T08:00:00",
    "dataEncerramentoProposta": "2026-08-31T09:00:00",
    "linkSistemaOrigem": "https://exemplo.gov.br/compra/1",
    "unidadeOrgao": {"ufSigla": "PI", "municipioNome": "Teresina",
                     "codigoIbge": "2211001",
                     "nomeUnidade": "SECRETARIA DE ADMINISTRAÇÃO"},
    "orgaoEntidade": {"cnpj": "06553481000300", "razaoSocial": "ESTADO DO PIAUI"},
}


def test_situacao_unificada_entre_fontes():
    # "Divulgada no PNCP" e "Divulgada" (TCE) precisam virar o mesmo valor,
    # senão o filtro de situação separa as fontes por acidente
    m = mapear_registro(dict(REGISTRO, situacaoCompraNome="Divulgada no PNCP"))
    assert m["situacao"] == "Divulgada"


def test_mapear_registro_usa_nomes_reais_da_api():
    m = mapear_registro(REGISTRO)
    assert m["numero_controle_pncp"] == "06553481000300-1-000018/2026"
    assert m["objeto"] == "Contratação de serviços de limpeza"
    assert m["uf"] == "PI"
    assert m["municipio_nome"] == "Teresina"
    assert m["municipio_ibge"] == "2211001"
    assert m["orgao_cnpj"] == "06553481000300"
    assert m["valor_total_estimado"] == 935530.08
    assert m["modalidade_codigo"] == 6
    assert json.loads(m["payload_json"])["numeroControlePNCP"]


def test_link_pncp_formato_do_portal():
    # Formato verificado em licitações reais: /app/editais/{cnpj}/{ano}/{seq}
    assert montar_link_pncp("06553481000300-1-000018/2026") == \
        "https://pncp.gov.br/app/editais/06553481000300/2026/18"
    assert montar_link_pncp(None) is None
    assert montar_link_pncp("lixo") is None


class RespostaFake:
    def __init__(self, status, corpo=None):
        self.status_code = status
        self._corpo = corpo or {}

    def json(self):
        return self._corpo

    def raise_for_status(self):
        pass


class SessaoFake:
    """Simula a API: 2 páginas de resultados, depois fim."""
    def __init__(self):
        self.chamadas = []

    def get(self, url, params=None, timeout=None):
        self.chamadas.append(params)
        pagina = params["pagina"]
        if pagina > 2:
            return RespostaFake(204)
        return RespostaFake(200, {
            "totalPaginas": 2,
            "data": [dict(REGISTRO,
                          numeroControlePNCP=f"x-1-00000{pagina}/2026")],
        })


def test_propostas_abertas_pagina_ate_o_fim(monkeypatch):
    monkeypatch.setattr("app.ingestao.pncp.PAUSA", 0)  # sem espera nos testes
    sessao = SessaoFake()
    itens = list(propostas_abertas(6, uf="PI", sessao=sessao))
    assert len(itens) == 2
    assert sessao.chamadas[0]["dataFinal"]           # exige dataFinal...
    assert "dataInicial" not in sessao.chamadas[0]   # ...e NUNCA dataInicial
    assert sessao.chamadas[0]["uf"] == "PI"
