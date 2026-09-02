"""Testes da triagem sugerida por IA e do upload em lote (nome/validade
lidos do nome do arquivo)."""
import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.analista import triagem
from app.db import (Base, DocumentoEmpresa, Licitacao, PerfilBusca,
                    PerfilMatch, Usuario)
from app.documentos.validades import nome_amigavel, validade_do_nome

AGORA = datetime(2026, 8, 31, 12, 0)


# ------------------------------------------------ nome e validade do arquivo
def test_validade_do_nome():
    assert validade_do_nome("02 - FGTS VAL.24-08-2026.pdf") == "2026-08-24"
    assert validade_do_nome("04 - FEDERAL VAL 30-08-2026.pdf") == "2026-08-30"
    assert validade_do_nome("10 - TCU VAL. 21-08-2026.pdf") == "2026-08-21"
    assert validade_do_nome("CONTRATO SOCIAL.pdf") is None
    assert validade_do_nome("X VAL.99-99-2026.pdf") is None


def test_nome_amigavel():
    assert nome_amigavel("02 - FGTS VAL.24-08-2026.pdf") == "FGTS"
    assert nome_amigavel("01 - CONTRATO SOCIAL.pdf") == "CONTRATO SOCIAL"
    assert nome_amigavel("17 - CAT BOQUEIRÃO.pdf") == "CAT BOQUEIRÃO"
    assert nome_amigavel("balanço_2024_final.pdf") == "balanço 2024 final"
    assert nome_amigavel("") == "Documento"


# --------------------------------------------------------- triagem sugerida
@pytest.fixture()
def sessao():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


@pytest.fixture()
def cenario(sessao):
    u = Usuario(nome="U", email="u@x", senha_hash="h")
    sessao.add(u)
    sessao.flush()
    p = PerfilBusca(nome="Ar", usuario_id=u.id,
                    palavras_incluir=["ar condicionado"])
    sessao.add(p)
    # dossiê é privado: o documento é DESTE usuário
    sessao.add(DocumentoEmpresa(nome="Atestado clim.",
                                tipo="Atestado de Capacidade",
                                enviado_por=u.id))
    sessao.flush()
    matches = []
    for i, objeto in enumerate(["Manutenção de ar condicionado",
                                "Merenda escolar", "Roçagem de vias"]):
        lic = Licitacao(numero_controle_pncp=f"x-{i}", objeto=objeto,
                        fonte="pncp",
                        data_encerramento_proposta="2026-12-01T09:00:00")
        sessao.add(lic)
        sessao.flush()
        m = PerfilMatch(perfil_id=p.id, licitacao_id=lic.id, status="novo",
                        data_match=AGORA - timedelta(hours=2))
        sessao.add(m)
        matches.append(m)
    sessao.commit()
    return u, matches


def test_sugestoes_gravadas_e_invalidas_ignoradas(sessao, cenario,
                                                  monkeypatch):
    u, (m1, m2, m3) = cenario
    monkeypatch.setenv("ANTHROPIC_API_KEY", "chave-teste")
    resposta = {"sugestoes": [
        {"id": m1.id, "sugestao": "participar", "motivo": "ramo da empresa"},
        {"id": m2.id, "sugestao": "descartar", "motivo": "fora do ramo"},
        {"id": m3.id, "sugestao": "explodir", "motivo": "inválida"},
        {"id": 999999, "sugestao": "participar", "motivo": "id fantasma"},
    ]}
    monkeypatch.setattr(triagem.cliente, "chamar",
                        lambda *a, **k: json.dumps(resposta))
    contagem = triagem.sugerir_triagem(sessao, u.id, agora_=AGORA)
    assert contagem == {"participar": 1, "analisar": 0, "descartar": 1}
    assert m1.sugestao == "participar" and "ramo" in m1.sugestao_motivo
    assert m2.sugestao == "descartar"
    assert m3.sugestao == ""               # sugestão inválida não gruda


def test_ja_sugeridos_e_antigos_ficam_de_fora(sessao, cenario, monkeypatch):
    u, (m1, m2, m3) = cenario
    m1.sugestao = "analisar"                       # já tem sugestão
    m2.data_match = AGORA - timedelta(days=10)     # velho demais
    sessao.commit()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "chave-teste")
    capturado = {}
    def falso(*a, **k):
        capturado["msg"] = k.get("mensagem", "")
        return json.dumps({"sugestoes": []})
    monkeypatch.setattr(triagem.cliente, "chamar", falso)
    triagem.sugerir_triagem(sessao, u.id, agora_=AGORA)
    itens = json.loads(capturado["msg"])["itens"]
    assert [i["id"] for i in itens] == [m3.id]


def test_retrato_da_empresa_usa_dossie_e_perfis(sessao, cenario):
    u, _ = cenario
    retrato = triagem._retrato_da_empresa(sessao, u.id)
    assert "Atestado clim." in retrato["atestados_e_cats"]
    assert "ar condicionado" in retrato["palavras_dos_perfis_de_busca"]


def test_lote_ruim_nao_trava_os_demais(sessao, cenario, monkeypatch):
    u, (m1, m2, m3) = cenario
    monkeypatch.setenv("ANTHROPIC_API_KEY", "chave-teste")
    monkeypatch.setattr(triagem, "LOTE", 1)
    chamadas = {"n": 0}
    def instavel(*a, **k):
        chamadas["n"] += 1
        if chamadas["n"] == 2:
            raise RuntimeError("API 500")
        itens = json.loads(k["mensagem"])["itens"]
        return json.dumps({"sugestoes": [
            {"id": itens[0]["id"], "sugestao": "analisar", "motivo": "ok"}]})
    monkeypatch.setattr(triagem.cliente, "chamar", instavel)
    contagem = triagem.sugerir_triagem(sessao, u.id, agora_=AGORA)
    assert chamadas["n"] == 3              # o lote 2 falhou e seguiu adiante
    assert contagem["analisar"] == 2
