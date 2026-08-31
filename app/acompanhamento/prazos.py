"""Prazos em dias úteis — código determinístico, nunca IA (arquitetura §5).

Um alerta de prazo errado encerra a confiança do cliente, então aqui não
há heurística: feriados nacionais fixos + móveis (Carnaval, Paixão e
Corpus Christi derivam da Páscoa, calculada por Meeus/Butcher). Feriado
estadual/municipal do órgão a gente NÃO conhece — toda resposta que
depende disso avisa que a conta pode recuar um dia.

Referências da Lei 14.133/2021 usadas na ficha:
- art. 164: impugnação/esclarecimento até 3 dias ÚTEIS antes da abertura.
"""
from datetime import date, timedelta


def pascoa(ano):
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher, gregoriano)."""
    a = ano % 19
    b, c = divmod(ano, 100)
    d, e = divmod(b, 4)
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741 — nome do algoritmo
    m = (a + 11 * h + 22 * l) // 451
    mes, dia = divmod(h + l - 7 * m + 114, 31)
    return date(ano, mes, dia + 1)


def feriados_nacionais(ano):
    """Feriados nacionais (Lei 662/1949 e correlatas) + móveis.

    Carnaval (ter) e Corpus Christi não são feriado nacional por lei, mas
    são ponto facultativo federal e feriado na prática em quase todo órgão
    licitante — para prazo, tratar como não útil é o lado SEGURO (o prazo
    limite recua, nunca avança).
    """
    p = pascoa(ano)
    return {
        date(ano, 1, 1), date(ano, 4, 21), date(ano, 5, 1),
        date(ano, 9, 7), date(ano, 10, 12), date(ano, 11, 2),
        date(ano, 11, 15), date(ano, 11, 20),   # Consciência Negra (14.759/23)
        date(ano, 12, 25),
        p - timedelta(days=47),                 # Carnaval (terça)
        p - timedelta(days=48),                 # Carnaval (segunda)
        p - timedelta(days=2),                  # Paixão de Cristo
        p + timedelta(days=60),                 # Corpus Christi
    }


def e_dia_util(dia, feriados=None):
    if dia.weekday() >= 5:
        return False
    return dia not in (feriados if feriados is not None
                       else feriados_nacionais(dia.year))


def dias_uteis_entre(inicio, fim):
    """Dias úteis no intervalo (inicio, fim] — exclusivo no início,
    inclusivo no fim, como se conta 'faltam X dias úteis para a sessão'."""
    if fim <= inicio:
        return 0
    total, dia = 0, inicio
    feriados = feriados_nacionais(inicio.year) | feriados_nacionais(fim.year)
    while dia < fim:
        dia += timedelta(days=1)
        if e_dia_util(dia, feriados):
            total += 1
    return total


def recuar_dias_uteis(referencia, quantidade):
    """A data que fica `quantidade` dias úteis ANTES de `referencia`.

    É a conta do art. 164: o protocolo tem de acontecer ATÉ o fim desse
    dia. Recuar um dia útil de uma segunda-feira cai na sexta anterior.
    """
    dia = referencia
    feriados = (feriados_nacionais(referencia.year)
                | feriados_nacionais(referencia.year - 1))
    restam = quantidade
    while restam > 0:
        dia -= timedelta(days=1)
        if e_dia_util(dia, feriados):
            restam -= 1
    return dia


def prazos_da_sessao(data_sessao, hoje):
    """O bloco de prazos que a ficha exibe — tudo data absoluta.

    Devolve dict com: dias_uteis_restantes, limite_impugnacao (art. 164,
    3 dias úteis antes), impugnacao_apertada (limite em ≤ 2 dias úteis) e
    sessao_passou. O aviso sobre feriado local vai fixo no template.
    """
    if not data_sessao:
        return None
    limite = recuar_dias_uteis(data_sessao, 3)
    return {
        "sessao_passou": data_sessao < hoje,
        "dias_uteis_restantes": dias_uteis_entre(hoje, data_sessao),
        "limite_impugnacao": limite,
        "impugnacao_passou": limite < hoje,
        "dias_uteis_para_impugnar": dias_uteis_entre(hoje, limite),
    }
