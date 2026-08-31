"""Multiusuário: contas, isolamento entre pessoas e canais de aviso próprios."""
import pytest
from fastapi.testclient import TestClient

from app.config import config
from app.db import PerfilBusca, PushAssinatura, Sessao, Usuario
from app.main import app
from app.usuarios import gerar_hash

SENHA_COLEGA = "senha-do-colega-123"


@pytest.fixture(scope="module")
def colega():
    """Uma segunda conta real, removida ao final."""
    s = Sessao()
    u = Usuario(nome="Colega de Teste", email="colega@teste.local",
                senha_hash=gerar_hash(SENHA_COLEGA),
                email_alertas="colega@teste.local")
    s.add(u)
    s.commit()
    uid = u.id
    s.close()
    yield uid
    s = Sessao()
    s.query(PushAssinatura).filter_by(usuario_id=uid).delete()
    s.query(PerfilBusca).filter_by(usuario_id=uid).delete()
    alvo = s.get(Usuario, uid)
    if alvo:
        s.delete(alvo)
    s.commit()
    s.close()


@pytest.fixture()
def como_colega(colega):
    with TestClient(app) as c:
        r = c.post("/login", data={"email": "colega@teste.local",
                                   "senha": SENHA_COLEGA},
                   follow_redirects=False)
        assert r.status_code == 303
        yield c


@pytest.fixture()
def como_admin():
    with TestClient(app) as c:
        r = c.post("/login", data={"email": "", "senha": config.APP_SENHA},
                   follow_redirects=False)
        assert r.status_code == 303
        yield c


def test_com_usuarios_existentes_registro_fecha(como_admin):
    """/registrar só existe na instalação zerada — depois vira porta trancada."""
    with TestClient(app) as anonimo:
        r = anonimo.get("/registrar", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login"
        r = anonimo.post("/registrar", data={"nome": "x", "email": "x@x.co",
                                             "senha": "123456"},
                         follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login"


def test_login_com_email_errado_nao_entra():
    with TestClient(app) as anonimo:
        r = anonimo.post("/login",
                         data={"email": "colega@teste.local",
                               "senha": config.APP_SENHA},
                         follow_redirects=False)
        assert r.status_code == 200          # volta com erro, sem cookie
        assert "sessao" not in r.cookies


def test_colega_nao_ve_os_perfis_do_admin(como_colega):
    html = como_colega.get("/perfis").text
    assert "Ar-condicionado" not in html
    assert "Comece criando" in html          # convite da tela vazia


def test_colega_nao_edita_perfil_do_admin(como_colega):
    s = Sessao()
    alheio = (s.query(PerfilBusca)
              .filter(PerfilBusca.usuario_id != None)  # noqa: E711
              .filter(PerfilBusca.nome.like("Ar-condicionado%")).first())
    s.close()
    assert alheio is not None
    r = como_colega.get(f"/perfis/{alheio.id}", follow_redirects=False)
    assert r.status_code == 303              # devolvido à lista, sem o form
    r = como_colega.post(f"/perfis/{alheio.id}/excluir", follow_redirects=False)
    s = Sessao()
    assert s.get(PerfilBusca, alheio.id) is not None   # continua vivo
    s.close()


def test_perfil_criado_pelo_colega_e_so_dele(como_colega, colega):
    r = como_colega.post("/perfis/salvar", data={
        "nome": "Perfil do colega", "ativo": "on", "palavras_incluir": "obra",
        "frequencia": "diario"}, follow_redirects=False)
    assert r.status_code == 303
    s = Sessao()
    p = s.query(PerfilBusca).filter_by(nome="Perfil do colega").first()
    assert p is not None and p.usuario_id == colega
    s.close()
    assert "Perfil do colega" in como_colega.get("/perfis").text


def test_painel_e_funil_do_colega_nascem_vazios(como_colega):
    assert como_colega.get("/").status_code == 200
    assert como_colega.get("/funil").status_code == 200
    assert como_colega.get("/agenda").status_code == 200


def test_usuarios_e_config_sao_so_do_admin(como_colega, como_admin):
    r = como_colega.get("/usuarios", follow_redirects=False)
    assert r.status_code == 303
    r = como_colega.get("/config", follow_redirects=False)
    assert r.status_code == 303
    assert como_admin.get("/usuarios").status_code == 200
    assert como_admin.get("/config").status_code == 200


def test_conta_renderiza_e_salva_preferencias(como_colega):
    assert "Minha conta" in como_colega.get("/conta").text
    r = como_colega.post("/conta", data={
        "nome": "Colega de Teste", "email_alertas": "novo@teste.local",
        "receber_telegram": "on"}, follow_redirects=False)
    assert r.status_code == 303
    s = Sessao()
    u = s.query(Usuario).filter_by(email="colega@teste.local").first()
    assert u.email_alertas == "novo@teste.local"
    assert u.receber_telegram and not u.receber_email and not u.receber_push
    s.close()


def test_push_assinar_e_remover(como_colega, colega):
    assinatura = {"endpoint": "https://push.exemplo/abc123",
                  "keys": {"p256dh": "chaveP", "auth": "chaveA"}}
    r = como_colega.post("/api/push/assinar", json=assinatura)
    assert r.status_code == 200 and r.json()["ok"]
    s = Sessao()
    a = s.query(PushAssinatura).filter_by(usuario_id=colega).first()
    assert a is not None and a.endpoint == "https://push.exemplo/abc123"
    s.close()
    r = como_colega.post("/api/push/remover",
                         json={"endpoint": "https://push.exemplo/abc123"})
    assert r.json()["ok"]
    s = Sessao()
    assert s.query(PushAssinatura).filter_by(usuario_id=colega).count() == 0
    s.close()


def test_push_assinar_recusa_lixo(como_colega):
    r = como_colega.post("/api/push/assinar",
                         json={"endpoint": "javascript:alert(1)", "keys": {}})
    assert r.status_code == 400


def test_chave_publica_do_push_existe(como_colega):
    chave = como_colega.get("/api/push/chave").json()["chave"]
    assert len(chave) > 60


def test_despacho_usa_os_canais_do_dono(monkeypatch):
    """O alerta de um perfil sai pelos canais de QUEM criou o perfil."""
    from app.notificacoes import alerta

    class Dono:
        id = 1
        receber_telegram = True
        telegram_chat_id = "111222"
        receber_email = True
        email_alertas = "dono@empresa.com"
        receber_push = False

    class Perfil:
        nome = "Obras"
        usuario = Dono()

    chamadas = {}
    monkeypatch.setattr(alerta, "enviar_telegram",
                        lambda texto, chat_id=None:
                        chamadas.update({"tg": chat_id}) or True)
    monkeypatch.setattr(alerta, "enviar_email",
                        lambda texto, destino=None:
                        chamadas.update({"email": destino}) or True)
    ok_tg, ok_email, ok_push = alerta.despachar_canais(
        None, Perfil(), "texto", 3, False)
    assert (ok_tg, ok_email, ok_push) == (True, True, False)
    assert chamadas == {"tg": "111222", "email": "dono@empresa.com"}


def test_despacho_respeita_canal_desligado(monkeypatch):
    from app.notificacoes import alerta

    class Dono:
        id = 1
        receber_telegram = False
        telegram_chat_id = "111222"
        receber_email = False
        email_alertas = "dono@empresa.com"
        receber_push = False

    class Perfil:
        nome = "Obras"
        usuario = Dono()

    monkeypatch.setattr(alerta, "enviar_telegram",
                        lambda *a, **k: pytest.fail("telegram desligado"))
    monkeypatch.setattr(alerta, "enviar_email",
                        lambda *a, **k: pytest.fail("email desligado"))
    assert alerta.despachar_canais(None, Perfil(), "t", 1, False) == \
        (False, False, False)


def test_tela_inicial_guia_o_usuario_novo():
    """Quem acabou de chegar não pode ver zeros: vê os três primeiros passos,
    com o que já foi feito marcado."""
    s = Sessao()
    novato = Usuario(nome="Novato", email="novato@teste.local",
                     senha_hash=gerar_hash("novato-123"),
                     email_alertas="", receber_email=False)
    s.add(novato)
    s.commit()
    uid = novato.id
    s.close()
    try:
        with TestClient(app) as c:
            c.post("/login", data={"email": "novato@teste.local",
                                   "senha": "novato-123"},
                   follow_redirects=False)
            html = c.get("/").text
            assert "Bem-vindo" in html
            assert "Diga o que interessa" in html
            assert "Escolha como ser avisado" in html
            assert "Criar meu primeiro perfil" in html
    finally:
        s = Sessao()
        alvo = s.get(Usuario, uid)
        if alvo:
            s.delete(alvo)
        s.commit()
        s.close()


def test_tela_inicial_do_usuario_completo_nao_mostra_o_guia(como_admin):
    """Com perfil, canal e coleta feitos, o guia sai da frente."""
    html = como_admin.get("/").text
    assert "Diga o que interessa" not in html
