"""Testes do módulo Editais (ficha por IA): validação do JSON, cache
'1× por edital', degradação sem chave e sem texto. A chamada de IA é
sempre dublada — teste não gasta token."""
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import ArquivoEdital, Base, EditalFicha, Licitacao
from app.editais import analise


@pytest.fixture()
def sessao():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


@pytest.fixture()
def lic(sessao):
    licitacao = Licitacao(numero_controle_pncp="00000000000000-1-000001/2026",
                          objeto="Manutenção de ar condicionado",
                          orgao_cnpj="00000000000000", ano_compra=2026,
                          uf="PI", fonte="pncp")
    sessao.add(licitacao)
    sessao.commit()
    return licitacao


@pytest.fixture()
def ia_dublada(monkeypatch, sessao, lic):
    """Ambiente completo de mentira: chave presente, PDF 'lido', IA que
    devolve o que o teste mandar e contador de chamadas."""
    estado = {"chamadas": 0, "resposta": json.dumps({
        "resumo": "Pregão de manutenção de ar condicionado.",
        "habilitacao": {"tecnica": ["atestado de capacidade"]},
        "riscos": [{"clausula": "9.1", "motivo": "prazo apertado"}],
    })}
    monkeypatch.setenv("ANTHROPIC_API_KEY", "chave-de-teste")
    monkeypatch.setattr(analise, "extrair_texto_pdfs",
                        lambda arqs: ("TEXTO DO EDITAL " * 20, arqs))
    def falso_chamar(**kwargs):
        estado["chamadas"] += 1
        return estado["resposta"]
    monkeypatch.setattr(analise.cliente, "chamar",
                        lambda *a, **k: falso_chamar(**k))
    monkeypatch.setattr(analise, "_custo_da_ultima_chamada", lambda: 0.1234)
    sessao.add(ArquivoEdital(licitacao_id=lic.id, titulo="Edital",
                             tipo="Edital", caminho_local="x.pdf"))
    sessao.commit()
    return estado


# ------------------------------------------------------------ validação
def test_validar_completa_o_esqueleto():
    dados = analise._validar_ficha('{"resumo": "ok"}')
    assert dados["riscos"] == [] and dados["habilitacao"]["tecnica"] == []
    assert dados["lei_base"] is None       # escalar ausente vira None, nunca
    assert dados["datas"] == {}            # Undefined no template


def test_validar_rejeita_nao_objeto():
    with pytest.raises(ValueError):
        analise._validar_ficha('["uma", "lista"]')
    with pytest.raises(ValueError):
        analise._validar_ficha("não é json")


def test_validar_conserta_tipos_trocados():
    dados = analise._validar_ficha(
        '{"habilitacao": "nada", "riscos": "nenhum", "pontos_atencao": "um só"}')
    assert dados["habilitacao"]["juridica"] == []
    assert dados["riscos"] == []
    assert dados["pontos_atencao"] == ["um só"]


# ------------------------------------------------------- fluxo principal
def test_gera_ficha_e_grava_custo(sessao, lic, ia_dublada):
    ficha = analise.analisar_edital(sessao, lic)
    assert ficha.ficha_json and not ficha.erro
    assert ficha.custo_usd == 0.1234
    assert ficha.versao_prompt == analise.VERSAO_PROMPT
    dados = json.loads(ficha.ficha_json)
    assert dados["resumo"].startswith("Pregão")


def test_ficha_e_ativo_global_analisa_uma_vez_so(sessao, lic, ia_dublada):
    analise.analisar_edital(sessao, lic)
    analise.analisar_edital(sessao, lic)     # segundo clique: cache
    assert ia_dublada["chamadas"] == 1
    assert sessao.query(EditalFicha).count() == 1


def test_forcar_regera_e_substitui(sessao, lic, ia_dublada):
    analise.analisar_edital(sessao, lic)
    ia_dublada["resposta"] = json.dumps({"resumo": "Versão nova."})
    ficha = analise.analisar_edital(sessao, lic, forcar=True)
    assert ia_dublada["chamadas"] == 2
    assert json.loads(ficha.ficha_json)["resumo"] == "Versão nova."
    assert sessao.query(EditalFicha).count() == 1


def test_sem_chave_explica_em_vez_de_quebrar(sessao, lic, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(analise.SemChaveIA):
        analise.analisar_edital(sessao, lic)
    assert sessao.query(EditalFicha).count() == 0   # nada gravado pela metade


def test_pdf_escaneado_vira_erro_legivel(sessao, lic, ia_dublada, monkeypatch):
    monkeypatch.setattr(analise, "extrair_texto_pdfs", lambda arqs: ("", []))
    ficha = analise.analisar_edital(sessao, lic)
    assert not ficha.ficha_json and "escaneados" in ficha.erro
    assert ia_dublada["chamadas"] == 0     # não paga IA por imagem


def test_ia_fora_do_ar_vira_erro_e_pode_tentar_de_novo(sessao, lic, ia_dublada,
                                                       monkeypatch):
    def explode(*a, **k):
        raise RuntimeError("API 500")
    monkeypatch.setattr(analise.cliente, "chamar", explode)
    ficha = analise.analisar_edital(sessao, lic)
    assert "falhou" in ficha.erro and not ficha.ficha_json
    # a IA volta: a MESMA linha é reaproveitada (erro pendente não trava)
    monkeypatch.setattr(analise.cliente, "chamar",
                        lambda *a, **k: '{"resumo": "agora foi"}')
    ficha2 = analise.analisar_edital(sessao, lic)
    assert ficha2.id == ficha.id and ficha2.ficha_json and not ficha2.erro


def test_resposta_com_cerca_de_codigo_e_aceita():
    texto = '```json\n{"resumo": "ok"}\n```'
    from ia.cliente import _extrair_json
    assert json.loads(_extrair_json(texto))["resumo"] == "ok"


def test_limite_de_caracteres_e_respeitado(sessao, lic, ia_dublada,
                                           monkeypatch):
    gigante = "x" * (analise.LIMITE_CARACTERES + 50_000)
    monkeypatch.setattr(analise, "extrair_texto_pdfs",
                        lambda arqs: (gigante[:analise.LIMITE_CARACTERES], arqs))
    ficha = analise.analisar_edital(sessao, lic)
    assert ficha.caracteres_lidos <= analise.LIMITE_CARACTERES
