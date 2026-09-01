"""Testes do parecer do analista: insumos, dossiê na data da sessão,
base jurídica anexada e o aviso de apoio à decisão."""
import json
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.analista import parecer as analista
from app.db import (Base, DocumentoEmpresa, EditalFicha, Licitacao, Parecer)

HOJE = date(2026, 8, 31)


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
def ambiente(monkeypatch, sessao, lic):
    """Chave presente, edital 'legível', IA dublada que captura a entrada."""
    capturado = {}
    monkeypatch.setenv("ANTHROPIC_API_KEY", "chave-teste")
    monkeypatch.setattr(analista, "extrair_texto_pdfs",
                        lambda arqs: ("CLÁUSULA 9.1 DO EDITAL " * 30, []))
    def falso(*a, **k):
        capturado.update(k)
        return "# Parecer — Pregão 7/2026\n\n## 1. Em uma frase\nVale."
    monkeypatch.setattr(analista.cliente, "chamar", falso)
    monkeypatch.setattr(analista, "_custo_da_ultima_chamada", lambda: 0.42)
    return capturado


def test_gera_grava_e_prefixa_o_aviso(sessao, lic, ambiente):
    p = analista.gerar_parecer(sessao, lic, hoje=HOJE)
    assert p.id and p.custo_usd == 0.42
    assert p.texto.startswith("> Parecer gerado automaticamente")
    assert sessao.query(Parecer).count() == 1


def test_prazos_entram_calculados_no_prompt(sessao, lic, ambiente):
    analista.gerar_parecer(sessao, lic, hoje=HOJE)
    msg = ambiente["mensagem"]
    # sessão 20/09 → art. 164 = 3 dias úteis antes = 16/09 (qua)
    assert "impugnação/esclarecimento até 16/09/2026" in msg
    assert "art. 164" in msg


def test_dossie_com_validade_na_data_da_sessao(sessao, lic, ambiente):
    sessao.add_all([
        DocumentoEmpresa(nome="CND boa", tipo="CND Federal (RFB/PGFN)",
                         validade="2026-12-01"),
        DocumentoEmpresa(nome="CRF morta", tipo="CRF do FGTS",
                         validade="2026-09-10"),   # morre antes da sessão
        DocumentoEmpresa(nome="Arquivada", tipo="CAT", arquivado=True),
    ])
    sessao.commit()
    analista.gerar_parecer(sessao, lic, hoje=HOJE)
    msg = ambiente["mensagem"]
    assert "válido até 2026-12-01" in msg
    assert "VENCIDO na data da sessão" in msg
    assert "Arquivada" not in msg          # arquivado não vai à perícia


def test_base_juridica_anexada(sessao, lic, ambiente):
    analista.gerar_parecer(sessao, lic, hoje=HOJE)
    assert "BASE JURÍDICA:" in ambiente["mensagem"]
    assert "14.133" in ambiente["mensagem"]


def test_modelo_forte_e_o_da_pericia(sessao, lic, ambiente):
    analista.gerar_parecer(sessao, lic, hoje=HOJE)
    from ia import camadas
    assert ambiente["modelo"] == camadas.PERICIA


def test_sem_material_nenhum_recusa_sem_gastar(sessao, lic, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "chave-teste")
    monkeypatch.setattr(analista, "extrair_texto_pdfs",
                        lambda arqs: ("", []))
    chamadas = []
    monkeypatch.setattr(analista.cliente, "chamar",
                        lambda *a, **k: chamadas.append(1))
    with pytest.raises(analista.ParecerIndevido):
        analista.gerar_parecer(sessao, lic, hoje=HOJE)
    assert not chamadas


def test_sem_pdf_mas_com_ficha_gera_pela_ficha(sessao, lic, ambiente,
                                               monkeypatch):
    monkeypatch.setattr(analista, "extrair_texto_pdfs",
                        lambda arqs: ("", []))
    sessao.add(EditalFicha(licitacao_id=lic.id, ficha_json=json.dumps(
        {"resumo": "ok", "riscos": []})))
    sessao.commit()
    p = analista.gerar_parecer(sessao, lic, hoje=HOJE)
    assert p.id and "análise pela ficha" in ambiente["mensagem"]
