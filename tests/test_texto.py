"""Testes da normalização de texto da interface (UI §6)."""
from app.texto import sentenca


def test_texto_gritado_vira_sentence_case():
    assert sentenca("CONTRATAÇÃO DE EMPRESA ESPECIALIZADA") == \
        "Contratação de empresa especializada"


def test_siglas_conhecidas_sobrevivem():
    assert sentenca("REGISTRO DE PREÇOS (SRP) PARA ME/EPP CONFORME CND") == \
        "Registro de preços (SRP) para ME/EPP conforme CND"


def test_texto_bem_escrito_fica_em_paz():
    original = "Contratação de empresa para manutenção de ar-condicionado"
    assert sentenca(original) == original


def test_frases_recomecam_com_maiuscula():
    assert sentenca("OBJETO: OBRA CIVIL. INCLUI MATERIAL.") == \
        "Objeto: obra civil. Inclui material."


def test_vazio_e_none_nao_quebram():
    assert sentenca("") == ""
    assert sentenca(None) is None
    assert sentenca("123 456") == "123 456"
