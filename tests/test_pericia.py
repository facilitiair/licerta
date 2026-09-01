"""Perícia completa: pipeline leitor → peritos → síntese, condicionais
por material no dossiê, custo somado e laudos anexados ao parecer."""
import json
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.analista import parecer as analista
from app.analista import pericia
from app.db import Base, DocumentoEmpresa, Licitacao, Parecer

HOJE = date(2026, 9, 1)


@pytest.fixture()
def sessao():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


@pytest.fixture()
def lic(sessao):
    licitacao = Licitacao(
        numero_controle_pncp="x-1-7/2026", objeto="Manutenção de ar",
        modalidade_nome="Pregão", numero_compra="7", ano_compra=2026,
        orgao_nome="Pref.", municipio_nome="Teresina", uf="PI",
        fonte="pncp", data_encerramento_proposta="2026-09-20T09:00:00")
    sessao.add(licitacao)
    sessao.commit()
    return licitacao


@pytest.fixture()
def ambiente(monkeypatch):
    """Chave presente, edital 'legível', dossiê legível, IA dublada."""
    chamadas = []
    monkeypatch.setenv("ANTHROPIC_API_KEY", "chave-teste")
    monkeypatch.setattr(analista, "extrair_texto_pdfs",
                        lambda arqs: ("CLÁUSULA 9.1 DO EDITAL " * 30, []))
    monkeypatch.setattr(analista, "_texto_documento",
                        lambda d: f"CONTEÚDO LIDO DE {d.nome}")

    def falso(*a, **k):
        chamadas.append(k["job"])
        return f"# Saída de {k['job']}\n\nParecer gerado automaticamente" \
            if k["job"] == "pericia_sintese" else f"# Saída de {k['job']}"
    monkeypatch.setattr(pericia.cliente, "chamar", falso)
    monkeypatch.setattr(pericia, "_custo_da_ultima_chamada", lambda: 0.5)
    return chamadas


def test_pipeline_completo_com_material(sessao, lic, ambiente):
    sessao.add_all([
        DocumentoEmpresa(nome="Atestado obra X",
                         tipo="Atestado de Capacidade"),
        DocumentoEmpresa(nome="Balanço 2025", tipo="Balanço Patrimonial"),
        DocumentoEmpresa(nome="CND Federal", tipo="CND Federal (RFB/PGFN)",
                         validade="2027-02-28"),
    ])
    sessao.commit()
    p = pericia.gerar_pericia(sessao, lic, hoje=HOJE)
    assert ambiente == ["pericia_leitor", "pericia_documental",
                       "pericia_atestados", "pericia_contabil",
                       "pericia_contraditorio", "pericia_sintese",
                       "pericia_revisao", "pericia_correcao"]
    assert p.custo_usd == 4.0                      # 8 etapas × 0.5
    assert "peritos" in p.modelo
    assert "Anexos — laudos dos peritos" in p.texto
    assert "perito de atestados" in p.texto
    assert "Contraditório" in p.texto
    assert p.texto.startswith("> Parecer gerado automaticamente") or \
        "Parecer gerado automaticamente" in p.texto[:400]


def test_peritos_condicionais_so_entram_com_material(sessao, lic, ambiente):
    """Documental e contraditório sempre acompanham docs legíveis;
    atestados e contábil só com material do seu tipo."""
    sessao.add(DocumentoEmpresa(nome="CND Federal",
                                tipo="CND Federal (RFB/PGFN)"))
    sessao.commit()
    pericia.gerar_pericia(sessao, lic, hoje=HOJE)
    assert "pericia_atestados" not in ambiente
    assert "pericia_contabil" not in ambiente
    assert "pericia_documental" in ambiente
    assert "pericia_contraditorio" in ambiente


def test_revisor_aprovado_pula_a_correcao(sessao, lic, ambiente,
                                          monkeypatch):
    def falso(*a, **k):
        ambiente.append(k["job"])
        if k["job"] == "pericia_revisao":
            return ("PARECER DE REVISÃO\nCorreções obrigatórias:\n"
                    "  nenhuma\nVEREDITO: aprovado")
        return f"# Saída de {k['job']}\n\nParecer gerado automaticamente"
    monkeypatch.setattr(pericia.cliente, "chamar", falso)
    pericia.gerar_pericia(sessao, lic, hoje=HOJE)
    assert "pericia_correcao" not in ambiente


def test_iniciar_nao_duplica(sessao, lic, ambiente, monkeypatch):
    """Segundo clique com perícia em andamento não paga duas."""
    rodadas = []
    monkeypatch.setattr(pericia.threading, "Thread",
                        lambda **k: type("T", (), {
                            "start": lambda self: rodadas.append(1)})())
    assert pericia.iniciar(sessao, lic, hoje=HOJE) is True
    assert pericia.iniciar(sessao, lic, hoje=HOJE) is False
    pericia._em_andamento.discard(lic.id)
    assert rodadas == [1]


def test_falha_no_fundo_vira_parecer_visivel(sessao, lic, ambiente,
                                             monkeypatch):
    monkeypatch.setattr(pericia, "Sessao", lambda: sessao)
    monkeypatch.setattr(sessao, "close", lambda: None)
    monkeypatch.setattr(pericia, "gerar_pericia",
                        lambda *a, **k: (_ for _ in ()).throw(
                            RuntimeError("API fora do ar")))
    pericia._em_andamento.add(lic.id)
    pericia._rodar_em_fundo(lic.id, None)
    p = sessao.query(Parecer).one()
    assert "NÃO terminou" in p.texto and "API fora do ar" in p.texto
    assert lic.id not in pericia._em_andamento
