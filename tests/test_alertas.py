"""Testes dos alertas configuráveis: vigência, situação e frequência."""
from datetime import datetime, timedelta

import pytest

from app.alerta import (JANELA_ATRASO, alerta_devido, resumo_frequencia,
                        separar_pendentes)
from app.matcher import esta_vigente, licitacao_casa_perfil

AGORA = datetime(2026, 8, 31, 9, 0)      # segunda-feira, 09:00


class LicFake:
    def __init__(self, encerramento="2026-12-01T09:00:00", situacao="Divulgada"):
        self.data_encerramento_proposta = encerramento
        self.situacao = situacao
        self.uf = "PI"
        self.municipio_ibge = "2211001"
        self.modalidade_codigo = 6
        self.srp = False
        self.valor_total_estimado = 100000.0
        self.objeto = "Manutenção de ar condicionado"


class PerfilFake:
    def __init__(self, **campos):
        self.id = 1
        self.nome = "Teste"
        self.ativo = True
        self.notificar = True
        self.ufs = []
        self.municipios_ibge = []
        self.modalidades = []
        self.palavras_incluir = []
        self.palavras_excluir = []
        self.valor_min = self.valor_max = None
        self.somente_srp = False
        self.modo_busca = "ou"
        self.ordenacao = "encerramento_asc"
        self.situacoes = []
        self.somente_vigentes = True
        self.frequencia = "diario"
        self.dia_semana = 0
        self.dia_mes = 1
        self.mes_ano = 1
        self.hora_envio = "07:00"
        self.ultimo_envio = None
        self.__dict__.update(campos)


class MatchFake:
    def __init__(self, lic):
        self.licitacao = lic
        self.licitacao_id = id(lic)
        self.notificado = False
        self.termos = "ar condicionado"


class SessaoFake:
    """Sessão mínima: devolve os matches dados e conta os commits.

    Basta para o alerta — a única consulta que ele faz por fora é a do link
    do edital, que não acha arquivo e desiste em silêncio.
    """

    def __init__(self, pendentes=()):
        self.pendentes = list(pendentes)
        self.commits = 0
        self._filtrando_matches = False

    def query(self, modelo):
        self._filtrando_matches = getattr(modelo, "__name__", "") == "PerfilMatch"
        return self

    def filter_by(self, **_):
        return self

    def all(self):
        return self.pendentes if self._filtrando_matches else []

    def first(self):
        return None

    def commit(self):
        self.commits += 1


# ------------------------------------------------------------------ vigência
def test_prazo_encerrado_nao_esta_vigente():
    assert not esta_vigente(LicFake("2026-08-24T08:00:00"), AGORA)


def test_prazo_futuro_esta_vigente():
    assert esta_vigente(LicFake("2026-09-10T09:00:00"), AGORA)


def test_encerramento_hoje_mais_tarde_ainda_vale():
    assert esta_vigente(LicFake("2026-08-31T17:00:00"), AGORA)


def test_encerramento_hoje_ja_passou_nao_vale():
    assert not esta_vigente(LicFake("2026-08-31T08:00:00"), AGORA)


def test_sem_data_de_encerramento_nao_descarta():
    assert esta_vigente(LicFake(None), AGORA)


def test_data_com_espaco_no_lugar_do_T_tambem_e_lida():
    assert not esta_vigente(LicFake("2026-08-24 08:00:00"), AGORA)


# ------------------------------------------------- filtro no matcher completo
def test_matcher_descarta_vencida_quando_somente_vigentes():
    perfil = PerfilFake(somente_vigentes=True)
    assert not licitacao_casa_perfil(LicFake("2026-01-01T09:00:00"), perfil, AGORA)


def test_matcher_aceita_vencida_se_o_usuario_desligar_a_trava():
    perfil = PerfilFake(somente_vigentes=False)
    assert licitacao_casa_perfil(LicFake("2026-01-01T09:00:00"), perfil, AGORA)


def test_matcher_respeita_a_lista_de_situacoes():
    perfil = PerfilFake(situacoes=["Divulgada", "Aberta"])
    assert licitacao_casa_perfil(LicFake(situacao="Aberta"), perfil, AGORA)
    assert not licitacao_casa_perfil(LicFake(situacao="Cancelada"), perfil, AGORA)


def test_situacoes_vazio_aceita_qualquer_situacao():
    perfil = PerfilFake(situacoes=[])
    assert licitacao_casa_perfil(LicFake(situacao="Revogada"), perfil, AGORA)


# ------------------------------------------------------ separação de pendentes
def test_separar_pendentes_isola_vencidas_e_fora_de_situacao():
    perfil = PerfilFake(situacoes=["Divulgada"])
    boa = MatchFake(LicFake("2026-09-30T09:00:00", "Divulgada"))
    vencida = MatchFake(LicFake("2026-08-01T09:00:00", "Divulgada"))
    cancelada = MatchFake(LicFake("2026-09-30T09:00:00", "Cancelada"))
    enviaveis, vencidos, fora = separar_pendentes(
        perfil, [boa, vencida, cancelada], AGORA)
    assert enviaveis == [boa]
    assert vencidos == [vencida]
    assert fora == [cancelada]


# ------------------------------------------------------------- agendamento
def test_antes_da_hora_o_alerta_nao_sai():
    perfil = PerfilFake(hora_envio="10:00")
    assert not alerta_devido(perfil, AGORA)


def test_depois_da_hora_o_diario_sai():
    assert alerta_devido(PerfilFake(hora_envio="07:00"), AGORA)


def test_nao_repete_no_mesmo_dia():
    perfil = PerfilFake(ultimo_envio=datetime(2026, 8, 31, 7, 0))
    assert not alerta_devido(perfil, AGORA)


def test_perfil_sem_notificar_nunca_sai():
    assert not alerta_devido(PerfilFake(notificar=False), AGORA)


def test_perfil_inativo_nunca_sai():
    assert not alerta_devido(PerfilFake(ativo=False), AGORA)


def test_semanal_so_sai_no_dia_marcado():
    # 31/08/2026 é segunda (weekday 0)
    ontem = datetime(2026, 8, 30, 7, 0)
    na_segunda = PerfilFake(frequencia="semanal", dia_semana=0,
                            ultimo_envio=ontem)
    na_quarta = PerfilFake(frequencia="semanal", dia_semana=2,
                           ultimo_envio=ontem)
    assert alerta_devido(na_segunda, AGORA)
    assert not alerta_devido(na_quarta, AGORA)


def test_mensal_so_sai_no_dia_do_mes():
    ontem = datetime(2026, 8, 30, 7, 0)
    dia_31 = PerfilFake(frequencia="mensal", dia_mes=31, ultimo_envio=ontem)
    dia_5 = PerfilFake(frequencia="mensal", dia_mes=5, ultimo_envio=ontem)
    assert alerta_devido(dia_31, AGORA)
    assert not alerta_devido(dia_5, AGORA)


def test_anual_exige_mes_e_dia():
    ontem = datetime(2026, 8, 30, 7, 0)
    certo = PerfilFake(frequencia="anual", mes_ano=8, dia_mes=31,
                       ultimo_envio=ontem)
    outro_mes = PerfilFake(frequencia="anual", mes_ano=3, dia_mes=31,
                           ultimo_envio=ontem)
    assert alerta_devido(certo, AGORA)
    assert not alerta_devido(outro_mes, AGORA)


def test_ciclo_vencido_sai_mesmo_fora_do_dia_marcado():
    """App fora do ar no dia certo não pode fazer o alerta sumir."""
    atrasado = AGORA - timedelta(days=JANELA_ATRASO["semanal"] + 1)
    perfil = PerfilFake(frequencia="semanal", dia_semana=2,
                        ultimo_envio=atrasado)
    assert alerta_devido(perfil, AGORA)


def test_respeitar_hora_desligado_ignora_o_relogio():
    perfil = PerfilFake(hora_envio="23:00")
    assert not alerta_devido(perfil, AGORA)
    assert alerta_devido(perfil, AGORA, respeitar_hora=False)


def test_hora_invalida_cai_no_padrao_do_env():
    from app.config import config
    perfil = PerfilFake(hora_envio="banana")
    esperado = datetime(2026, 8, 31, *config.HORA_ALERTA)
    assert alerta_devido(perfil, esperado)


# ------------------------------------------------------------------- envio
def _lic_completa(encerramento, situacao="Divulgada"):
    lic = LicFake(encerramento, situacao)
    lic.id = id(lic)
    lic.fonte = "tcepi"                  # sem consulta à API de documentos
    lic.modalidade_nome = "Pregão - Eletrônico"
    lic.numero_compra, lic.ano_compra = "10", 2026
    lic.orgao_nome, lic.unidade_nome = "PREFEITURA DE TESTE", "SEC"
    lic.municipio_nome = "Teresina"
    lic.data_abertura_proposta = "2026-09-01T08:00:00"
    lic.data_publicacao_pncp = "2026-08-20T08:00:00"
    lic.link_pncp = "https://pncp.gov.br/app/editais/x"
    lic.link_sistema_origem = ""
    lic.orgao_cnpj = "18457226000181"
    lic.numero_controle_pncp = "18457226000181-1-000010/2026"
    return lic


def test_mensagem_lista_so_as_vigentes(monkeypatch):
    from app import alerta
    perfil = PerfilFake(nome="Ar-condicionado", situacoes=["Divulgada"])
    boa = MatchFake(_lic_completa("2026-09-30T09:00:00"))
    sessao = SessaoFake()
    texto = alerta.montar_mensagem_perfil(sessao, perfil, [boa],
                                          host="http://exemplo")
    assert texto.startswith("📡 Ar-condicionado")
    assert "1 oportunidade com proposta em aberto" in texto
    assert "PREFEITURA DE TESTE" in texto
    assert "http://exemplo/" in texto


def test_envio_descarta_vencida_e_nao_a_reavalia(monkeypatch):
    """O prazo não volta atrás: a vencida sai da fila de vez."""
    from app import alerta
    enviados = []
    monkeypatch.setattr(alerta, "enviar_telegram",
                        lambda t: enviados.append(t) or True)
    monkeypatch.setattr(alerta, "enviar_email", lambda t: False)
    boa = MatchFake(_lic_completa("2026-09-30T09:00:00"))
    vencida = MatchFake(_lic_completa("2026-08-01T09:00:00"))
    perfil = PerfilFake(situacoes=["Divulgada"])
    sessao = SessaoFake([boa, vencida])

    enviou, quantidade = alerta.enviar_alerta_perfil(sessao, perfil, agora=AGORA)

    assert (enviou, quantidade) == (True, 1)
    assert vencida.notificado and boa.notificado
    assert len(enviados) == 1
    assert "2026" in enviados[0] and "01/08/2026" not in enviados[0]
    assert perfil.ultimo_envio == AGORA


def test_ciclo_sem_novidade_nao_manda_mensagem(monkeypatch):
    from app import alerta
    monkeypatch.setattr(alerta, "enviar_telegram",
                        lambda t: pytest.fail("não devia enviar nada"))
    monkeypatch.setattr(alerta, "enviar_email",
                        lambda t: pytest.fail("não devia enviar nada"))
    perfil = PerfilFake()
    enviou, quantidade = alerta.enviar_alerta_perfil(
        SessaoFake([MatchFake(_lic_completa("2026-08-01T09:00:00"))]),
        perfil, agora=AGORA)
    assert (enviou, quantidade) == (False, 0)
    assert perfil.ultimo_envio == AGORA      # ciclo cumprido mesmo em silêncio


def test_falha_no_canal_nao_marca_como_avisado(monkeypatch):
    """Telegram fora do ar não pode fazer a oportunidade sumir."""
    from app import alerta
    monkeypatch.setattr(alerta, "enviar_telegram", lambda t: False)
    monkeypatch.setattr(alerta, "enviar_email", lambda t: False)
    boa = MatchFake(_lic_completa("2026-09-30T09:00:00"))
    perfil = PerfilFake()
    enviou, _ = alerta.enviar_alerta_perfil(SessaoFake([boa]), perfil,
                                            agora=AGORA)
    assert not enviou
    assert not boa.notificado
    assert perfil.ultimo_envio is None       # tenta de novo no próximo ciclo


# ------------------------------------------------------------------- resumo
def test_resumo_descreve_a_agenda_em_portugues():
    assert resumo_frequencia(PerfilFake()) == "Todo dia, às 07:00"
    assert resumo_frequencia(PerfilFake(frequencia="semanal", dia_semana=2)) == \
        "Toda quarta-feira, às 07:00"
    assert resumo_frequencia(PerfilFake(frequencia="mensal", dia_mes=5)) == \
        "Todo dia 5 do mês, às 07:00"
    assert resumo_frequencia(
        PerfilFake(frequencia="anual", dia_mes=10, mes_ano=3)) == \
        "Todo dia 10 de março, às 07:00"
