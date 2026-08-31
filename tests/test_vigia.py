"""Testes do vigia: cada jeito conhecido de falha silenciosa e o
anti-fadiga dos avisos (surge → avisa; dura → relembra 1×/dia; some →
resolvido). As checagens são funções puras; a máquina de estados roda
contra um SQLite em memória para não sujar o banco real."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import vigia
from app.db import Base, VigiaProblema

AGORA = datetime(2026, 8, 31, 12, 0)
SUBIU_ONTEM = AGORA - timedelta(days=1)


class ColetaFake:
    def __init__(self, fim_ha_horas, sucesso=True, novas=10, erro=""):
        self.fim = AGORA - timedelta(hours=fim_ha_horas)
        self.inicio = self.fim - timedelta(minutes=30)
        self.sucesso = sucesso
        self.qtd_novas = novas
        self.qtd_erros = 0 if sucesso else 1
        self.detalhe_erro = erro


class PerfilFake:
    def __init__(self, **campos):
        self.nome = "Teste"
        self.frequencia = "diario"
        self.intervalo_horas = 3
        self.ultimo_envio = AGORA - timedelta(hours=2)
        self.criado_em = AGORA - timedelta(days=30)
        self.__dict__.update(campos)


# ------------------------------------------------------------ coleta parada
def test_coleta_recente_nao_e_problema():
    ultimo_ok = AGORA - timedelta(hours=2)
    assert vigia.checar_coleta_parada(ultimo_ok, True, AGORA,
                                      SUBIU_ONTEM, 3) is None


def test_coleta_parada_apos_dois_ciclos_perdidos():
    ultimo_ok = AGORA - timedelta(hours=10)      # limite com passo 3h = 6h
    p = vigia.checar_coleta_parada(ultimo_ok, True, AGORA, SUBIU_ONTEM, 3)
    assert p and p["chave"] == "coleta_parada" and "10h" in p["titulo"]


def test_boot_recente_tem_carencia():
    """PC ficou dias desligado: ao religar, coleta velha é normal."""
    ultimo_ok = AGORA - timedelta(days=4)
    subiu_agora = AGORA - timedelta(minutes=20)
    assert vigia.checar_coleta_parada(ultimo_ok, True, AGORA,
                                      subiu_agora, 3) is None


def test_sem_perfil_ativo_nao_ha_o_que_vigiar():
    assert vigia.checar_coleta_parada(None, False, AGORA,
                                      SUBIU_ONTEM, 3) is None


def test_nunca_coletou_conta_do_inicio_do_processo():
    p = vigia.checar_coleta_parada(None, True, AGORA, SUBIU_ONTEM, 3)
    assert p and "desde que o app subiu" in p["detalhe"]


# ---------------------------------------------------------- coleta falhando
def test_uma_falha_isolada_nao_avisa():
    ultimas = [ColetaFake(1, sucesso=False, erro="PI/mod 6: timeout"),
               ColetaFake(4, sucesso=True)]
    assert vigia.checar_coleta_falhando(ultimas) is None


def test_duas_falhas_seguidas_avisam_com_o_ultimo_erro():
    ultimas = [ColetaFake(1, sucesso=False, erro="erro geral: WAF bloqueou"),
               ColetaFake(4, sucesso=False, erro="idem"),
               ColetaFake(7, sucesso=True)]
    p = vigia.checar_coleta_falhando(ultimas)
    assert p and p["chave"] == "coleta_falhando"
    assert "WAF bloqueou" in p["detalhe"] and "2" in p["titulo"]


def test_interrupcao_por_reinicio_nao_e_fonte_falhando():
    """PC de desenvolvimento reinicia o app no meio da coleta o tempo todo;
    isso não pode virar alarme de fonte quebrada."""
    from app.radar.coleta import MSG_INTERROMPIDA
    ultimas = [ColetaFake(1, sucesso=False, erro=MSG_INTERROMPIDA),
               ColetaFake(4, sucesso=False, erro=MSG_INTERROMPIDA),
               ColetaFake(7, sucesso=True)]
    assert vigia.checar_coleta_falhando(ultimas) is None


def test_reinicio_no_meio_nao_quebra_a_sequencia_de_falhas_reais():
    from app.radar.coleta import MSG_INTERROMPIDA
    ultimas = [ColetaFake(1, sucesso=False, erro="erro geral: WAF"),
               ColetaFake(2, sucesso=False, erro=MSG_INTERROMPIDA),
               ColetaFake(4, sucesso=False, erro="erro geral: WAF")]
    p = vigia.checar_coleta_falhando(ultimas)
    assert p and "WAF" in p["detalhe"]


def test_falha_antiga_seguida_de_sucesso_nao_avisa():
    ultimas = [ColetaFake(1, sucesso=True),
               ColetaFake(4, sucesso=False), ColetaFake(7, sucesso=False)]
    assert vigia.checar_coleta_falhando(ultimas) is None


# ---------------------------------------------------------- captura zerada
def test_coletas_ok_sem_gravar_nada_em_24h_e_suspeito():
    ultimas = [ColetaFake(2), ColetaFake(8), ColetaFake(14)]
    p = vigia.checar_captura_zerada(ultimas, frescas_24h=0, agora_=AGORA)
    assert p and p["chave"] == "captura_zerada"


def test_banco_sendo_tocado_esta_saudavel():
    ultimas = [ColetaFake(2), ColetaFake(8)]
    assert vigia.checar_captura_zerada(ultimas, 4200, AGORA) is None


def test_uma_unica_coleta_ok_ainda_nao_conclui_nada():
    ultimas = [ColetaFake(2), ColetaFake(30)]   # a 2ª já saiu da janela
    assert vigia.checar_captura_zerada(ultimas, 0, AGORA) is None


# --------------------------------------------------------- alertas travados
def test_alerta_diario_despachado_ontem_esta_bem():
    p = PerfilFake(ultimo_envio=AGORA - timedelta(hours=20))
    assert vigia.checar_alertas_travados([p], AGORA, SUBIU_ONTEM) is None


def test_alerta_diario_parado_ha_tres_dias_avisa():
    p = PerfilFake(nome="Ar-condicionado — PI",
                   ultimo_envio=AGORA - timedelta(days=3))
    prob = vigia.checar_alertas_travados([p], AGORA, SUBIU_ONTEM)
    assert prob and "Ar-condicionado — PI" in prob["detalhe"]


def test_pausa_noturna_da_frequencia_horas_nao_e_travamento():
    """1/1h com 1º envio às 07:00: o gap da madrugada beira 24h e é normal."""
    p = PerfilFake(frequencia="horas", intervalo_horas=1,
                   ultimo_envio=AGORA - timedelta(hours=13))
    assert vigia.checar_alertas_travados([p], AGORA, SUBIU_ONTEM) is None


def test_frequencia_horas_parada_alem_da_noite_avisa():
    p = PerfilFake(frequencia="horas", intervalo_horas=1,
                   ultimo_envio=AGORA - timedelta(hours=30))
    assert vigia.checar_alertas_travados([p], AGORA, SUBIU_ONTEM)


def test_ultimo_envio_no_futuro_nao_e_assunto_do_vigia():
    p = PerfilFake(ultimo_envio=AGORA + timedelta(hours=5))
    assert vigia.checar_alertas_travados([p], AGORA, SUBIU_ONTEM) is None


def test_carencia_de_uma_hora_apos_o_boot():
    p = PerfilFake(ultimo_envio=AGORA - timedelta(days=3))
    subiu_agora = AGORA - timedelta(minutes=10)
    assert vigia.checar_alertas_travados([p], AGORA, subiu_agora) is None


# ------------------------------------------- máquina de estados do vigiar()
@pytest.fixture()
def sessao_memoria():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


@pytest.fixture()
def vigia_controlado(monkeypatch, sessao_memoria):
    """vigiar() com diagnóstico e canais dublados: `problemas` é o que o
    diagnóstico dirá; `enviados` acumula as mensagens; `canal_ok` simula
    canal fora do ar."""
    estado = {"problemas": [], "enviados": [], "canal_ok": True}
    monkeypatch.setattr(vigia, "diagnosticar",
                        lambda *a, **k: list(estado["problemas"]))
    def falso_aviso(_s, texto, resumo=""):
        estado["enviados"].append(texto)
        return estado["canal_ok"]
    monkeypatch.setattr(vigia, "_avisar_admins", falso_aviso)
    estado["rodar"] = lambda quando: vigia.vigiar(quando,
                                                  sessao_db=sessao_memoria)
    return estado


PROBLEMA = {"chave": "coleta_parada", "titulo": "A coleta parou",
            "detalhe": "há 10h sem coleta"}


def test_problema_novo_avisa_e_fica_registrado(vigia_controlado, sessao_memoria):
    vigia_controlado["problemas"] = [PROBLEMA]
    vigia_controlado["rodar"](AGORA)
    assert len(vigia_controlado["enviados"]) == 1
    reg = sessao_memoria.get(VigiaProblema, "coleta_parada")
    assert reg and reg.avisado_em == AGORA


def test_problema_persistente_so_relembra_apos_24h(vigia_controlado):
    vigia_controlado["problemas"] = [PROBLEMA]
    vigia_controlado["rodar"](AGORA)
    vigia_controlado["rodar"](AGORA + timedelta(hours=1))     # cala
    vigia_controlado["rodar"](AGORA + timedelta(hours=23))    # ainda cala
    assert len(vigia_controlado["enviados"]) == 1
    vigia_controlado["rodar"](AGORA + timedelta(hours=25))    # relembra
    assert len(vigia_controlado["enviados"]) == 2


def test_problema_resolvido_comemora_e_limpa(vigia_controlado, sessao_memoria):
    vigia_controlado["problemas"] = [PROBLEMA]
    vigia_controlado["rodar"](AGORA)
    vigia_controlado["problemas"] = []
    vigia_controlado["rodar"](AGORA + timedelta(hours=1))
    assert "Resolvido" in vigia_controlado["enviados"][-1]
    assert sessao_memoria.query(VigiaProblema).count() == 0


def test_problema_relampago_nunca_avisado_resolve_em_silencio(
        vigia_controlado, sessao_memoria):
    """Canal fora do ar quando surgiu; sumiu antes de conseguir avisar —
    não faz sentido comemorar o que ninguém soube que existiu."""
    vigia_controlado["canal_ok"] = False
    vigia_controlado["problemas"] = [PROBLEMA]
    vigia_controlado["rodar"](AGORA)
    vigia_controlado["problemas"] = []
    vigia_controlado["canal_ok"] = True
    vigia_controlado["rodar"](AGORA + timedelta(hours=1))
    # a 1ª tentativa saiu (e falhou); nenhuma mensagem de "resolvido" depois
    assert len(vigia_controlado["enviados"]) == 1
    assert sessao_memoria.query(VigiaProblema).count() == 0


def test_canal_fora_do_ar_tenta_de_novo_no_proximo_ciclo(vigia_controlado,
                                                         sessao_memoria):
    vigia_controlado["canal_ok"] = False
    vigia_controlado["problemas"] = [PROBLEMA]
    vigia_controlado["rodar"](AGORA)
    reg = sessao_memoria.get(VigiaProblema, "coleta_parada")
    assert reg.avisado_em is None          # ninguém foi avisado de verdade
    vigia_controlado["canal_ok"] = True
    vigia_controlado["rodar"](AGORA + timedelta(minutes=30))
    assert len(vigia_controlado["enviados"]) == 2
    sessao_memoria.refresh(reg)
    assert reg.avisado_em is not None
