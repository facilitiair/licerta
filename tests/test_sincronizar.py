"""Sincronização de perfis: o site é a fonte da verdade, os outros puxam."""
import hashlib
import hmac

import pytest
from fastapi.testclient import TestClient

from app.config import config
from app.db import PerfilBusca, Sessao
from app.main import app
from app.sincronizar import CAMPOS, PERFIL_SISTEMA, aplicar_perfis


@pytest.fixture(scope="module")
def cliente():
    with TestClient(app) as c:
        r = c.post("/login", data={"email": "", "senha": config.APP_SENHA},
                   follow_redirects=False)
        assert r.status_code == 303
        yield c


def _perfil_remoto(nome, **extra):
    base = {c: None for c in CAMPOS}
    base.update({
        "nome": nome, "ativo": True, "ufs": ["PI"], "municipios_ibge": [],
        "modalidades": [6], "palavras_incluir": ['"split"'],
        "palavras_excluir": [], "somente_srp": False, "modo_busca": "ou",
        "ordenacao": "encerramento_asc", "situacoes": ["Divulgada"],
        "somente_vigentes": True, "notificar": True, "frequencia": "diario",
        "intervalo_horas": 3, "dia_semana": 0, "dia_mes": 1, "mes_ano": 1,
        "hora_envio": "07:00",
    })
    base.update(extra)
    return base


def test_exportacao_exige_login_e_devolve_json(cliente):
    r = cliente.get("/api/perfis/exportar")
    assert r.status_code == 200
    perfis = r.json()
    assert isinstance(perfis, list) and perfis
    assert set(CAMPOS) <= set(perfis[0])
    assert all(p["nome"] != PERFIL_SISTEMA for p in perfis)
    # nada de estado operacional na configuração
    assert "ultimo_envio" not in perfis[0]
    assert "id" not in perfis[0]


def test_exportacao_sem_login_redireciona():
    with TestClient(app) as anonimo:
        r = anonimo.get("/api/perfis/exportar", follow_redirects=False)
        if config.APP_SENHA:
            assert r.status_code == 303


def test_aplicar_atualiza_por_nome_e_cria_o_que_falta():
    s = Sessao()
    try:
        existente = s.query(PerfilBusca).first()
        remoto = _perfil_remoto(existente.nome,
                                palavras_incluir=['"teste-sincronia"'])
        novo = _perfil_remoto("Perfil que só existe no site")
        atualizados, criados = aplicar_perfis(s, [remoto, novo])
        assert existente.nome in atualizados
        assert "Perfil que só existe no site" in criados
        assert existente.palavras_incluir == ['"teste-sincronia"']
        assert s.query(PerfilBusca).filter_by(
            nome="Perfil que só existe no site").first() is not None
    finally:
        s.rollback()
        s.close()


def test_aplicar_nao_mexe_no_que_so_existe_localmente():
    """Perfil local ausente no site fica como está — apagar é decisão do dono."""
    s = Sessao()
    try:
        nomes_antes = {p.nome: p.ativo for p in s.query(PerfilBusca).all()}
        aplicar_perfis(s, [_perfil_remoto("Perfil inédito qualquer")])
        for nome, ativo in nomes_antes.items():
            p = s.query(PerfilBusca).filter_by(nome=nome).first()
            assert p is not None and p.ativo == ativo
    finally:
        s.rollback()
        s.close()


def test_aplicar_ignora_o_perfil_de_sistema_e_nome_vazio():
    s = Sessao()
    try:
        antes = s.query(PerfilBusca).count()
        atualizados, criados = aplicar_perfis(
            s, [_perfil_remoto(PERFIL_SISTEMA), _perfil_remoto("")])
        assert (atualizados, criados) == ([], [])
        assert s.query(PerfilBusca).count() == antes
    finally:
        s.rollback()
        s.close()


def test_aplicar_sem_mudanca_nao_marca_como_atualizado():
    s = Sessao()
    try:
        existente = s.query(PerfilBusca).first()
        igual = {c: getattr(existente, c) for c in CAMPOS}
        atualizados, criados = aplicar_perfis(s, [igual])
        assert (atualizados, criados) == ([], [])
    finally:
        s.rollback()
        s.close()
