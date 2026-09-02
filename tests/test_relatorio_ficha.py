"""A ficha como documento (PDF/Word) e o pente fino (segunda leitura)."""
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import ArquivoEdital, Base, EditalFicha, Licitacao
from app.editais import analise
from app.editais.relatorio import ficha_para_markdown
from app.pdf_export import markdown_para_html, markdown_para_pdf


class LicFake:
    modalidade_nome = "Pregão eletrônico"
    numero_compra, ano_compra = "20", 2026
    orgao_nome, municipio_nome, uf = "Prefeitura de Teste", "Teresina", "PI"
    objeto = "Manutenção de ar-condicionado"
    data_encerramento_proposta = "2026-09-30T09:00:00"
    valor_total_estimado = 181370.0
    numero_controle_pncp = "x-1-20/2026"


DADOS = {
    "resumo": "Pregão de manutenção.", "lei_base": "14.133/2021",
    "criterio_julgamento": "menor preço", "srp": True,
    "datas": {"sessao_abertura": "2026-09-30T09:00"},
    "habilitacao": {"tecnica": ["atestado de capacidade técnica"],
                    "juridica": [], "fiscal_social_trabalhista": [],
                    "economico_financeira": ["índice de liquidez ≥ 1"]},
    "riscos": [{"clausula": "9.1", "motivo": "prazo apertado"}],
    "pontos_atencao": ["valor sigiloso"],
    "revisoes": [{"quando": "02/09/2026 14:00",
                  "achados": ["Cláusula 12.3: garantia de 5% não constava"]}],
}


def test_markdown_da_ficha_traz_tudo_e_nada_de_none():
    md = ficha_para_markdown(LicFake(), DADOS)
    assert "# Ficha do edital — Pregão eletrônico 20/2026" in md
    assert "atestado de capacidade técnica" in md
    assert "| Registro de preços (SRP) | sim |" in md
    assert "**9.1**: prazo apertado" in md
    assert "Pente fino nº 1" in md and "garantia de 5%" in md
    assert "None" not in md


def test_pdf_e_word_saem_do_mesmo_markdown():
    from app.docx_export import markdown_para_docx
    md = ficha_para_markdown(LicFake(), DADOS)
    pdf = markdown_para_pdf(md, rodape="Licerta")
    assert pdf.startswith(b"%PDF") and len(pdf) > 1000
    docx = markdown_para_docx(md)
    assert docx[:2] == b"PK"


def test_html_do_markdown_escapa_e_faz_listas_e_tabelas():
    html = markdown_para_html("# T\n- a <b>\n- b\n\n| x | y |\n|---|---|\n| 1 | 2 |")
    assert "<h1>T</h1>" in html and "&lt;b&gt;" in html
    assert html.count("<li>") == 2 and "<td>1</td>" in html


# ------------------------------------------------------------- pente fino
@pytest.fixture()
def sessao():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


@pytest.fixture()
def lic_com_ficha(sessao, tmp_path, monkeypatch):
    lic = Licitacao(numero_controle_pncp="00000000000000-1-000001/2026",
                    objeto="Obra", uf="PI", fonte="pncp")
    sessao.add(lic)
    sessao.flush()
    (tmp_path / "x.pdf").write_bytes(b"%PDF-1.4 de mentira")
    monkeypatch.setattr(analise, "PASTA_DADOS", str(tmp_path))
    sessao.add(ArquivoEdital(licitacao_id=lic.id, caminho_local="x.pdf"))
    sessao.add(EditalFicha(licitacao_id=lic.id, custo_usd=0.1,
                           ficha_json=json.dumps({"resumo": "primeira",
                                                  "riscos": []})))
    sessao.commit()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "chave-teste")
    monkeypatch.setattr(analise, "extrair_texto_pdfs",
                        lambda arqs: ("TEXTO DO EDITAL " * 20, arqs))
    monkeypatch.setattr(analise, "_custo_da_ultima_chamada", lambda: 0.5)
    return lic


def test_pente_fino_corrige_registra_achados_e_soma_custo(sessao, lic_com_ficha,
                                                          monkeypatch):
    capturado = {}

    def falso(**k):
        capturado.update(k)
        return json.dumps({"resumo": "revisada", "riscos": [
            {"clausula": "12.3", "motivo": "garantia não constava"}],
            "achados_do_pente_fino": ["Cláusula 12.3: garantia de 5%"]})
    monkeypatch.setattr(analise.cliente, "chamar", lambda *a, **k: falso(**k))
    ficha = analise.pente_fino_da_ficha(sessao, lic_com_ficha)
    dados = json.loads(ficha.ficha_json)
    assert dados["resumo"] == "revisada" and dados["riscos"][0]["clausula"] == "12.3"
    assert dados["revisoes"][0]["achados"] == ["Cláusula 12.3: garantia de 5%"]
    assert "achados_do_pente_fino" not in dados
    assert ficha.custo_usd == 0.6 and "pente fino" in ficha.modelo
    assert capturado["job"] == "ficha_pente_fino"
    assert "FICHA DA PRIMEIRA LEITURA" in capturado["mensagem"]
    # segunda passada empilha, não substitui
    analise.pente_fino_da_ficha(sessao, lic_com_ficha)
    assert len(json.loads(ficha.ficha_json)["revisoes"]) == 2


def test_pente_fino_que_falha_mantem_a_ficha_anterior(sessao, lic_com_ficha,
                                                      monkeypatch):
    def explode(*a, **k):
        raise RuntimeError("API 500")
    monkeypatch.setattr(analise.cliente, "chamar", explode)
    ficha = analise.pente_fino_da_ficha(sessao, lic_com_ficha)
    assert json.loads(ficha.ficha_json)["resumo"] == "primeira"
    assert "anterior continua valendo" in ficha.erro


def test_rotas_de_download_e_pente_fino():
    from fastapi.testclient import TestClient
    from app.config import config
    from app.db import Sessao
    from app.main import app
    s = Sessao()
    try:
        com_ficha = (s.query(EditalFicha.licitacao_id)
                     .filter(EditalFicha.ficha_json != "").first())
        sem_ficha = (s.query(Licitacao.id).outerjoin(EditalFicha)
                     .filter(EditalFicha.id.is_(None)).first())
    finally:
        s.close()
    with TestClient(app) as c:
        c.post("/login", data={"email": "", "senha": config.APP_SENHA},
               follow_redirects=False)
        if com_ficha:
            r = c.get(f"/licitacoes/{com_ficha[0]}/ficha/baixar?formato=pdf")
            assert r.status_code == 200 and r.content.startswith(b"%PDF")
            r = c.get(f"/licitacoes/{com_ficha[0]}/ficha/baixar?formato=docx")
            assert r.status_code == 200 and r.content[:2] == b"PK"
        if sem_ficha:
            assert c.get(f"/licitacoes/{sem_ficha[0]}/ficha/baixar").status_code \
                == 404
        assert c.post("/licitacoes/999999/pente-fino").status_code == 404


def test_ficha_antiga_sem_chaves_nao_derruba_a_pagina():
    """Produção (02/09): /licitacoes/95 e /licitacoes/95/ficha davam 500 —
    ficha gravada por versão antiga, sem `datas` e com itens que são
    dicionários. A leitura agora normaliza como a geração faz."""
    from fastapi.testclient import TestClient
    from app.config import config
    from app.db import Sessao
    from app.main import _dados_ficha, app
    velha = json.dumps({"resumo": "antiga",
                        "habilitacao": {"tecnica": [{"documento": "CAT",
                                                     "observacao": "x"}]},
                        "riscos": ["prazo apertado"],
                        "datas": {"sessao_abertura": {"iso": "2026-09-30"}}})
    dados = _dados_ficha(type("F", (), {"ficha_json": velha})())
    assert dados["habilitacao"]["tecnica"] == ["documento: CAT; observacao: x"]
    assert dados["riscos"][0]["motivo"] == "prazo apertado"
    assert isinstance(dados["datas"]["sessao_abertura"], str)
    assert dados["habilitacao"]["juridica"] == []
    s = Sessao()
    try:
        lic = (s.query(Licitacao).outerjoin(EditalFicha)
               .filter(EditalFicha.id.is_(None)).first())
        if lic is None:
            pytest.skip("banco local sem licitação livre")
        ficha = EditalFicha(licitacao_id=lic.id, ficha_json=velha)
        s.add(ficha)
        s.commit()
        lic_id, ficha_id = lic.id, ficha.id
    finally:
        s.close()
    try:
        with TestClient(app) as c:
            c.post("/login", data={"email": "", "senha": config.APP_SENHA},
                   follow_redirects=False)
            for rota in (f"/licitacoes/{lic_id}", f"/licitacoes/{lic_id}/ficha",
                         f"/licitacoes/{lic_id}/detalhe",
                         f"/licitacoes/{lic_id}/ficha/baixar?formato=pdf"):
                assert c.get(rota).status_code == 200, rota
    finally:
        s = Sessao()
        try:
            s.query(EditalFicha).filter_by(id=ficha_id).delete()
            s.commit()
        finally:
            s.close()


def test_portal_cai_para_quem_publicou_no_pncp():
    from app.main import _filtro_portal

    class L:
        link_sistema_origem, objeto, fonte = None, "Serviço de manutenção", "pncp"
        payload_json = json.dumps({"usuarioNome": "ASSESI BRASIL"})
    assert _filtro_portal(L()) == "Assesi (portal de compras)"
    L.payload_json = json.dumps({"usuarioNome": "Licitanet Licitações LTDA"})
    assert _filtro_portal(L()) == "Licitanet"
    L.payload_json = json.dumps({"usuarioNome": "SISTEMA XYZ LTDA"})
    assert _filtro_portal(L()) == "Sistema Xyz"
    L.payload_json = None
    assert _filtro_portal(L()) == ""


def test_erro_inesperado_vira_pagina_humana_e_registro(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from app import main
    from app.config import config
    monkeypatch.setattr(main, "CAMINHO_ERROS", str(tmp_path / "erros.jsonl"))

    @main.app.get("/__explode")
    def explode():
        raise RuntimeError("boom de teste")
    with TestClient(main.app, raise_server_exceptions=False) as c:
        c.post("/login", data={"email": "", "senha": config.APP_SENHA},
               follow_redirects=False)
        r = c.get("/__explode")
        assert r.status_code == 500 and "Internal Server Error" not in r.text
        assert "Não conseguimos abrir esta página" in r.text
        r = c.get("/__explode", headers={"HX-Request": "true"})
        assert "faixa" in r.text
    erros = main.erros_recentes()
    assert erros and "boom de teste" in erros[0]["erro"]
    assert "/__explode" in erros[0]["rota"]
