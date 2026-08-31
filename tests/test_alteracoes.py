"""Testes da detecção de republicação/alteração: o que é mudança de
verdade, quem é avisado e o anti-reprocessamento."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import (Base, Licitacao, LicitacaoAlteracao, PerfilBusca,
                    PerfilMatch, Usuario)
from app.radar import alteracoes


class LicFake:
    situacao = "Divulgada"
    data_encerramento_proposta = "2026-09-10T09:00:00"
    data_abertura_proposta = "2026-09-01T08:00:00"
    valor_total_estimado = 100000.0
    objeto = "Manutenção de ar condicionado"
    numero_controle_pncp = "x-1-1/2026"


def item_base(**muda):
    item = {"situacao": "Divulgada",
            "data_encerramento_proposta": "2026-09-10T09:00:00",
            "data_abertura_proposta": "2026-09-01T08:00:00",
            "valor_total_estimado": 100000.0,
            "objeto": "Manutenção de ar condicionado",
            "coletado_em": "muda sempre e não interessa"}
    item.update(muda)
    return item


# ------------------------------------------------------------------ detectar
def test_nada_mudou_nada_detecta():
    assert alteracoes.detectar(LicFake(), item_base()) == []


def test_suspensao_e_prorrogacao_sao_detectadas():
    mudancas = alteracoes.detectar(LicFake(), item_base(
        situacao="Suspensa",
        data_encerramento_proposta="2026-09-20T09:00:00"))
    campos = {c for c, _, _ in mudancas}
    assert campos == {"situacao", "data_encerramento_proposta"}


def test_none_na_origem_nao_e_alteracao():
    """A busca ao vivo devolve campos nulos; preencher depois não é notícia."""
    lic = LicFake()
    lic.valor_total_estimado = None
    assert alteracoes.detectar(lic, item_base(situacao=None)) == []
    assert alteracoes.detectar(lic, item_base()) == []   # None -> valor: idem


def test_ruido_de_float_nao_dispara():
    assert alteracoes.detectar(LicFake(),
                               item_base(valor_total_estimado=100000.001)) == []
    mudancas = alteracoes.detectar(LicFake(),
                                   item_base(valor_total_estimado=250000.0))
    assert [c for c, _, _ in mudancas] == ["valor_total_estimado"]


def test_espacos_nas_pontas_nao_disparam():
    assert alteracoes.detectar(LicFake(), item_base(
        objeto="  Manutenção de ar condicionado ")) == []


# --------------------------------------------------------------- fim a fim
@pytest.fixture()
def sessao():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def montar_cenario(sessao, status="vou_participar", favorito=False,
                   chat_id="111"):
    usuario = Usuario(nome="Dona", email="dona@x.com", senha_hash="h",
                      papel="admin", telegram_chat_id=chat_id,
                      receber_telegram=True, receber_email=False,
                      receber_push=False)
    lic = Licitacao(numero_controle_pncp="x-1-1/2026", objeto="Ar",
                    situacao="Divulgada", uf="PI",
                    modalidade_nome="Pregão", numero_compra="1",
                    ano_compra=2026, orgao_nome="Pref.")
    sessao.add_all([usuario, lic])
    sessao.flush()
    perfil = PerfilBusca(nome="P", usuario_id=usuario.id)
    sessao.add(perfil)
    sessao.flush()
    sessao.add(PerfilMatch(perfil_id=perfil.id, licitacao_id=lic.id,
                           status=status, favorito=favorito))
    sessao.add(LicitacaoAlteracao(licitacao_id=lic.id, campo="situacao",
                                  valor_antigo="Divulgada",
                                  valor_novo="Suspensa"))
    sessao.commit()
    return usuario, lic


@pytest.fixture()
def telegram_capturado(monkeypatch):
    enviados = []
    monkeypatch.setattr("app.notificacoes.alerta.enviar_telegram",
                        lambda texto, chat_id=None: enviados.append(
                            (chat_id, texto)) or True)
    return enviados


def test_quem_acompanha_recebe_o_aviso(sessao, telegram_capturado):
    montar_cenario(sessao, status="vou_participar")
    assert alteracoes.avisar_alteracoes(sessao) == 1
    chat, texto = telegram_capturado[0]
    assert chat == "111" and "MUDOU" in texto
    assert "situação: Divulgada → Suspensa" in texto
    assert sessao.query(LicitacaoAlteracao).filter_by(avisada=False).count() == 0


def test_favorito_tambem_acompanha(sessao, telegram_capturado):
    montar_cenario(sessao, status="novo", favorito=True)
    assert alteracoes.avisar_alteracoes(sessao) == 1


def test_match_novo_nao_e_incomodado_mas_nao_fica_pendente(
        sessao, telegram_capturado):
    """Mudança em edital não triado: sem aviso — e sem varrer para sempre."""
    montar_cenario(sessao, status="novo")
    assert alteracoes.avisar_alteracoes(sessao) == 0
    assert telegram_capturado == []
    assert sessao.query(LicitacaoAlteracao).filter_by(avisada=False).count() == 0


def test_canal_fora_deixa_pendente_para_o_proximo_ciclo(sessao, monkeypatch):
    montar_cenario(sessao)
    monkeypatch.setattr("app.notificacoes.alerta.enviar_telegram",
                        lambda *a, **k: False)
    assert alteracoes.avisar_alteracoes(sessao) == 0
    assert sessao.query(LicitacaoAlteracao).filter_by(avisada=False).count() == 1


def test_registrar_grava_e_trunca(sessao):
    _, lic = montar_cenario(sessao)
    alteracoes.registrar(sessao, lic, {"objeto": "Novo objeto " + "x" * 3000})
    sessao.commit()
    linha = (sessao.query(LicitacaoAlteracao)
             .filter_by(campo="objeto").one())
    assert len(linha.valor_novo) <= 2000


def test_formatacao_humana_no_aviso():
    assert alteracoes._fmt("valor_total_estimado", "250000.0") == "R$ 250.000,00"
    assert alteracoes._fmt("data_encerramento_proposta",
                           "2026-09-20T09:00:00") == "20/09/2026 09:00"
