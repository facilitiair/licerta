"""Perito documental: pipeline sobre caderno de concorrente."""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.analista import pericia_documental as pd
from app.analista.parecer import ParecerIndevido
from app.db import Base, CasoPericial, DocumentoCaso, LaudoPericial

HOJE = date(2026, 9, 1)


@pytest.fixture()
def sessao():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


@pytest.fixture()
def caso(sessao):
    c = CasoPericial(titulo="Empresa X — PE 24/2026")
    sessao.add(c)
    sessao.commit()
    return c


@pytest.fixture()
def ambiente(monkeypatch):
    chamadas = []
    monkeypatch.setenv("ANTHROPIC_API_KEY", "chave-teste")
    monkeypatch.setattr(
        pd, "_texto_documento",
        lambda d: f"ATESTADO DE CAPACIDADE — conteúdo lido de {d.nome} "
                  + "x" * 120)
    monkeypatch.setattr(pd, "examinar_pdf", lambda *a, **k: {
        "sha256": "f" * 64, "formato_real": "PDF"})

    def falso(*a, **k):
        chamadas.append(k["job"])
        if k["job"] == "laudo_revisao":
            return ("PARECER DE REVISÃO\nCorreções obrigatórias:\n"
                    "  nenhuma\nVEREDITO: aprovado")
        return f"# Saída de {k['job']}"
    monkeypatch.setattr(pd.cliente, "chamar", falso)
    monkeypatch.setattr(pd, "_custo_da_ultima_chamada", lambda: 0.5)
    # o pipeline reaproveita o _chamar da perícia — o custo é lido lá
    from app.analista import pericia
    monkeypatch.setattr(pericia, "_custo_da_ultima_chamada", lambda: 0.5)
    return chamadas


def test_caso_sem_documentos_recusa(sessao, caso, ambiente):
    with pytest.raises(ParecerIndevido):
        pd.gerar_laudo(sessao, caso)


def test_pipeline_do_laudo(sessao, caso, ambiente):
    sessao.add(DocumentoCaso(caso_id=caso.id, nome="Atestado obra Y.pdf",
                             caminho_local="casos/1/1-a.pdf"))
    sessao.commit()
    laudo = pd.gerar_laudo(sessao, caso)
    assert ambiente == ["laudo_leitor", "laudo_documental",
                        "laudo_atestados", "laudo_contraditorio",
                        "laudo_sintese", "laudo_revisao"]
    assert laudo.custo_usd == 3.0
    assert laudo.texto.startswith("> Laudo preliminar gerado")
    assert "Contraditório" in laudo.texto
    assert sessao.query(LaudoPericial).count() == 1


def test_falha_vira_laudo_visivel(sessao, caso, ambiente, monkeypatch):
    monkeypatch.setattr(pd, "Sessao", lambda: sessao)
    monkeypatch.setattr(sessao, "close", lambda: None)
    monkeypatch.setattr(pd, "gerar_laudo",
                        lambda *a, **k: (_ for _ in ()).throw(
                            RuntimeError("API fora do ar")))
    pd._em_andamento.add(caso.id)
    pd._rodar_em_fundo(caso.id, None)
    laudo = sessao.query(LaudoPericial).one()
    assert "NÃO terminou" in laudo.texto
    assert caso.id not in pd._em_andamento
