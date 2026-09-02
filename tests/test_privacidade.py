"""Cada login é privado: dossiê, casos periciais, pareceres, minutas e
dados da empresa são de quem os criou — outro usuário não vê, não baixa
e não usa (decisão do dono do produto em 02/09/2026)."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import (Base, CasoPericial, DocumentoEmpresa, EmpresaDados,
                    LaudoPericial, Licitacao, Minuta, Parecer, Sessao,
                    Usuario)
from tests.test_multiusuario import (SENHA_COLEGA, colega,  # noqa: F401
                                     como_admin, como_colega)


@pytest.fixture()
def memoria():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def _admin_id():
    s = Sessao()
    try:
        return (s.query(Usuario.id).filter_by(papel="admin")
                .order_by(Usuario.id).scalar())
    finally:
        s.close()


# ------------------------------------------------------------ dossiê
def test_dossie_do_admin_nao_aparece_para_o_colega(como_admin, como_colega):
    s = Sessao()
    try:
        doc = DocumentoEmpresa(nome="CND privada do admin",
                               enviado_por=_admin_id())
        s.add(doc)
        s.commit()
        doc_id = doc.id
    finally:
        s.close()
    try:
        assert "CND privada do admin" in como_admin.get("/documentos").text
        assert "CND privada do admin" not in como_colega.get("/documentos").text
        assert como_colega.get(f"/documentos/{doc_id}/arquivo").status_code \
            == 404
        # editar/arquivar alheio não faz nada
        como_colega.post(f"/documentos/{doc_id}/arquivar",
                         follow_redirects=False)
        s = Sessao()
        try:
            assert s.get(DocumentoEmpresa, doc_id).arquivado is False
        finally:
            s.close()
    finally:
        s = Sessao()
        try:
            s.query(DocumentoEmpresa).filter_by(id=doc_id).delete()
            s.commit()
        finally:
            s.close()


def test_upload_do_colega_pertence_ao_colega(como_colega, colega):
    r = como_colega.post(
        "/documentos",
        files=[("arquivos", ("cnd.pdf", b"%PDF-1.4 teste", "application/pdf"))],
        follow_redirects=False)
    assert r.status_code == 303
    s = Sessao()
    try:
        doc = (s.query(DocumentoEmpresa).filter_by(enviado_por=colega)
               .order_by(DocumentoEmpresa.id.desc()).first())
        assert doc is not None
        s.delete(doc)
        s.commit()
    finally:
        s.close()


def test_parecer_so_le_o_dossie_do_proprio_usuario(memoria):
    from app.analista.parecer import _dossie
    a = Usuario(nome="A", email="a@x", senha_hash="h")
    b = Usuario(nome="B", email="b@x", senha_hash="h")
    memoria.add_all([a, b])
    memoria.flush()
    memoria.add_all([DocumentoEmpresa(nome="de A", enviado_por=a.id),
                     DocumentoEmpresa(nome="de B", enviado_por=b.id)])
    memoria.commit()
    assert [d["nome"] for d in _dossie(memoria, None, a.id)] == ["de A"]
    assert [d["nome"] for d in _dossie(memoria, None, b.id)] == ["de B"]


def test_aviso_de_validade_vai_para_o_dono(memoria, monkeypatch):
    from datetime import date
    from app.documentos import validades
    dono = Usuario(nome="Dono", email="dono@x", senha_hash="h",
                   telegram_chat_id="123")
    memoria.add(dono)
    memoria.flush()
    memoria.add(DocumentoEmpresa(nome="CND do dono", validade="2026-09-05",
                                 enviado_por=dono.id))
    memoria.commit()
    recebidos = []
    monkeypatch.setattr("app.notificacoes.alerta.enviar_telegram",
                        lambda texto, chat_id=None: recebidos.append(chat_id)
                        or True)
    monkeypatch.setattr("app.vigia._avisar_admins",
                        lambda *a, **k: pytest.fail("foi para o admin"))
    assert validades.avisar_vencimentos(memoria, hoje=date(2026, 8, 31)) == 1
    assert recebidos == ["123"]


# ---------------------------------------------------------- empresa
def test_dados_da_empresa_sao_por_usuario(memoria):
    from app.pecas.minutas import dados_empresa
    a = Usuario(nome="A", email="a@x", senha_hash="h")
    b = Usuario(nome="B", email="b@x", senha_hash="h")
    memoria.add_all([a, b])
    memoria.flush()
    dados_empresa(memoria, a.id).razao_social = "Empresa de A"
    memoria.commit()
    assert dados_empresa(memoria, b.id).razao_social == ""
    assert dados_empresa(memoria, a.id).razao_social == "Empresa de A"
    assert memoria.query(EmpresaDados).count() == 2


def test_empresa_salva_pela_conta(como_colega, colega):
    r = como_colega.post("/conta/empresa",
                         data={"razao_social": "Colega LTDA"},
                         follow_redirects=False)
    assert r.status_code == 303
    assert "Colega LTDA" in como_colega.get("/conta").text
    s = Sessao()
    try:
        s.query(EmpresaDados).filter_by(usuario_id=colega).delete()
        s.commit()
    finally:
        s.close()


# ------------------------------------------- casos, pareceres e minutas
def test_caso_pericial_e_pecas_do_admin_dao_404_ao_colega(como_colega):
    s = Sessao()
    try:
        lic = s.query(Licitacao).first()
        if lic is None:
            pytest.skip("banco local sem licitação")
        caso = CasoPericial(titulo="Caso privado", criado_por=_admin_id())
        s.add(caso)
        s.flush()
        laudo = LaudoPericial(caso_id=caso.id, texto="l",
                              criado_por=_admin_id())
        parecer = Parecer(licitacao_id=lic.id, texto="p",
                          criado_por=_admin_id())
        minuta = Minuta(licitacao_id=lic.id, texto="m",
                        criado_por=_admin_id())
        s.add_all([laudo, parecer, minuta])
        s.commit()
        ids = (caso.id, laudo.id, parecer.id, minuta.id)
    finally:
        s.close()
    caso_id, laudo_id, parecer_id, minuta_id = ids
    try:
        assert "Caso privado" not in como_colega.get("/pericias").text
        for rota in (f"/pericias/{caso_id}",
                     f"/pericias/laudos/{laudo_id}",
                     f"/pericias/laudos/{laudo_id}/baixar",
                     f"/pareceres/{parecer_id}",
                     f"/pareceres/{parecer_id}/baixar",
                     f"/minutas/{minuta_id}",
                     f"/minutas/{minuta_id}/baixar"):
            assert como_colega.get(rota).status_code == 404, rota
        assert como_colega.post(f"/pericias/{caso_id}/laudo").status_code \
            in (200, 404)     # premium ou não, nunca o caso alheio
        assert "Caso privado" not in como_colega.post(
            f"/pericias/{caso_id}/laudo").text
    finally:
        s = Sessao()
        try:
            s.query(LaudoPericial).filter_by(id=laudo_id).delete()
            s.query(CasoPericial).filter_by(id=caso_id).delete()
            s.query(Parecer).filter_by(id=parecer_id).delete()
            s.query(Minuta).filter_by(id=minuta_id).delete()
            s.commit()
        finally:
            s.close()


def test_migracao_adota_orfaos_para_o_admin(memoria):
    from app.db import _adotar_orfaos
    adm = Usuario(nome="Adm", email="adm@x", senha_hash="h", papel="admin")
    memoria.add(adm)
    memoria.flush()
    memoria.add_all([DocumentoEmpresa(nome="antigo"),
                     CasoPericial(titulo="antigo"),
                     EmpresaDados(razao_social="antiga")])
    memoria.commit()
    _adotar_orfaos(memoria, adm.id)
    memoria.commit()
    assert memoria.query(DocumentoEmpresa).one().enviado_por == adm.id
    assert memoria.query(CasoPericial).one().criado_por == adm.id
    assert memoria.query(EmpresaDados).one().usuario_id == adm.id
