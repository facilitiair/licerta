"""Auditoria de rotas: toda tela precisa responder sem erro 500 —
inclusive com parâmetros inválidos, ids inexistentes e texto onde
se espera número. Roda contra o banco local real (só leituras e
escritas inofensivas)."""
import hashlib
import hmac

import pytest
from fastapi.testclient import TestClient

from app.config import config
from app.main import app


@pytest.fixture(scope="module")
def cliente():
    with TestClient(app) as c:
        token = hmac.new(b"radar-licitacoes", config.APP_SENHA.encode(),
                         hashlib.sha256).hexdigest()
        c.cookies.set("sessao", token)
        yield c


ROTAS_GET = [
    "/login",
    "/",
    "/funil",
    "/agenda",
    "/logs",
    "/config",
    "/perfis",
    "/perfis/novo",
    "/perfis/novo?q=poço artesiano&ufs=PI&ufs=MA&modalidades=6",
    "/perfis/999999",                       # id inexistente -> redirect
    "/licitacoes",
    "/licitacoes?uf=MA",
    "/licitacoes?uf=XX",                    # UF inválida -> lista vazia
    "/licitacoes?modalidade=abc",           # número inválido -> ignorado
    "/licitacoes?perfil_id=abc",
    "/licitacoes?pagina=0",
    "/licitacoes?pagina=-5",
    "/licitacoes?q=climatização çãé",       # acentos na busca
    "/licitacoes?data_ini=lixo&data_fim=lixo",
    "/licitacoes?status=novo&ordenar=valor_asc",
    "/licitacoes?ordenar=inexistente",      # ordenação inválida -> padrão
    "/licitacoes/999999/detalhe",           # 404 sem 500
    "/licitacoes/exportar?formato=csv&modalidade=abc",
    "/licitacoes/exportar?formato=xlsx",
    "/atas",
    "/atas?q=ar condicionado&adesao=1&pagina=999",
    "/atas?pagina=0",
    "/arquivos/999999",                     # 404 sem 500
    "/api/municipios?uf=PI&q=ter",
    "/api/municipios?q=a",                  # curto demais -> vazio
    "/api/pncp/opcoes?tipo=invalido&q=teste",
    "/pesquisar",                           # sem consulta -> não chama a API
]


@pytest.mark.parametrize("rota", ROTAS_GET)
def test_rota_nao_da_erro_500(cliente, rota):
    resposta = cliente.get(rota, follow_redirects=False)
    assert resposta.status_code < 500, f"{rota} -> {resposta.status_code}"


ROTAS_POST = [
    ("/matches/999999", {"status": "novo"}),          # 404 sem 500
    ("/funil/mover/999999/novo", {}),                 # id inexistente
    ("/funil/mover/1/status_invalido", {}),           # status inválido
    ("/pesquisar/salvar", {}),                        # sem identificador -> 400
    ("/perfis/999999/toggle", {}),
    ("/perfis/999999/excluir", {}),
    ("/perfis/999999/enviar", {}),                    # id inexistente: não envia
    ("/perfis/preview", {"nome": "x", "valor_min": "abc",  # texto no número
                         "palavras_incluir": "teste"}),
    ("/perfis/preview", {"nome": "x", "frequencia": "quinzenal",  # inexistente
                         "dia_semana": "99", "dia_mes": "0",
                         "mes_ano": "abc", "hora_envio": "25:99"}),
]


@pytest.mark.parametrize("rota,dados", ROTAS_POST)
def test_post_nao_da_erro_500(cliente, rota, dados):
    resposta = cliente.post(rota, data=dados, follow_redirects=False)
    assert resposta.status_code < 500, f"{rota} -> {resposta.status_code}"


def test_sem_login_redireciona():
    with TestClient(app) as anonimo:
        r = anonimo.get("/licitacoes", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login"


def test_login_senha_errada_nao_entra():
    with TestClient(app) as anonimo:
        r = anonimo.post("/login", data={"senha": "senha-errada"},
                         follow_redirects=False)
        assert r.status_code == 200          # volta ao formulário com erro
        assert "sessao" not in r.cookies


def test_gatilho_da_coleta_respeita_o_intervalo():
    """A coleta repete ao longo do dia; 24 volta à coleta única."""
    from app.config import config
    from app.main import _gatilho_coleta
    original = config.HORAS_ENTRE_COLETAS
    try:
        config.HORAS_ENTRE_COLETAS = 3
        assert _gatilho_coleta()["hour"] == "0,3,6,9,12,15,18,21"
        config.HORAS_ENTRE_COLETAS = 24
        assert _gatilho_coleta()["hour"] == str(config.HORA_COLETA[0])
    finally:
        config.HORAS_ENTRE_COLETAS = original
