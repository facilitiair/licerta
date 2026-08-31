"""Testes das peças sob demanda: as recusas certas (prazo vencido, sem
riscos, sem ficha), a trava de rascunho e o custo gravado."""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, EmpresaDados, Licitacao, Minuta
from app.pecas import minutas

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
    licitacao = Licitacao(numero_controle_pncp="x-1-9/2026",
                          objeto="Obra", modalidade_nome="Concorrência",
                          numero_compra="9", ano_compra=2026,
                          orgao_nome="Pref.", municipio_nome="Teresina",
                          uf="PI", fonte="pncp",
                          data_encerramento_proposta="2026-09-20T09:00:00")
    sessao.add(licitacao)
    sessao.commit()
    return licitacao


FICHA = {"riscos": [{"clausula": "9.1", "motivo": "atestado com quantitativo "
                     "acima de 50% sem justificativa (Súmula 263/TCU)"}],
         "datas": {"sessao_abertura": "2026-09-20T09:00"}}


@pytest.fixture()
def ia_dublada(monkeypatch):
    estado = {"chamadas": 0,
              "resposta": "> ⚠️ **MINUTA GERADA POR IA — RASCUNHO.**\n\n"
                          "ILUSTRÍSSIMO SENHOR..."}
    monkeypatch.setenv("ANTHROPIC_API_KEY", "chave-teste")
    def falso(*a, **k):
        estado["chamadas"] += 1
        return estado["resposta"]
    monkeypatch.setattr(minutas.cliente, "chamar", falso)
    monkeypatch.setattr(minutas, "_custo_da_ultima_chamada", lambda: 0.08)
    monkeypatch.setattr(minutas, "extrair_texto_pdfs",
                        lambda arqs: ("CLÁUSULA 9.1 ...", []))
    return estado


def test_gera_e_grava_com_custo(sessao, lic, ia_dublada):
    minuta = minutas.gerar_impugnacao(sessao, lic, FICHA, hoje=HOJE)
    assert minuta.id and minuta.custo_usd == 0.08
    assert "MINUTA" in minuta.texto[:100]
    assert sessao.query(Minuta).count() == 1


def test_sem_ficha_orienta_a_gerar_ficha(sessao, lic, ia_dublada):
    with pytest.raises(minutas.MinutaIndevida, match="ficha"):
        minutas.gerar_impugnacao(sessao, lic, None, hoje=HOJE)


def test_sem_riscos_nao_forca_argumento(sessao, lic, ia_dublada):
    with pytest.raises(minutas.MinutaIndevida, match="risco"):
        minutas.gerar_impugnacao(sessao, lic, {"riscos": []}, hoje=HOJE)
    assert ia_dublada["chamadas"] == 0     # recusa não gasta IA


def test_prazo_vencido_recusa_e_aponta_caminhos(sessao, lic, ia_dublada):
    """Sessão 20/09, art. 164 = 3 dias úteis antes. Em 18/09 já passou."""
    with pytest.raises(minutas.MinutaIndevida, match="intempestivo"):
        minutas.gerar_impugnacao(sessao, lic, FICHA, hoje=date(2026, 9, 18))
    assert ia_dublada["chamadas"] == 0


def test_sem_chave_recusa_antes_de_tudo(sessao, lic, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from ia.cliente import SemChaveIA
    with pytest.raises(SemChaveIA):
        minutas.gerar_impugnacao(sessao, lic, FICHA, hoje=HOJE)


def test_trava_de_rascunho_e_inegociavel(sessao, lic, ia_dublada):
    """Se o modelo 'esquecer' o aviso de minuta, o código o injeta."""
    ia_dublada["resposta"] = "ILUSTRÍSSIMO SENHOR PREGOEIRO..."
    minuta = minutas.gerar_impugnacao(sessao, lic, FICHA, hoje=HOJE)
    assert minuta.texto.startswith("> ⚠️ **MINUTA GERADA POR IA")


def test_empresa_vazia_vira_preencher(sessao, lic, ia_dublada, monkeypatch):
    capturado = {}
    def espiao(*a, **k):
        capturado["mensagem"] = k.get("mensagem", "")
        return "> ⚠️ **MINUTA...**\n corpo"
    monkeypatch.setattr(minutas.cliente, "chamar", espiao)
    minutas.gerar_impugnacao(sessao, lic, FICHA, hoje=HOJE)
    assert "[PREENCHER: razão social]" in capturado["mensagem"]


def test_dados_da_empresa_preenchidos_entram(sessao, lic, ia_dublada,
                                             monkeypatch):
    sessao.add(EmpresaDados(id=1, razao_social="Construtora Genérica LTDA",
                            cnpj="00.000.000/0001-00"))
    sessao.commit()
    capturado = {}
    def espiao(*a, **k):
        capturado["mensagem"] = k.get("mensagem", "")
        return "> ⚠️ **MINUTA...**\n corpo"
    monkeypatch.setattr(minutas.cliente, "chamar", espiao)
    minutas.gerar_impugnacao(sessao, lic, FICHA, hoje=HOJE)
    assert "Construtora Genérica LTDA" in capturado["mensagem"]
