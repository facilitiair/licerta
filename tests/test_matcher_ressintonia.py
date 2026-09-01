"""Perfil editado remove casamentos que não casam mais — preservando
o que o usuário já triou, favoritou ou anotou."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, Licitacao, PerfilBusca, PerfilMatch
from app.radar.matcher import ressintonizar_matches


@pytest.fixture()
def sessao():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def test_ressintonia_limpa_estado_errado_e_preserva_triados(sessao):
    perfil = PerfilBusca(nome="ar PI", ufs=["PI"],
                         palavras_incluir=["ar condicionado"],
                         somente_vigentes=False)
    pi = Licitacao(numero_controle_pncp="a-1-1/2026", uf="PI",
                   objeto="Manutenção de ar condicionado", fonte="pncp")
    ac = Licitacao(numero_controle_pncp="b-1-2/2026", uf="AC",
                   objeto="Manutenção de ar condicionado", fonte="pncp")
    ac2 = Licitacao(numero_controle_pncp="c-1-3/2026", uf="AC",
                    objeto="Ar condicionado do fórum", fonte="pncp")
    sessao.add_all([perfil, pi, ac, ac2])
    sessao.commit()
    sessao.add_all([
        PerfilMatch(perfil_id=perfil.id, licitacao_id=pi.id),
        PerfilMatch(perfil_id=perfil.id, licitacao_id=ac.id),   # lixo
        PerfilMatch(perfil_id=perfil.id, licitacao_id=ac2.id,
                    status="vou_participar"),                   # triado!
    ])
    sessao.commit()
    removidos = ressintonizar_matches(sessao, perfil)
    sessao.commit()
    assert removidos == 1
    restantes = {m.licitacao_id for m in sessao.query(PerfilMatch)}
    assert restantes == {pi.id, ac2.id}   # PI fica; AC triado fica; lixo sai
