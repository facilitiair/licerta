"""Testes dos prazos em dias úteis — as contas que a IA nunca faz.
Datas reais de 2026 conferidas no calendário."""
from datetime import date

from app.acompanhamento import prazos


def test_pascoa_e_moveis_de_2026():
    assert prazos.pascoa(2026) == date(2026, 4, 5)
    feriados = prazos.feriados_nacionais(2026)
    assert date(2026, 2, 17) in feriados     # Carnaval (terça)
    assert date(2026, 4, 3) in feriados      # Paixão de Cristo
    assert date(2026, 6, 4) in feriados      # Corpus Christi
    assert date(2026, 11, 20) in feriados    # Consciência Negra


def test_fim_de_semana_e_feriado_nao_sao_uteis():
    assert not prazos.e_dia_util(date(2026, 9, 5))   # sábado
    assert not prazos.e_dia_util(date(2026, 9, 7))   # Independência
    assert prazos.e_dia_util(date(2026, 9, 8))       # terça comum


def test_dias_uteis_entre_pula_o_sete_de_setembro():
    # seg 31/08 -> ter 08/09: 01,02,03,04 (qui/sex) + 08 = 5 úteis
    assert prazos.dias_uteis_entre(date(2026, 8, 31), date(2026, 9, 8)) == 5
    assert prazos.dias_uteis_entre(date(2026, 8, 31), date(2026, 8, 31)) == 0
    assert prazos.dias_uteis_entre(date(2026, 9, 10), date(2026, 9, 1)) == 0


def test_recuo_do_artigo_164_atravessa_feriado():
    """Sessão na quarta 09/09: 3 dias úteis antes = qui 03/09 (o recuo pula
    o fim de semana E o feriado de 07/09)."""
    assert prazos.recuar_dias_uteis(date(2026, 9, 9), 3) == date(2026, 9, 3)


def test_recuo_de_segunda_cai_na_sexta():
    assert prazos.recuar_dias_uteis(date(2026, 9, 14), 1) == date(2026, 9, 11)


def test_bloco_da_ficha():
    p = prazos.prazos_da_sessao(date(2026, 9, 9), hoje=date(2026, 8, 31))
    assert p["dias_uteis_restantes"] == 6
    assert p["limite_impugnacao"] == date(2026, 9, 3)
    assert not p["sessao_passou"] and not p["impugnacao_passou"]


def test_sessao_passada_e_impugnacao_vencida():
    p = prazos.prazos_da_sessao(date(2026, 8, 20), hoje=date(2026, 8, 31))
    assert p["sessao_passou"] and p["impugnacao_passou"]
    assert p["dias_uteis_restantes"] == 0


def test_limite_hoje_ainda_nao_passou():
    """Impugnação com limite HOJE ainda dá tempo — até o fim do expediente."""
    p = prazos.prazos_da_sessao(date(2026, 9, 3), hoje=date(2026, 8, 31))
    assert p["limite_impugnacao"] == date(2026, 8, 31)
    assert not p["impugnacao_passou"]


def test_sem_sessao_sem_bloco():
    assert prazos.prazos_da_sessao(None, hoje=date(2026, 8, 31)) is None
