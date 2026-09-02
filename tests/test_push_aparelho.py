"""Avisos no aparelho com cara de app nativo (v0.31.0).

Um aviso por oportunidade, abrindo na página dela; título curto e texto
com prazo e valor; preferências da pessoa (assuntos, som, silêncio
noturno, prazo fixo na tela, detalhado ou resumo) respeitadas no envio.
"""
import json

import pytest
from fastapi.testclient import TestClient

from app.config import config
from app.db import PerfilBusca, PushAssinatura, Sessao, Usuario
from app.main import app
from app.notificacoes import alerta, push
from app.usuarios import gerar_hash

SENHA_COLEGA = "senha-do-colega-push"


@pytest.fixture(scope="module")
def admin():
    with TestClient(app) as c:
        r = c.post("/login", data={"email": "", "senha": config.APP_SENHA},
                   follow_redirects=False)
        assert r.status_code == 303
        yield c


@pytest.fixture(scope="module")
def colega():
    s = Sessao()
    u = Usuario(nome="Colega do Push", email="colega-push@teste.local",
                senha_hash=gerar_hash(SENHA_COLEGA))
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
        r = c.post("/login", data={"email": "colega-push@teste.local",
                                   "senha": SENHA_COLEGA},
                   follow_redirects=False)
        assert r.status_code == 303
        yield c


class _Lic:
    def __init__(self, id, objeto, municipio="Teresina", uf="PI",
                 valor=1_700_000.0, encerra="2099-09-04T09:00:00",
                 modalidade="PREGÃO ELETRÔNICO"):
        self.id = id
        self.objeto = objeto
        self.municipio_nome = municipio
        self.uf = uf
        self.valor_total_estimado = valor
        self.data_encerramento_proposta = encerra
        self.modalidade_nome = modalidade


class _Dono:
    id = 7
    receber_telegram = False
    telegram_chat_id = ""
    receber_email = False
    email_alertas = ""
    receber_push = True


class _Perfil:
    id = 3
    nome = "Ar-condicionado — PI"
    usuario = _Dono()


def _capturar(monkeypatch):
    """Substitui o envio real: guarda o que sairia para cada aparelho."""
    enviados = []

    def falso_enviar(sessao_db, usuario, titulo, corpo, url="/", tag=None,
                     urgente=False, acao="Abrir", assunto=None):
        if not push.quer_assunto(usuario, assunto):
            return 0
        enviados.append({"titulo": titulo, "corpo": corpo, "url": url,
                         "tag": tag, "urgente": urgente, "acao": acao,
                         "assunto": assunto})
        return 1
    monkeypatch.setattr(push, "enviar_push", falso_enviar)
    return enviados


def test_resumo_push_fala_a_lingua_da_tela():
    lic = _Lic(1, "CONTRATAÇÃO DE EMPRESA PARA MANUTENÇÃO DE AR-CONDICIONADO "
                  "NAS UNIDADES BÁSICAS DE SAÚDE DO MUNICÍPIO (SRP)")
    titulo, corpo = alerta.resumo_push(lic)
    assert titulo == "Nova oportunidade · Teresina/PI"
    primeira, segunda = corpo.split("\n")
    assert primeira.startswith("Contratação de empresa para manutenção")
    assert "SRP" in primeira                       # sigla preservada
    assert "Encerra 04/09/2099 09:00" in segunda
    assert "R$ 1,7 mi" in segunda
    assert "Pregão eletrônico" in segunda
    assert "PREGÃO" not in corpo                    # nada gritado no aparelho


def test_prazo_fechando_muda_o_titulo():
    titulo, _ = alerta.resumo_push(_Lic(1, "Obra"), urgente=True)
    assert titulo.startswith("Prazo fechando")


def test_um_aviso_por_oportunidade_abrindo_na_pagina_dela(monkeypatch):
    enviados = _capturar(monkeypatch)
    lics = [_Lic(10, "Obra A"), _Lic(11, "Obra B")]
    ok = alerta.despachar_canais(None, _Perfil(), "texto", 2, False,
                                 host="https://www.licerta.com.br",
                                 itens=lics)
    assert ok == (False, False, True)
    assert [e["url"] for e in enviados] == [
        "https://www.licerta.com.br/licitacoes/10",
        "https://www.licerta.com.br/licitacoes/11"]
    assert [e["tag"] for e in enviados] == ["oportunidade-10", "oportunidade-11"]
    assert all(e["assunto"] == "oportunidades" for e in enviados)
    assert all(e["acao"] == "Ver oportunidade" for e in enviados)


def test_excedente_vira_um_resumo_so(monkeypatch):
    enviados = _capturar(monkeypatch)
    lics = [_Lic(i, f"Obra {i}") for i in range(1, 9)]      # 8 > LIMITE_PUSH
    alerta.despachar_canais(None, _Perfil(), "t", 8, True, host="https://x",
                            itens=lics)
    assert len(enviados) == alerta.LIMITE_PUSH + 1
    resumo = enviados[-1]
    assert resumo["titulo"] == "E mais 3 em Ar-condicionado — PI"
    assert resumo["url"] == "https://x/licitacoes?perfil_id=3"
    assert resumo["assunto"] == "prazos"
    assert all(e["urgente"] for e in enviados[:-1])


def test_quem_prefere_resumo_recebe_um_aviso_com_a_contagem(monkeypatch):
    enviados = _capturar(monkeypatch)

    class Dono(_Dono):
        push_detalhado = False

    class Perfil(_Perfil):
        usuario = Dono()
    alerta.despachar_canais(None, Perfil(), "t", 4, False, host="https://x",
                            itens=[_Lic(i, "o") for i in range(4)])
    assert len(enviados) == 1
    assert enviados[0]["titulo"] == "Novas oportunidades · Ar-condicionado — PI"
    assert "4 oportunidades novas" in enviados[0]["corpo"]
    assert enviados[0]["url"] == "https://x/licitacoes?perfil_id=3"


def test_chamada_antiga_sem_itens_continua_valendo(monkeypatch):
    enviados = _capturar(monkeypatch)
    alerta.despachar_canais(None, _Perfil(), "t", 1, False, host="https://x")
    assert len(enviados) == 1 and "1 oportunidade nova" in enviados[0]["corpo"]


def test_assunto_desligado_nao_sai_e_nao_conta_como_entregue():
    class Dono(_Dono):
        push_assuntos = "prazos,dossie"
    assert not push.quer_assunto(Dono(), "oportunidades")
    assert push.quer_assunto(Dono(), "prazos")
    assert push.quer_assunto(Dono(), None)          # teste de Minha conta


def test_preferencias_tem_padrao_para_objetos_sem_as_colunas():
    prefs = push.preferencias(_Dono())
    assert prefs["som"] and prefs["detalhado"] and prefs["fixar_prazo"]
    assert not prefs["noturno"]
    assert prefs["assuntos"] == {c for c, _ in push.ASSUNTOS}


@pytest.mark.parametrize("de,ate,hora,esperado", [
    (22, 7, 23, True), (22, 7, 3, True), (22, 7, 7, False), (22, 7, 12, False),
    (13, 14, 13, True), (13, 14, 14, False), (8, 8, 8, False),
])
def test_silencio_noturno_atravessa_a_meia_noite(de, ate, hora, esperado):
    prefs = {"noturno": True, "noturno_de": de, "noturno_ate": ate}
    assert push.em_silencio_noturno(prefs, hora=hora) is esperado
    assert push.em_silencio_noturno(dict(prefs, noturno=False), hora=hora) is False


def test_aviso_leva_tag_hora_e_marcas_de_som_e_fixacao():
    aviso = push.montar_aviso("T" * 100, "c" * 500, url="/x", tag="a",
                              urgente=True, silencioso=True)
    assert len(aviso["titulo"]) <= push.LIMITE_TITULO
    assert len(aviso["corpo"]) <= push.LIMITE_CORPO
    assert aviso["titulo"].endswith("…") and aviso["corpo"].endswith("…")
    assert aviso["tag"] == "a" and aviso["quando"] > 0
    assert aviso["silencioso"] is True and aviso["fixar"] is True
    assert push.montar_aviso("t", "c")["fixar"] is False
    json.dumps(aviso)                                # vai como JSON ao aparelho


def test_envio_real_respeita_som_silencio_e_prazo_fixo(monkeypatch, tmp_path):
    """Com a rede substituída: o pacote que sai leva as escolhas da pessoa."""
    pacotes = []

    class Assinatura:
        endpoint = "https://push.exemplo/1"
        p256dh = "p"
        auth = "a"

    class Consulta:
        def filter_by(self, **k):
            return self

        def all(self):
            return [Assinatura()]

    class Sessao:
        def query(self, *a):
            return Consulta()

        def commit(self):
            pass

    monkeypatch.setattr(push, "webpush",
                        lambda **kw: pacotes.append(kw) or "ok")
    monkeypatch.setattr(push, "CAMINHO_CHAVE", str(tmp_path / "vapid.pem"))
    push._vapid = None

    class Dono(_Dono):
        push_som = False
        push_fixar_prazo = False
    assert push.enviar_push(Sessao(), Dono(), "t", "c", urgente=True) == 1
    dados = json.loads(pacotes[-1]["data"])
    assert dados["silencioso"] is True and dados["fixar"] is False
    assert pacotes[-1]["headers"] == {"Urgency": "high"}
    assert pacotes[-1]["ttl"] == 24 * 3600

    class Ligado(_Dono):
        push_assuntos = "dossie"
    assert push.enviar_push(Sessao(), Ligado(), "t", "c",
                            assunto="oportunidades") == 0
    assert len(pacotes) == 1                          # nada saiu


def test_conta_grava_as_preferencias_do_aparelho(admin):
    """Grava e, ao fim, devolve o admin ao estado em que estava: os testes
    rodam no banco local de verdade."""
    from app.db import Sessao, Usuario
    campos = ("nome", "email_alertas", "receber_telegram", "receber_email",
              "receber_push", "push_som", "push_detalhado", "push_fixar_prazo",
              "push_noturno", "push_noturno_de", "push_noturno_ate",
              "push_assuntos")
    s = Sessao()
    try:
        adm = s.query(Usuario).filter_by(papel="admin").first()
        antes = {c: getattr(adm, c) for c in campos}
    finally:
        s.close()
    try:
        r = admin.post("/conta", data={
            "nome": antes["nome"], "email_alertas": antes["email_alertas"],
            "receber_push": "on", "push_formato": "resumo",
            "push_fixar_prazo": "on", "push_noturno": "on",
            "push_noturno_de": "21", "push_noturno_ate": "6",
            "assunto_prazos": "on", "assunto_dossie": "on",
        }, follow_redirects=False)
        assert r.status_code == 303
        s = Sessao()
        try:
            u = s.query(Usuario).filter_by(papel="admin").first()
            assert u.push_som is False                 # caixa desmarcada
            assert u.push_detalhado is False
            assert u.push_fixar_prazo is True
            assert u.push_noturno is True
            assert (u.push_noturno_de, u.push_noturno_ate) == (21, 6)
            assert u.push_assuntos == "prazos,dossie"
        finally:
            s.close()
        pagina = admin.get("/conta").text
        assert "Instalar o app no aparelho" in pagina
        assert "Sem som das" in pagina
    finally:
        s = Sessao()
        try:
            adm = s.query(Usuario).filter_by(papel="admin").first()
            for c, v in antes.items():
                setattr(adm, c, v)
            s.commit()
        finally:
            s.close()


def test_hora_invalida_cai_no_padrao():
    from app.main import _hora_valida
    assert _hora_valida("25", 22) == 22
    assert _hora_valida("abc", 7) == 7
    assert _hora_valida("0", 7) == 0


def test_assinar_com_endereco_anterior_apaga_o_antigo(como_colega, colega):
    from app.db import PushAssinatura, Sessao
    chaves = {"p256dh": "x", "auth": "y"}
    como_colega.post("/api/push/assinar",
                     json={"endpoint": "https://push.exemplo/velho", "keys": chaves})
    r = como_colega.post("/api/push/assinar",
                         json={"endpoint": "https://push.exemplo/novo",
                               "keys": chaves,
                               "anterior": "https://push.exemplo/velho"})
    assert r.status_code == 200
    s = Sessao()
    try:
        pontas = [a.endpoint for a in s.query(PushAssinatura).all()]
    finally:
        s.close()
    assert "https://push.exemplo/velho" not in pontas
    assert "https://push.exemplo/novo" in pontas


def test_service_worker_e_manifesto_tem_o_que_o_aparelho_precisa(admin):
    sw = admin.get("/sw.js").text
    for trecho in ("badge-96.png", "renotify", "requireInteraction", "silent",
                   "pushsubscriptionchange", "actions", "timestamp"):
        assert trecho in sw
    manifesto = admin.get("/manifest.json").json()
    assert manifesto["display"] == "standalone"
    assert any(i.get("purpose") == "maskable" for i in manifesto["icons"])
    for arquivo in ("badge-96.png", "icone-maskable-512.png"):
        assert admin.get(f"/static/{arquivo}").status_code == 200


def test_assinatura_vapid_e_aceita_pela_pywebpush(monkeypatch, tmp_path):
    """Regressão: o PEM como string era rejeitado pela pywebpush 2.x e todo
    aviso morria no servidor ('Nenhum aparelho ativado' com 4 aparelhos).
    Com curl=True a biblioteca assina de verdade e não toca a rede."""
    import pywebpush
    monkeypatch.setattr(push, "CAMINHO_CHAVE", str(tmp_path / "vapid.pem"))
    push._vapid = None
    monkeypatch.setattr(config, "EMAIL_DESTINO", "x@y")   # inválido p/ VAPID
    chamadas = []

    def real_sem_rede(**kw):
        chamadas.append(kw)
        return pywebpush.webpush(curl=True, **kw)
    monkeypatch.setattr(push, "webpush", real_sem_rede)

    # Chave do aparelho de verdade (ponto válido da curva P-256)
    import base64
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    ponto = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)

    class Assinatura:
        endpoint = "https://fcm.googleapis.com/fcm/send/abc"
        p256dh = base64.urlsafe_b64encode(ponto).decode().rstrip("=")
        auth = "tBHItJI5svbpez7KI4CCXg"

    class Consulta:
        def filter_by(self, **k):
            return self

        def all(self):
            return [Assinatura()]

    class Sessao:
        def query(self, *a):
            return Consulta()

        def commit(self):
            pass

    assert push.enviar_push(Sessao(), _Dono(), "t", "c") == 1
    assert chamadas[0]["vapid_claims"]["sub"] == f"mailto:{push.CONTATO_PADRAO}"
    assert push._claims("https://x.y/z")["sub"] == f"mailto:{push.CONTATO_PADRAO}"
    monkeypatch.setattr(config, "EMAIL_DESTINO", "dono@empresa.com.br")
    assert push._claims("https://x.y/z")["sub"] == "mailto:dono@empresa.com.br"


def test_chave_vapid_corrompida_e_regravada_e_fica_estavel(monkeypatch, tmp_path):
    """Produção: PEM truncado pelo disco cheio → chave nova a cada reinício
    → 403 em todo aparelho. Agora o arquivo ruim é substituído e a chave
    seguinte lida do disco é a mesma."""
    caminho = tmp_path / "vapid_privada.pem"
    caminho.write_text("-----BEGIN PRIVATE KEY-----\nMIGHAgEAMBMG\n",
                       encoding="utf-8")                      # truncado
    monkeypatch.setattr(push, "CAMINHO_CHAVE", str(caminho))
    push._vapid = None
    publica = push.chave_publica()
    assert len(publica) > 60
    push._vapid = None                                        # "reinício"
    assert push.chave_publica() == publica
    assert "BEGIN PRIVATE KEY" in caminho.read_text(encoding="utf-8")
    assert len(caminho.read_text(encoding="utf-8")) > 100


def test_aparelho_com_chave_antiga_sai_da_lista(monkeypatch, tmp_path):
    from pywebpush import WebPushException
    monkeypatch.setattr(push, "CAMINHO_CHAVE", str(tmp_path / "v.pem"))
    push._vapid = None
    apagados = []

    class Resposta:
        status_code = 403

    class Assinatura:
        endpoint = "https://fcm.googleapis.com/fcm/send/velho"
        p256dh = "p"
        auth = "a"

    class Consulta:
        def filter_by(self, **k):
            return self

        def all(self):
            return [Assinatura()]

    class Sessao:
        def query(self, *a):
            return Consulta()

        def delete(self, obj):
            apagados.append(obj.endpoint)

        def commit(self):
            pass

    def recusa(**kw):
        raise WebPushException("Push failed: 403 Forbidden", response=Resposta())
    monkeypatch.setattr(push, "webpush", recusa)
    assert push.enviar_push(Sessao(), _Dono(), "t", "c") == 0
    assert apagados == ["https://fcm.googleapis.com/fcm/send/velho"]


def test_toda_pagina_refaz_a_assinatura_quando_a_chave_muda(admin):
    html = admin.get("/").text
    assert "applicationServerKey" in html and "anterior" in html
    assert "/api/push/chave" in html
