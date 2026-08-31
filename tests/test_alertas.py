"""Testes dos alertas configuráveis: vigência, situação e frequência."""
from datetime import datetime, timedelta

import pytest

from app.alerta import (alerta_devido, horario_previsto,
                        proximo_horario_previsto, resumo_frequencia,
                        separar_pendentes, tem_urgencia)
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
        self.intervalo_horas = 3
        self.dia_semana = 0
        self.dia_mes = 1
        self.mes_ano = 1
        self.hora_envio = "07:00"
        self.ultimo_envio = None
        self.criado_em = datetime(2026, 8, 1, 0, 0)
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
    perfil = PerfilFake(hora_envio="10:00",
                        ultimo_envio=datetime(2026, 8, 30, 10, 0))
    assert not alerta_devido(perfil, AGORA)
    assert alerta_devido(perfil, datetime(2026, 8, 31, 10, 0))


def test_perfil_recem_criado_espera_a_hora_escolhida():
    """Criado às 8h com envio às 10h: não dispara na hora da criação."""
    perfil = PerfilFake(hora_envio="10:00", ultimo_envio=None,
                        criado_em=datetime(2026, 8, 31, 8, 0))
    assert not alerta_devido(perfil, datetime(2026, 8, 31, 9, 0))
    assert alerta_devido(perfil, datetime(2026, 8, 31, 10, 0))


def test_depois_da_hora_o_diario_sai():
    assert alerta_devido(PerfilFake(hora_envio="07:00"), AGORA)


def test_nao_repete_no_mesmo_dia():
    perfil = PerfilFake(ultimo_envio=datetime(2026, 8, 31, 7, 0))
    assert not alerta_devido(perfil, AGORA)


def test_perfil_sem_notificar_nunca_sai():
    assert not alerta_devido(PerfilFake(notificar=False), AGORA)


def test_perfil_inativo_nunca_sai():
    assert not alerta_devido(PerfilFake(ativo=False), AGORA)


def test_varias_vezes_por_dia_repete_apos_o_intervalo():
    """A única frequência que pode sair mais de uma vez no mesmo dia."""
    perfil = PerfilFake(frequencia="horas", intervalo_horas=3,
                        hora_envio="07:00",
                        ultimo_envio=datetime(2026, 8, 31, 7, 0))
    assert not alerta_devido(perfil, datetime(2026, 8, 31, 9, 30))  # 2h30
    assert alerta_devido(perfil, datetime(2026, 8, 31, 10, 0))      # 3h


def test_varias_vezes_por_dia_nao_toca_de_madrugada():
    """A hora do perfil vira o primeiro envio do dia: nada às 3 da manhã."""
    perfil = PerfilFake(frequencia="horas", intervalo_horas=3,
                        hora_envio="07:00",
                        ultimo_envio=datetime(2026, 8, 30, 22, 0))
    assert not alerta_devido(perfil, datetime(2026, 8, 31, 3, 0))
    assert alerta_devido(perfil, datetime(2026, 8, 31, 7, 0))


def test_varias_vezes_por_dia_sem_envio_anterior_sai_na_primeira_hora():
    perfil = PerfilFake(frequencia="horas", hora_envio="07:00")
    assert alerta_devido(perfil, datetime(2026, 8, 31, 7, 0))


def test_intervalo_fora_da_faixa_cai_no_padrao():
    for valor in (0, 99, None, "abc"):
        perfil = PerfilFake(frequencia="horas", intervalo_horas=valor,
                            hora_envio="07:00",
                            ultimo_envio=datetime(2026, 8, 31, 7, 0))
        # qualquer que seja o saneamento, 12h depois já pode sair de novo
        assert alerta_devido(perfil, datetime(2026, 8, 31, 19, 0))


def test_semanal_so_sai_no_dia_marcado():
    # 31/08/2026 é segunda (weekday 0)
    ontem = datetime(2026, 8, 30, 7, 0)
    na_segunda = PerfilFake(frequencia="semanal", dia_semana=0,
                            ultimo_envio=ontem)
    na_quarta = PerfilFake(frequencia="semanal", dia_semana=2,
                           ultimo_envio=ontem)
    assert alerta_devido(na_segunda, AGORA)
    assert not alerta_devido(na_quarta, AGORA)


def test_mensal_so_sai_uma_vez_por_mes():
    # Enviado dia 30/08; o dia marcado (5) deste mês já passou e já foi
    # atendido, então nada sai até 05/09.
    perfil = PerfilFake(frequencia="mensal", dia_mes=5,
                        ultimo_envio=datetime(2026, 8, 30, 7, 0))
    assert not alerta_devido(perfil, AGORA)
    assert alerta_devido(perfil, datetime(2026, 9, 5, 7, 0))


def test_mensal_atrasado_sai_assim_que_puder():
    """Perdeu o dia 28 porque o app estava fora do ar: sai no 31."""
    perfil = PerfilFake(frequencia="mensal", dia_mes=28,
                        ultimo_envio=datetime(2026, 7, 28, 7, 0))
    assert alerta_devido(perfil, AGORA)


def test_anual_sai_uma_vez_por_ano():
    perfil = PerfilFake(frequencia="anual", mes_ano=8, dia_mes=20,
                        ultimo_envio=datetime(2025, 8, 20, 7, 0))
    assert alerta_devido(perfil, AGORA)              # 20/08/2026 já passou
    perfil.ultimo_envio = datetime(2026, 8, 20, 7, 0)
    assert not alerta_devido(perfil, AGORA)          # já saiu este ano
    assert alerta_devido(perfil, datetime(2027, 8, 20, 7, 0))


def test_ciclo_vencido_sai_mesmo_fora_do_dia_marcado():
    """App fora do ar no dia certo não pode fazer o alerta sumir."""
    perfil = PerfilFake(frequencia="semanal", dia_semana=2,
                        ultimo_envio=AGORA - timedelta(days=9))
    assert alerta_devido(perfil, AGORA)


def test_respeitar_hora_desligado_ignora_o_relogio():
    perfil = PerfilFake(hora_envio="23:00",
                        ultimo_envio=datetime(2026, 8, 30, 23, 0))
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
    texto, incluidos = alerta.montar_mensagem_perfil(sessao, perfil, [boa],
                                                     host="http://exemplo")
    assert incluidos == [boa]
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
    assert resumo_frequencia(
        PerfilFake(frequencia="horas", intervalo_horas=3)) == \
        "A cada 3h, a partir das 07:00"
    assert resumo_frequencia(PerfilFake(frequencia="semanal", dia_semana=2)) == \
        "Toda quarta-feira, às 07:00"
    assert resumo_frequencia(PerfilFake(frequencia="mensal", dia_mes=5)) == \
        "Todo dia 5 do mês, às 07:00"
    assert resumo_frequencia(
        PerfilFake(frequencia="anual", dia_mes=10, mes_ano=3)) == \
        "Todo dia 10 de março, às 07:00"


# ------------------------------------------------------------------- fuso
def test_agora_segue_o_fuso_do_env_e_nao_o_relogio_do_processo():
    """Regressão: o Railway roda em UTC e o PC do dono estava 3h à frente.

    Com datetime.now() cru, um alerta das 07:00 tocava às 04:00 e uma
    licitação que encerrava às 10:00 era descartada como vencida às 07:00.
    """
    from datetime import timezone
    from zoneinfo import ZoneInfo

    from app.config import agora, config, hoje

    esperado = datetime.now(ZoneInfo(config.TZ)).replace(tzinfo=None)
    assert abs((agora() - esperado).total_seconds()) < 5
    assert agora().tzinfo is None          # comparável com o que o banco guarda
    assert hoje() == esperado.date()

    utc = datetime.now(timezone.utc).replace(tzinfo=None)
    offset = abs((agora() - utc).total_seconds())
    assert 3 * 3600 - 5 < offset < 3 * 3600 + 5   # Fortaleza é UTC-3, sem horário de verão


def test_fuso_invalido_nao_derruba_o_app():
    from app.config import agora, config
    original = config.TZ
    try:
        config.TZ = "Marte/Olympus_Mons"
        assert agora() is not None         # cai no relógio do sistema, mas responde
    finally:
        config.TZ = original


# ------------------------------------------------- divisão da mensagem longa
def test_mensagem_longa_quebra_entre_linhas_e_nao_no_meio_do_link():
    """O link do edital não pode ficar partido entre duas mensagens."""
    from app.alerta import _unidades_telegram, dividir_mensagem
    link = "https://pncp.gov.br/pncp-api/v1/orgaos/12345678000199/compras/2026/7/arquivos/1"
    texto = "\n".join(f"{i}. Objeto {'x' * 200}\n   Baixar: {link}"
                      for i in range(40))
    pedacos = dividir_mensagem(texto)
    assert len(pedacos) > 1
    for p in pedacos:
        assert _unidades_telegram(p) <= 4096
    # o link aparece inteiro tantas vezes quanto no original
    assert sum(p.count(link) for p in pedacos) == texto.count(link)


def test_divisao_nao_perde_nem_duplica_conteudo():
    from app.alerta import dividir_mensagem
    texto = "\n".join(f"linha {i} " + "y" * 300 for i in range(60))
    assert "\n".join(dividir_mensagem(texto)) == texto


def test_conta_emoji_como_o_telegram_conta():
    """Emoji vale 2 unidades: medir com len() do Python estoura o limite."""
    from app.alerta import _unidades_telegram, dividir_mensagem
    linha = "📡 " + "z" * 60
    texto = "\n".join(linha for _ in range(200))
    assert _unidades_telegram(texto) > len(texto)
    for p in dividir_mensagem(texto):
        assert _unidades_telegram(p) <= 4096


def test_linha_gigante_sozinha_e_cortada_na_forca():
    from app.alerta import _unidades_telegram, dividir_mensagem
    pedacos = dividir_mensagem("w" * 12000)
    assert len(pedacos) >= 3
    for p in pedacos:
        assert _unidades_telegram(p) <= 4096
    assert "".join(pedacos) == "w" * 12000


def test_mensagem_curta_sai_num_pedaco_so():
    from app.alerta import dividir_mensagem
    assert dividir_mensagem("oi") == ["oi"]


# ------------------------------------- regressões apontadas pela auditoria
def test_hora_perto_da_meia_noite_nao_faz_o_alerta_sumir():
    """O agendador confere de 10 em 10 min numa grade que depende da hora do
    boot: com envio às 23:55 podia não haver NENHUM tique na janela, e o
    alerta não saía nunca — nem naquele dia, nem em nenhum outro."""
    perfil = PerfilFake(hora_envio="23:55",
                        ultimo_envio=datetime(2026, 8, 30, 23, 55))
    assert not alerta_devido(perfil, datetime(2026, 8, 31, 23, 50))
    # o tique seguinte já é depois da meia-noite: mesmo assim tem de sair
    assert alerta_devido(perfil, datetime(2026, 9, 1, 0, 0))


def test_ultimo_envio_no_futuro_nao_cala_o_alerta():
    """Banco restaurado de outra máquina ou relógio corrigido para trás."""
    perfil = PerfilFake(ultimo_envio=AGORA + timedelta(days=3))
    assert alerta_devido(perfil, AGORA)


def test_urgencia_dispara_fora_da_agenda_quando_o_prazo_fecha_antes():
    """Dispensa achada às 9h que encerra às 17h do mesmo dia não pode esperar
    o alerta de amanhã — amanhã ela já estaria vencida e seria descartada."""
    perfil = PerfilFake(ultimo_envio=datetime(2026, 8, 31, 7, 0))
    assert not alerta_devido(perfil, AGORA)          # fora da agenda
    fecha_hoje = MatchFake(LicFake("2026-08-31T17:00:00"))
    fecha_depois = MatchFake(LicFake("2026-10-01T17:00:00"))
    assert tem_urgencia(perfil, [fecha_hoje], AGORA)
    assert not tem_urgencia(perfil, [fecha_depois], AGORA)


def test_proximo_horario_e_sempre_depois_de_agora():
    for freq in ("horas", "diario", "semanal", "mensal", "anual"):
        perfil = PerfilFake(frequencia=freq)
        assert horario_previsto(perfil, AGORA) <= AGORA
        assert proximo_horario_previsto(perfil, AGORA) > AGORA


def test_excedente_do_limite_nao_e_queimado(monkeypatch):
    """Só o que entrou na mensagem vira 'avisado'. O resto fica para o
    próximo alerta em vez de sumir para sempre."""
    from app import alerta
    monkeypatch.setattr(alerta, "enviar_telegram", lambda t: True)
    monkeypatch.setattr(alerta, "enviar_email", lambda t: False)
    muitos = [MatchFake(_lic_completa(f"2026-10-{d:02d}T09:00:00"))
              for d in range(1, 26)]
    perfil = PerfilFake()
    enviou, quantidade = alerta.enviar_alerta_perfil(
        SessaoFake(muitos), perfil, agora=AGORA)
    assert enviou
    assert quantidade == alerta.LIMITE_POR_PERFIL
    marcados = [m for m in muitos if m.notificado]
    assert len(marcados) == alerta.LIMITE_POR_PERFIL
    assert len(muitos) - len(marcados) == 25 - alerta.LIMITE_POR_PERFIL
