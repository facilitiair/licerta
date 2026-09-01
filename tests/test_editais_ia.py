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
def ia_dublada(monkeypatch, sessao, lic, tmp_path):
    """Ambiente completo de mentira: chave presente, PDF 'lido', IA que
    devolve o que o teste mandar e contador de chamadas."""
    # O arquivo precisa EXISTIR no disco: linha órfã não conta como baixada.
    (tmp_path / "x.pdf").write_bytes(b"%PDF-1.4 de mentira")
    monkeypatch.setattr(analise, "PASTA_DADOS", str(tmp_path))
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


def test_sem_arquivo_no_disco_diz_a_verdade(sessao, lic, ia_dublada,
                                            monkeypatch):
    """Linha no banco sem arquivo no disco: tenta baixar de novo e, se nada
    vier, a mensagem distingue 'download falhou' de 'órgão não publicou' —
    nunca mais a mentira 'não tem documento publicado'."""
    import os
    monkeypatch.setattr(analise, "extrair_texto_pdfs", lambda arqs: ("", []))
    os.remove(os.path.join(analise.PASTA_DADOS, "x.pdf"))   # arquivo sumiu
    monkeypatch.setattr("app.editais.arquivos.baixar_arquivos",
                        lambda *a, **k: 0)
    # O portal LISTA documentos → a culpa é do download, e a frase diz isso.
    monkeypatch.setattr(
        "app.ingestao.pncp.listar_arquivos_compra",
        lambda *a, **k: [{"url": "https://pncp.gov.br/x", "statusAtivo": True}])
    ficha = analise.analisar_edital(sessao, lic)
    assert "download não funcionou" in ficha.erro
    assert ia_dublada["chamadas"] == 0


def test_orgao_sem_documento_publicado(sessao, lic, ia_dublada, monkeypatch):
    monkeypatch.setattr(analise, "extrair_texto_pdfs", lambda arqs: ("", []))
    import os
    os.remove(os.path.join(analise.PASTA_DADOS, "x.pdf"))
    monkeypatch.setattr("app.editais.arquivos.baixar_arquivos",
                        lambda *a, **k: 0)
    monkeypatch.setattr("app.ingestao.pncp.listar_arquivos_compra",
                        lambda *a, **k: [])
    ficha = analise.analisar_edital(sessao, lic)
    assert "ainda não publicou" in ficha.erro


def test_pncp_fora_do_ar_nao_culpa_o_orgao(sessao, lic, ia_dublada,
                                           monkeypatch):
    import os
    monkeypatch.setattr(analise, "extrair_texto_pdfs", lambda arqs: ("", []))
    os.remove(os.path.join(analise.PASTA_DADOS, "x.pdf"))
    monkeypatch.setattr("app.editais.arquivos.baixar_arquivos",
                        lambda *a, **k: 0)
    def explode(*a, **k):
        raise RuntimeError("timeout")
    monkeypatch.setattr("app.ingestao.pncp.listar_arquivos_compra", explode)
    ficha = analise.analisar_edital(sessao, lic)
    assert "não respondeu" in ficha.erro


def test_ia_fora_do_ar_vira_erro_e_pode_tentar_de_novo(sessao, lic, ia_dublada,
                                                       monkeypatch):
    def explode(*a, **k):
        raise RuntimeError("API 500")
    monkeypatch.setattr(analise.cliente, "chamar", explode)
    ficha = analise.analisar_edital(sessao, lic)
    # A tela fala a língua do usuário (UI §7): nada de HTTP nem stack —
    # o motivo técnico vai para o log.
    assert "não terminou" in ficha.erro and not ficha.ficha_json
    assert "500" not in ficha.erro
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
