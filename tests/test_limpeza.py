"""Testes da faxina: só sai o que ninguém tocou, e nada vivo sai."""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import (Ata, Base, ColetaLog, EditalFicha, Licitacao, Minuta,
                    PerfilBusca, PerfilMatch, Usuario)
from app.radar import limpeza

HOJE = date(2026, 8, 31)


@pytest.fixture()
def sessao():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def lic(sessao, numero, encerra):
    linha = Licitacao(numero_controle_pncp=numero, objeto="x",
                      data_encerramento_proposta=encerra, fonte="pncp")
    sessao.add(linha)
    sessao.flush()
    return linha


def test_encerrada_velha_e_intocada_sai(sessao):
    velha = lic(sessao, "a", "2026-07-01T09:00:00")
    aberta = lic(sessao, "b", "2026-12-01T09:00:00")
    recente = lic(sessao, "c", "2026-08-25T09:00:00")   # encerrada há 6 dias
    sem_prazo = lic(sessao, "d", None)
    sessao.commit()
    contadores = limpeza.limpar(sessao, hoje=HOJE, vacuum=False)
    assert contadores["licitacoes"] == 1
    vivos = {l.numero_controle_pncp for l in sessao.query(Licitacao)}
    assert vivos == {"b", "c", "d"}


def test_interacao_humana_segura_a_linha(sessao):
    usuario = Usuario(nome="U", email="u@x", senha_hash="h")
    sessao.add(usuario)
    sessao.flush()
    perfil = PerfilBusca(nome="P", usuario_id=usuario.id)
    sessao.add(perfil)
    sessao.flush()
    favorita = lic(sessao, "fav", "2026-07-01T09:00:00")
    anotada = lic(sessao, "anot", "2026-07-01T09:00:00")
    movida = lic(sessao, "mov", "2026-07-01T09:00:00")
    com_minuta = lic(sessao, "min", "2026-07-01T09:00:00")
    solta = lic(sessao, "solta", "2026-07-01T09:00:00")
    sessao.add_all([
        PerfilMatch(perfil_id=perfil.id, licitacao_id=favorita.id,
                    favorito=True),
        PerfilMatch(perfil_id=perfil.id, licitacao_id=anotada.id,
                    anotacao="ver depois"),
        PerfilMatch(perfil_id=perfil.id, licitacao_id=movida.id,
                    status="descartado"),
        PerfilMatch(perfil_id=perfil.id, licitacao_id=solta.id),  # não tocado
        Minuta(licitacao_id=com_minuta.id, tipo="impugnacao", texto="m"),
    ])
    sessao.commit()
    limpeza.limpar(sessao, hoje=HOJE, vacuum=False)
    vivos = {l.numero_controle_pncp for l in sessao.query(Licitacao)}
    assert vivos == {"fav", "anot", "mov", "min"}
    # o match não tocado da linha removida foi junto — nada de órfão
    assert sessao.query(PerfilMatch).count() == 3


def test_dependentes_saem_juntos(sessao):
    velha = lic(sessao, "a", "2026-07-01T09:00:00")
    sessao.add(EditalFicha(licitacao_id=velha.id, ficha_json="{}"))
    sessao.commit()
    limpeza.limpar(sessao, hoje=HOJE, vacuum=False)
    assert sessao.query(EditalFicha).count() == 0


def test_atas_vencidas_e_logs_antigos(sessao):
    sessao.add_all([
        Ata(numero_controle_ata="v", vigencia_fim="2026-07-01"),
        Ata(numero_controle_ata="ok", vigencia_fim="2026-12-01"),
    ])
    from datetime import datetime, timedelta
    for i in range(limpeza.MANTER_LOGS + 20):
        sessao.add(ColetaLog(inicio=datetime(2026, 1, 1)
                             + timedelta(hours=i)))
    sessao.commit()
    contadores = limpeza.limpar(sessao, hoje=HOJE, vacuum=False)
    assert contadores["atas"] == 1 and contadores["logs"] == 20
    assert sessao.query(Ata).one().numero_controle_ata == "ok"
    assert sessao.query(ColetaLog).count() == limpeza.MANTER_LOGS
