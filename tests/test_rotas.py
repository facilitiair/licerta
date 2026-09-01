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
        # multiusuário: entra de verdade pela rota de login (e-mail em branco
        # funciona quando a senha bate com uma conta só)
        r = c.post("/login", data={"email": "", "senha": config.APP_SENHA},
                   follow_redirects=False)
        assert r.status_code == 303 and "sessao" in c.cookies,             "fixture não conseguiu logar — confira APP_SENHA/migração"
        yield c


ROTAS_GET = [
    "/login",
    "/api/saude",
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
    "/documentos",
    "/documentos/999999/arquivo",           # 404 sem 500
    "/fichas",
    "/minutas",
    "/pareceres",
    "/pareceres/999999",                    # 404 sem 500
    "/pareceres/999999/baixar",
    "/minutas/999999",                      # 404 sem 500
    "/minutas/999999/baixar",
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
    ("/licitacoes/999999/analisar", {"forcar": 0}),   # id inexistente -> 404
    ("/documentos/999999/salvar", {"nome": "x", "validade": "lixo"}),
    ("/documentos/999999/arquivar", {}),
    ("/licitacoes/999999/minuta", {}),                # 404 sem 500
    ("/licitacoes/999999/parecer", {}),               # 404 sem 500
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


# --------------------------------------- regressões apontadas pela auditoria
def test_senha_com_acento_funciona_no_hash():
    """Senha brasileira tem acento; o hash trabalha em bytes UTF-8."""
    from app.usuarios import conferir_senha, gerar_hash
    h = gerar_hash("licitações2024")
    assert conferir_senha("licitações2024", h)
    assert not conferir_senha("licitacoes2024", h)


def test_cookie_esquisito_nao_derruba_as_rotas():
    """Cookie corrompido tem de virar redirect para /login, nunca 500."""
    with TestClient(app) as anonimo:
        for lixo in ("1:2", "a:b:c", ":::", "1:99999999999999:x", "9" * 500):
            anonimo.cookies.set("sessao", lixo)
            r = anonimo.get("/", follow_redirects=False)
            assert r.status_code == 303, repr(lixo)
    # byte acentuado não passa pelo cliente de teste; confere na função
    from app.usuarios import usuario_do_token
    assert usuario_do_token("caf\xe9", b"s" * 32) is None


def test_segredos_nao_aparecem_no_html_da_tela_de_configuracoes(cliente):
    """type='password' esconde na tela, mas 'ver código-fonte' entregava a
    senha do painel, o token do Telegram e a senha do e-mail em texto puro."""
    from app.config import config
    html = cliente.get("/config").text
    for segredo in (config.APP_SENHA, config.TELEGRAM_BOT_TOKEN,
                    config.SMTP_PASSWORD):
        if segredo:
            assert segredo not in html, "segredo vazando no HTML"


def test_autocomplete_do_pncp_escapa_html(monkeypatch, cliente):
    """O nome do órgão vem cru da API do PNCP; '<' ali virava markup
    executado no navegador já autenticado."""
    from app.ingestao import pncp_busca
    monkeypatch.setattr(
        pncp_busca, "buscar_opcoes",
        lambda tipo, q: [{"id": "1", "nome": "<img src=x onerror=alert(1)>",
                          "cnpj": "d'Água"}])
    html = cliente.get("/api/pncp/opcoes?tipo=orgaos&q=teste").text
    assert "<img" not in html                # o markup não vira elemento
    assert "&lt;img" in html                 # vira texto escapado, visível
    assert "onclick" not in html             # dados em data-*, não em handler


def test_pagina_gigante_nao_estoura_o_sqlite(cliente):
    for rota in ("/licitacoes?pagina=99999999999999999999",
                 "/atas?pagina=99999999999999999999"):
        assert cliente.get(rota, follow_redirects=False).status_code < 500


def test_modalidade_nao_numerica_nao_da_500(cliente):
    r = cliente.post("/perfis/preview",
                     data={"nome": "x", "modalidades": "abc"},
                     follow_redirects=False)
    assert r.status_code < 500


def test_agenda_sobrevive_a_data_impossivel(cliente):
    """O Mural do TCE-PI já gravou '2026-13-45'; uma linha torta derrubava
    a agenda inteira, em toda visita, até alguém apagar o registro."""
    from app.db import Licitacao, PerfilBusca, PerfilMatch, Sessao
    s = Sessao()
    try:
        perfil = s.query(PerfilBusca).first()
        lic = Licitacao(numero_controle_pncp="TESTE-DATA-TORTA/9999",
                        objeto="teste", data_encerramento_proposta="9026-13-45",
                        uf="PI", fonte="tcepi", situacao="Divulgada")
        s.add(lic)
        s.commit()
        match = PerfilMatch(perfil_id=perfil.id, licitacao_id=lic.id)
        s.add(match)
        s.commit()
        assert cliente.get("/agenda").status_code == 200
    finally:
        s.query(PerfilMatch).filter_by(licitacao_id=lic.id).delete()
        s.query(Licitacao).filter_by(
            numero_controle_pncp="TESTE-DATA-TORTA/9999").delete()
        s.commit()
        s.close()


def test_horario_invalido_no_env_nao_impede_o_app_de_subir():
    """'06:99' salvo em /config virava minute=99 no agendador, que recusa o
    gatilho — e o app deixava de iniciar, com o valor ruim já no .env."""
    from apscheduler.triggers.cron import CronTrigger

    from app.config import _hora, config
    from app.main import _gatilho_coleta
    assert _hora("06:99", (6, 0)) == (6, 0)
    assert _hora("25:00", (7, 0)) == (7, 0)
    original = config.HORA_COLETA
    try:
        config.HORA_COLETA = _hora("06:99", (6, 0))
        CronTrigger(**_gatilho_coleta())      # não pode levantar
    finally:
        config.HORA_COLETA = original


def test_env_preserva_chaves_que_a_tela_nao_conhece(tmp_path, monkeypatch):
    """Salvar um horário apagava o APP_URL posto à mão, e todo alerta passava
    a mandar um link que não abre no celular."""
    from app import envcfg
    caminho = tmp_path / ".env"
    caminho.write_text("APP_URL=https://radar.exemplo.com\nAPP_SENHA=x\n",
                       encoding="utf-8")
    monkeypatch.setattr(envcfg, "CAMINHO_ENV", str(caminho))
    envcfg.salvar({"HORA_COLETA": "05:00"})
    conteudo = caminho.read_text(encoding="utf-8")
    assert "APP_URL=https://radar.exemplo.com" in conteudo
    assert "HORA_COLETA=05:00" in conteudo


def test_campo_de_segredo_em_branco_mantem_o_valor(tmp_path, monkeypatch):
    """A tela não devolve mais o segredo no HTML, então em branco tem de
    significar 'não mexi' — e não 'apague a senha'."""
    from app import envcfg
    from app.config import config
    caminho = tmp_path / ".env"
    caminho.write_text("", encoding="utf-8")
    monkeypatch.setattr(envcfg, "CAMINHO_ENV", str(caminho))
    monkeypatch.setattr(config, "APP_SENHA", "senha-secreta")
    envcfg.salvar({"APP_SENHA": "", "HORA_ALERTA": "08:00"})
    assert config.APP_SENHA == "senha-secreta"
    assert "APP_SENHA=senha-secreta" in caminho.read_text(encoding="utf-8")


def test_login_funciona_mesmo_sem_poder_gravar_o_segredo(monkeypatch):
    """Regressão: a chave de sessão é gravada num arquivo, e quando a pasta
    de dados não aceitava escrita o login inteiro dava 500 — o dono ficava
    trancado do lado de fora do próprio app, sem nenhuma pista."""
    import app.main as m
    from app.config import config
    monkeypatch.setattr(m, "CAMINHO_SEGREDO", "Z:/nao/existe/.segredo")
    with TestClient(m.app) as anonimo:
        r = anonimo.post("/login", data={"email": "",
                                         "senha": config.APP_SENHA},
                         follow_redirects=False)
        assert r.status_code == 303          # entrou mesmo assim
        assert "sessao" in r.cookies


def test_trocar_a_senha_derruba_as_sessoes_antigas():
    """O token assina a senha: cookie roubado morre quando a senha muda."""
    from app.usuarios import criar_token, gerar_hash, usuario_do_token

    class U:
        id = 999
        ativo = True
        senha_hash = gerar_hash("antiga")

    segredo = b"s" * 32
    token = criar_token(U(), segredo)
    import app.usuarios as mod
    original = mod.carregar_usuario
    u = U()
    mod.carregar_usuario = lambda uid: u if uid == 999 else original(uid)
    try:
        assert usuario_do_token(token, segredo) is u
        u.senha_hash = gerar_hash("nova")
        assert usuario_do_token(token, segredo) is None
    finally:
        mod.carregar_usuario = original


def test_instalacao_nova_nasce_sem_perfil_de_exemplo(monkeypatch, tmp_path):
    """O produto é genérico: cada empresa define o próprio ramo pela tela.
    Um perfil de exemplo de um setor específico pré-carregado só confunde."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app import seed
    from app.db import Base, PerfilBusca
    eng = create_engine(f"sqlite:///{tmp_path / 'instalacao_nova.db'}")
    Base.metadata.create_all(eng)
    Sess = sessionmaker(bind=eng)
    monkeypatch.setattr(seed, "Sessao", Sess)
    monkeypatch.setattr(seed, "baixar_municipios_ibge", lambda: [])
    seed.semear()
    s = Sess()
    try:
        assert s.query(PerfilBusca).count() == 0
    finally:
        s.close()
