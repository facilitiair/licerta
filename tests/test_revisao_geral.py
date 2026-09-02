"""Regressões da revisão geral de 02/09/2026 (um teste por defeito corrigido).

Cada teste aqui nasceu de um bug real encontrado na varredura do código:
vazamento de triagem entre contas, 500 ao expandir a lista filtrada por
perfil, .env corrompido por senha com aspas, alerta 'fecha hoje' para
edital com semanas de prazo, checklist casando 'iss' em 'emissão' etc.
"""
import json
from datetime import datetime, timedelta

import pytest
import requests
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import _fuso_valido, _inteiro, config
from app.db import (Base, Licitacao, Minuta, Parecer, PerfilBusca,
                    PerfilMatch, Sessao, Usuario)
from app.main import app


# ------------------------------------------------------------- utilidades
@pytest.fixture()
def sessao_memoria():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


@pytest.fixture(scope="module")
def admin():
    with TestClient(app) as c:
        r = c.post("/login", data={"email": "", "senha": config.APP_SENHA},
                   follow_redirects=False)
        assert r.status_code == 303
        yield c


# ---------------------------------------------------- .env e configuração
def test_env_sobrevive_a_senha_com_aspas_cerquilha_e_cifrao(tmp_path,
                                                            monkeypatch):
    """Valor cru no .env: aspa invalidava a linha, ' #' cortava o resto e
    ${x} sumia por interpolação — só no próximo reinício, em silêncio."""
    from app import envcfg
    caminho = tmp_path / ".env"
    caminho.write_text("", encoding="utf-8")
    monkeypatch.setattr(envcfg, "CAMINHO_ENV", str(caminho))
    esquisita = 'ab"c\'d #e ${f} g\\h'
    envcfg.salvar({"SMTP_PASSWORD": esquisita, "SMTP_HOST": "smtp.x"})
    lido = dotenv_values(str(caminho), interpolate=False)
    assert lido["SMTP_PASSWORD"] == esquisita
    assert lido["SMTP_HOST"] == "smtp.x"
    assert not (tmp_path / ".env.tmp").exists()     # troca atômica concluída


def test_porta_e_janela_invalidas_nao_derrubam_o_boot():
    """'587a' gravado pela tela virava ValueError na importação do config."""
    assert _inteiro("587a", 587, 1, 65535) == 587
    assert _inteiro("99999", 587, 1, 65535) == 65535
    assert _fuso_valido("Brasil", "America/Fortaleza") == "America/Fortaleza"
    assert _fuso_valido("America/Sao_Paulo", "x") == "America/Sao_Paulo"


def test_salvar_grava_numeros_ja_validados(tmp_path, monkeypatch):
    from app import envcfg
    caminho = tmp_path / ".env"
    caminho.write_text("", encoding="utf-8")
    monkeypatch.setattr(envcfg, "CAMINHO_ENV", str(caminho))
    envcfg.salvar({"SMTP_PORT": "587a", "TZ": "Brasil",
                   "DIAS_JANELA_FUTURA": "abc"})
    lido = dotenv_values(str(caminho), interpolate=False)
    assert lido["SMTP_PORT"] == "587"
    assert lido["DIAS_JANELA_FUTURA"] == "90"
    assert lido["TZ"] != "Brasil"


def test_cookie_com_caractere_estranho_e_so_sessao_invalida():
    from app.usuarios import usuario_do_token
    assert usuario_do_token("1:9999999999:é-não-ascii", b"x" * 32) is None


# ------------------------------------------------- isolamento entre contas
def test_lista_com_perfil_de_outro_usuario_nao_vaza(sessao_memoria):
    """/licitacoes?perfil_id=<de outro> e ?status=... sem perfil juntavam a
    triagem de TODAS as contas (AGENTS.md regra 6)."""
    from app.main import _consulta_licitacoes
    s = sessao_memoria
    a = Usuario(nome="A", email="a@x", senha_hash="h")
    b = Usuario(nome="B", email="b@x", senha_hash="h")
    s.add_all([a, b])
    s.flush()
    perfil_a = PerfilBusca(nome="PA", usuario_id=a.id)
    s.add(perfil_a)
    s.flush()
    lic = Licitacao(numero_controle_pncp="n-1-1/2026", objeto="obra",
                    data_encerramento_proposta="2026-12-01T09:00:00")
    s.add(lic)
    s.flush()
    s.add(PerfilMatch(perfil_id=perfil_a.id, licitacao_id=lic.id,
                      status="vou_participar"))
    s.commit()
    # dono vê
    assert _consulta_licitacoes(
        s, {"perfil_id": str(perfil_a.id)}, a.id).count() == 1
    assert _consulta_licitacoes(
        s, {"status": "vou_participar"}, a.id).count() == 1
    # colega não vê a triagem alheia (perfil alheio cai para "todos",
    # que com status ainda filtra pelos casamentos DELE)
    assert _consulta_licitacoes(
        s, {"perfil_id": str(perfil_a.id), "status": "vou_participar"},
        b.id).count() == 0
    assert _consulta_licitacoes(
        s, {"status": "vou_participar"}, b.id).count() == 0


def test_exportar_perfis_de_nao_admin_so_devolve_os_dele(sessao_memoria):
    from app import sincronizar
    s = sessao_memoria
    a = Usuario(nome="A", email="a@x", senha_hash="h")
    b = Usuario(nome="B", email="b@x", senha_hash="h")
    s.add_all([a, b])
    s.flush()
    s.add_all([PerfilBusca(nome="de A", usuario_id=a.id),
               PerfilBusca(nome="de B", usuario_id=b.id)])
    s.commit()
    assert {p["nome"] for p in sincronizar.exportar_perfis(s)} == \
        {"de A", "de B"}
    assert [p["nome"] for p in sincronizar.exportar_perfis(
        s, usuario_id=b.id)] == ["de B"]


def test_enviar_agora_de_perfil_alheio_nao_dispara(admin):
    """POST /perfis/{id}/enviar sem conferir o dono disparava o alerta de
    outra conta e queimava os matches dela como notificados."""
    r = admin.post("/perfis/999999/enviar", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/perfis"


# ----------------------------------------------------------- rotas (500s)
def test_detalhe_filtrado_por_perfil_nao_da_500(admin):
    """filter_by(perfil_id=...) depois do join apontava para PerfilBusca:
    expandir qualquer linha da lista filtrada por perfil dava 500."""
    s = Sessao()
    try:
        lic_id = s.query(Licitacao.id).first()
        perfil_id = s.query(PerfilBusca.id).first()
    finally:
        s.close()
    if not (lic_id and perfil_id):
        pytest.skip("banco local sem licitação/perfil")
    r = admin.get(f"/licitacoes/{lic_id[0]}/detalhe?perfil_id={perfil_id[0]}")
    assert r.status_code == 200


def test_exportar_com_numero_gigante_nao_da_500(admin):
    r = admin.get("/licitacoes/exportar?formato=csv"
                  "&modalidade=99999999999999999999&perfil_id=1" + "0" * 30)
    assert r.status_code == 200


def test_push_com_corpo_que_nao_e_json_devolve_400(admin):
    r = admin.post("/api/push/assinar", content=b"nao e json",
                   headers={"Content-Type": "application/json"})
    assert r.status_code == 400
    r = admin.post("/api/push/remover", content=b"[1,2]",
                   headers={"Content-Type": "application/json"})
    assert r.status_code == 400


def test_desmarcar_favorito_pega(admin):
    """Checkbox desmarcado não viaja no formulário: sem o marcador, o
    favorito nunca era desligado (a tela dizia 'salvo')."""
    s = Sessao()
    try:
        m = (s.query(PerfilMatch).join(PerfilBusca)
             .filter(PerfilBusca.usuario_id == s.query(Usuario.id)
                     .filter_by(papel="admin").order_by(Usuario.id)
                     .scalar()).first())
        if not m:
            pytest.skip("banco local sem casamento do admin")
        mid, favorito_antes, status_antes = m.id, m.favorito, m.status
    finally:
        s.close()
    try:
        r = admin.post(f"/matches/{mid}", data={"status": status_antes,
                                                "favorito_enviado": "1",
                                                "favorito": "on"})
        assert r.status_code == 200
        r = admin.post(f"/matches/{mid}", data={"status": status_antes,
                                                "favorito_enviado": "1"})
        assert r.status_code == 200
        s = Sessao()
        try:
            assert s.get(PerfilMatch, mid).favorito is False
        finally:
            s.close()
    finally:
        s = Sessao()
        try:
            s.get(PerfilMatch, mid).favorito = favorito_antes
            s.commit()
        finally:
            s.close()


# ------------------------------------------------------------- painel
def test_disputa_que_fecha_hoje_e_a_mais_urgente():
    """`_dias_ate(...) or 99` transformava 0 (fecha hoje) em 99 e a
    disputa mais urgente sumia do cartão vermelho do painel."""
    from app.main import _dias_ate
    from app.config import agora
    hoje = agora().strftime("%Y-%m-%dT23:00:00")
    assert _dias_ate(hoje) == 0
    assert _dias_ate("lixo") is None


# ----------------------------------------------------------- coleta / radar
def test_get_do_pncp_repete_em_502(monkeypatch):
    from app.ingestao import pncp
    monkeypatch.setattr(pncp.time, "sleep", lambda *_: None)
    respostas = iter([502, 503, 200])

    class Resp:
        def __init__(self, codigo):
            self.status_code, self.reason = codigo, "x"

    class SessaoFake:
        def get(self, *_, **__):
            return Resp(next(respostas))
    resp = pncp._get(SessaoFake(), "u", {})
    assert resp.status_code == 200


def test_combinacoes_sao_por_perfil_e_sem_redundancia():
    from app.radar.coleta import _combinacoes

    class P:
        def __init__(self, ufs, modalidades):
            self.ufs, self.modalidades = ufs, modalidades
    combos = _combinacoes([P([], [6, 12]), P(["PI"], [6, 8])])
    assert (None, 6) in combos and (None, 12) in combos
    assert ("PI", 6) not in combos          # coberto pela nacional
    assert ("PI", 8) in combos
    assert (None, 8) not in combos          # ninguém pediu Brasil × 8
    # com "PI" entre as UFs, o PI é varrido em todas as modalidades
    assert ("PI", 4) in combos


def test_mural_sem_contador_de_linhas_e_erro_e_nao_zero(monkeypatch):
    from app.ingestao import tcepi

    class RespFake:
        text = 'javax.faces.ViewState" value="abc"'

        def raise_for_status(self):
            pass

    class SessaoFake:
        def get(self, *_, **__):
            return RespFake()
    monkeypatch.setattr(tcepi.requests, "Session", SessaoFake)
    monkeypatch.setattr(tcepi, "_post_ajax", lambda *_: "<xml sem rowCount>")
    monkeypatch.setattr(tcepi, "RE_VIEWSTATE", tcepi.re.compile(
        r'ViewState" value="([^"]+)"'))
    with pytest.raises(RuntimeError):
        list(tcepi.coletar_mural())


def test_data_com_e_sem_segundos_nao_e_alteracao():
    """A busca ao vivo manda '2026-09-16T08:59' e a coleta
    '2026-09-16T08:59:00': salvar da pesquisa gerava aviso de mudança."""
    from app.radar.alteracoes import detectar

    class L:
        data_encerramento_proposta = "2026-09-16T08:59:00"
        situacao = None
    assert detectar(L(), {"data_encerramento_proposta": "2026-09-16T08:59"}) \
        == []
    assert detectar(L(), {"data_encerramento_proposta": "2026-09-17T08:59"})


def test_faxina_preserva_licitacao_com_parecer(sessao_memoria):
    """Só a minuta segurava a linha; o parecer (dólares gastos) não —
    a licitação sumia e /pareceres caía para todo mundo."""
    from datetime import date
    from app.radar import limpeza
    s = sessao_memoria
    com_parecer = Licitacao(numero_controle_pncp="p", objeto="x",
                            data_encerramento_proposta="2026-07-01T09:00:00")
    solta = Licitacao(numero_controle_pncp="s", objeto="x",
                      data_encerramento_proposta="2026-07-01T09:00:00")
    s.add_all([com_parecer, solta])
    s.flush()
    s.add(Parecer(licitacao_id=com_parecer.id, texto="p"))
    s.commit()
    limpeza.limpar(s, hoje=date(2026, 8, 31), vacuum=False)
    vivos = {l.numero_controle_pncp for l in s.query(Licitacao)}
    assert vivos == {"p"}


def test_trabalho_humano_inclui_minuta_e_parecer(sessao_memoria):
    from app.radar.limpeza import tem_trabalho_humano
    s = sessao_memoria
    lic = Licitacao(numero_controle_pncp="m", objeto="x")
    s.add(lic)
    s.flush()
    assert not tem_trabalho_humano(s, lic)
    s.add(Minuta(licitacao_id=lic.id, tipo="impugnacao", texto="m"))
    s.commit()
    assert tem_trabalho_humano(s, lic)


# ------------------------------------------------------------------ alertas
def test_urgencia_tem_teto_de_24h_em_perfil_mensal():
    """Perfil mensal: 'antes do próximo alerta' abrangia o mês inteiro e
    cada coleta disparava 'fecha hoje' para edital com semanas de prazo."""
    from app.notificacoes.alerta import urgentes
    from tests.test_alertas import LicFake, MatchFake, PerfilFake
    agora = datetime(2026, 8, 2, 9, 0)
    perfil = PerfilFake(frequencia="mensal", dia_mes=1,
                        ultimo_envio=datetime(2026, 8, 1, 7, 0))
    em_tres_semanas = MatchFake(LicFake("2026-08-25T17:00:00"))
    hoje_a_tarde = MatchFake(LicFake("2026-08-02T17:00:00"))
    achados = urgentes(perfil, [em_tres_semanas, hoje_a_tarde], agora)
    assert achados == [hoje_a_tarde]


def test_alerta_urgente_so_leva_as_urgentes(monkeypatch):
    """Ordenado por valor, a urgente ficava fora dos 10 da mensagem e saíam
    10 não urgentes como 'fecha hoje' — de novo a cada 10 minutos."""
    from app.notificacoes import alerta
    from tests.test_alertas import (MatchFake, PerfilFake, SessaoFake,
                                    _lic_completa)
    agora = datetime(2026, 8, 31, 9, 0)
    perfil = PerfilFake(ordenacao="valor_desc", situacoes=["Divulgada"],
                        ultimo_envio=datetime(2026, 8, 31, 7, 0))
    urgente = MatchFake(_lic_completa("2026-08-31T17:00:00"))
    urgente.licitacao.valor_total_estimado = 1.0
    folgadas = []
    for i in range(12):
        m = MatchFake(_lic_completa("2026-10-01T09:00:00"))
        m.licitacao.valor_total_estimado = 1_000_000.0 + i
        folgadas.append(m)
    enviados = {}

    def despachar(sessao_db, p, texto, quantidade, urg, host=None,
                  itens=None):
        enviados["texto"], enviados["qtd"] = texto, quantidade
        return True, False, False
    monkeypatch.setattr(alerta, "despachar_canais", despachar)
    monkeypatch.setattr(alerta, "_link_download_edital", lambda *a, **k: "")
    sessao = SessaoFake(folgadas + [urgente])
    ok, qtd = alerta.enviar_alerta_perfil(sessao, perfil, agora=agora,
                                          urgente=True)
    assert ok and qtd == 1
    assert urgente.notificado and not folgadas[0].notificado
    assert "PRAZO FECHANDO" in enviados["texto"]


# -------------------------------------------------------------- checklist
def test_checklist_casa_por_palavra_inteira():
    from app.documentos.checklist import tipo_sugerido
    assert tipo_sugerido("Comprovante de inscrição no CNPJ com data de "
                         "emissão recente") is None
    assert tipo_sugerido("Declaração de enquadramento na categoria ME/EPP") \
        is None
    assert tipo_sugerido("Ata de reunião de sócios") is None
    assert tipo_sugerido("Certidão negativa de ISS") == "CND Municipal"
    assert tipo_sugerido("Certidão de acervo técnico (CAT)") == "CAT"


def test_data_da_sessao_cai_para_o_portal_e_prefere_prorrogacao():
    from datetime import date
    from app.documentos.checklist import data_da_sessao

    class L:
        data_encerramento_proposta = "2026-09-30T09:00:00"
    # ficha fora do ISO não derruba a do portal
    assert data_da_sessao({"datas": {"sessao_abertura": "20/09/2026"}}, L()) \
        == date(2026, 9, 30)
    # tipo errado não é 500
    assert data_da_sessao({"datas": {"sessao_abertura": 20260920}}, L()) \
        == date(2026, 9, 30)
    # ficha antiga (09/09) e portal prorrogado (30/09): vale o portal
    assert data_da_sessao({"datas": {"sessao_abertura": "2026-09-09T09:00"}},
                          L()) == date(2026, 9, 30)
    # ficha mais recente que o portal continua valendo
    L.data_encerramento_proposta = "2026-09-01T09:00:00"
    assert data_da_sessao({"datas": {"sessao_abertura": "2026-09-09T09:00"}},
                          L()) == date(2026, 9, 9)


# ------------------------------------------------------------- perícia/IA
def test_pdf_e_reconhecido_pelo_conteudo_nao_pela_extensao(tmp_path):
    from app.analista.parecer import e_pdf
    sem_extensao = tmp_path / "certidao"
    sem_extensao.write_bytes(b"%PDF-1.4 lixo")
    assert e_pdf(str(sem_extensao))
    falso = tmp_path / "x.pdf"
    falso.write_bytes(b"nao e pdf")
    assert not e_pdf(str(falso))


def test_prompt_do_corretor_existe_e_e_neutro():
    from ia import cliente
    texto = cliente.carregar_prompt("peritos/perito-corretor")
    assert "mérito" in texto and "inteiro corrigido" in texto.lower()


def test_cartao_de_edital_que_mudou_abre_o_proprio_edital(admin):
    """O cartão 'edital que você acompanha mudou' mandava para o funil —
    clique sem relação com o aviso. Agora abre o edital, dizendo o que
    mudou."""
    from app.config import agora
    from app.db import LicitacaoAlteracao
    s = Sessao()
    try:
        adm_id = (s.query(Usuario.id).filter_by(papel="admin")
                  .order_by(Usuario.id).scalar())
        perfil = PerfilBusca(nome="perfil-teste-mudanca", usuario_id=adm_id)
        lic = Licitacao(numero_controle_pncp="teste-mudou-1-1/2026",
                        objeto="Obra de teste que mudou", municipio_nome="X",
                        uf="PI", data_encerramento_proposta="2099-12-01T09:00:00")
        s.add_all([perfil, lic])
        s.flush()
        s.add(PerfilMatch(perfil_id=perfil.id, licitacao_id=lic.id,
                          status="vou_participar"))
        s.add(LicitacaoAlteracao(licitacao_id=lic.id, campo="situacao",
                                 valor_antigo="Divulgada",
                                 valor_novo="Suspensa", detectada_em=agora()))
        s.commit()
        ids = (perfil.id, lic.id)
    finally:
        s.close()
    perfil_id, lic_id = ids
    try:
        html = admin.get("/").text
        assert f'href="/licitacoes/{lic_id}"' in html
        assert "situação: Divulgada → Suspensa" in html
        assert "ver o que mudou" in html
        assert 'href="/funil"' not in html.split("Edital que você acompanha")[1] \
            .split("</a>")[0]
    finally:
        s = Sessao()
        try:
            s.query(LicitacaoAlteracao).filter_by(licitacao_id=lic_id).delete()
            s.query(PerfilMatch).filter_by(licitacao_id=lic_id).delete()
            s.query(Licitacao).filter_by(id=lic_id).delete()
            s.query(PerfilBusca).filter_by(id=perfil_id).delete()
            s.commit()
        finally:
            s.close()


# ------------------------------------------- tela da licitação (mural TCE-PI)
def test_sentenca_respeita_abreviacoes_e_resumir_corta_em_palavra():
    from app.texto import resumir, sentenca
    assert sentenca("P. M. DE SAO JULIAO") == "P. M. de sao juliao"
    assert sentenca("CONTRATAÇÃO DE EMPRESA. AQUISIÇÃO DE PEÇAS (SRP)") == \
        "Contratação de empresa. Aquisição de peças (SRP)"
    longo = "Contratação de empresa para manutenção de aparelhos e reposição"
    assert resumir(longo, 40) == "Contratação de empresa para manutenção…"
    assert resumir("curto", 40) == "curto"


def test_numero_da_compra_nunca_mostra_none():
    from app.main import _filtro_numero_compra

    class L:
        def __init__(self, n, a):
            self.numero_compra, self.ano_compra = n, a
    assert _filtro_numero_compra(L("020/2026", None)) == "020/2026"
    assert _filtro_numero_compra(L("90008", 2026)) == "90008/2026"
    assert _filtro_numero_compra(L(None, None)) == ""


def test_mural_ganha_codigo_ibge_e_nome_oficial(sessao_memoria):
    from app.db import Municipio
    from app.radar.coleta import _oficializar_municipio, ibge_por_nome
    s = sessao_memoria
    s.add(Municipio(codigo_ibge="2209906", nome="São Julião", uf="PI"))
    s.commit()
    item = {"municipio_nome": "Sao Juliao", "municipio_ibge": None}
    assert _oficializar_municipio(item, ibge_por_nome(s))
    assert item == {"municipio_nome": "São Julião", "municipio_ibge": "2209906"}
    assert not _oficializar_municipio({"municipio_nome": "Nárnia"},
                                      ibge_por_nome(s))


def test_pagina_de_item_do_mural_fala_a_lingua_certa(admin):
    """'Nº no PNCP' e 'Compra: 020/2026/None' num item do Mural TCE-PI;
    botão 'Tentar de novo' de leitura que nunca vai dar certo."""
    s = Sessao()
    try:
        lic = s.query(Licitacao).filter_by(fonte="tcepi").first()
        lic_id = lic.id if lic else None
    finally:
        s.close()
    if not lic_id:
        pytest.skip("banco local sem item do mural")
    html = admin.get(f"/licitacoes/{lic_id}").text
    assert "Nº no Mural TCE-PI" in html
    assert "/None" not in html
    assert "Tentar de novo" not in html
    assert "Localizando este certame no PNCP" in html
    assert "Abertura" in html


def test_correspondencia_mural_pncp_exige_municipio_e_mais_um_sinal():
    from app.ingestao.pncp_busca import pontuar_correspondencia

    class L:
        municipio_nome = "Sao Juliao"
        valor_total_estimado = 181370.0
        numero_compra = "020/2026"
        objeto = ("Contratação de empresa para prestação de serviços de "
                  "manutenção e instalação de aparelho de refrigeração")
    item_certo = {"municipio_nome": "São Julião", "valor_total_estimado":
                  181370.0, "numero_compra": "20", "ano_compra": 2026,
                  "objeto": "[Portal de Compras Públicas] - " + L.objeto}
    outro_municipio = dict(item_certo, municipio_nome="Teresina")
    so_municipio = {"municipio_nome": "São Julião", "valor_total_estimado":
                    5.0, "numero_compra": "99", "ano_compra": 2026,
                    "objeto": "Merenda escolar"}
    assert pontuar_correspondencia(L(), item_certo) >= 2
    assert pontuar_correspondencia(L(), outro_municipio) == 0
    assert pontuar_correspondencia(L(), so_municipio) == 0


def test_item_do_mural_adotado_pelo_pncp_leva_a_triagem(sessao_memoria):
    from app.radar.coleta import adotar_do_pncp
    s = sessao_memoria
    u = Usuario(nome="U", email="u@x", senha_hash="h")
    s.add(u)
    s.flush()
    perfil = PerfilBusca(nome="P", usuario_id=u.id)
    s.add(perfil)
    s.flush()
    mural = Licitacao(numero_controle_pncp="TCEPI-1", fonte="tcepi",
                      objeto="Obra", municipio_nome="São Julião", uf="PI",
                      municipio_ibge="2209906")
    s.add(mural)
    s.flush()
    s.add(PerfilMatch(perfil_id=perfil.id, licitacao_id=mural.id,
                      status="vou_participar", anotacao="ligar amanhã"))
    s.commit()
    item = {"numero_controle_pncp": "x-1-20/2026", "fonte": "pncp",
            "objeto": "Obra", "objeto_norm": "obra", "municipio_nome":
            "São Julião", "uf": "PI", "link_pncp": "https://pncp/x"}
    nova = adotar_do_pncp(s, mural, item)
    assert nova.fonte == "pncp" and nova.municipio_ibge == "2209906"
    assert s.query(Licitacao).filter_by(fonte="tcepi").count() == 0
    m = s.query(PerfilMatch).one()
    assert (m.licitacao_id, m.status, m.anotacao) ==         (nova.id, "vou_participar", "ligar amanhã")


def test_portal_da_disputa_em_nome_humano():
    from app.main import _filtro_portal

    class L:
        def __init__(self, link, objeto=""):
            self.link_sistema_origem, self.objeto = link, objeto
    assert _filtro_portal(L("https://www.portaldecompraspublicas.com.br/x"))         == "Portal de Compras Públicas"
    assert _filtro_portal(L("https://bllcompras.com/Process")) == "BLL Compras"
    assert _filtro_portal(L("", "[LICITANET] - Aquisição")) == "Licitanet"
    assert _filtro_portal(L("https://novo.exemplo.gov.br/a")) ==         "novo.exemplo.gov.br"
    assert _filtro_portal(L("", "Aquisição")) == ""


def test_titulo_sem_prefixo_do_portal():
    from app.main import _filtro_sem_portal
    assert _filtro_sem_portal("[Portal de Compras Públicas] - Futuro serviço")         == "Futuro serviço"
    assert _filtro_sem_portal("[LICITANET]Aquisição") == "Aquisição"
    assert _filtro_sem_portal("Sem prefixo") == "Sem prefixo"
    assert _filtro_sem_portal(None) == ""
