"""Tela /config: grava o .env e aplica as mudanças sem reiniciar o app."""
import os

from .config import RAIZ, _hora, config

CAMINHO_ENV = os.path.join(RAIZ, ".env")

# Chaves editáveis pela interface, na ordem em que aparecem no arquivo
CHAVES = ["APP_SENHA", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
          "EMAIL_ATIVO", "SMTP_HOST", "SMTP_PORT", "SMTP_USER",
          "SMTP_PASSWORD", "EMAIL_DESTINO", "TZ",
          "HORA_COLETA", "HORA_ALERTA", "DIAS_JANELA_FUTURA"]


def valores_atuais():
    return {
        "APP_SENHA": config.APP_SENHA,
        "TELEGRAM_BOT_TOKEN": config.TELEGRAM_BOT_TOKEN,
        "TELEGRAM_CHAT_ID": config.TELEGRAM_CHAT_ID,
        "EMAIL_ATIVO": "true" if config.EMAIL_ATIVO else "false",
        "SMTP_HOST": config.SMTP_HOST,
        "SMTP_PORT": str(config.SMTP_PORT),
        "SMTP_USER": config.SMTP_USER,
        "SMTP_PASSWORD": config.SMTP_PASSWORD,
        "EMAIL_DESTINO": config.EMAIL_DESTINO,
        "TZ": config.TZ,
        "HORA_COLETA": "%02d:%02d" % config.HORA_COLETA,
        "HORA_ALERTA": "%02d:%02d" % config.HORA_ALERTA,
        "DIAS_JANELA_FUTURA": str(config.DIAS_JANELA_FUTURA),
    }


def salvar(novos):
    """Reescreve o .env e atualiza o objeto config em memória."""
    valores = valores_atuais()
    valores.update({c: str(novos.get(c, valores[c])).strip() for c in CHAVES
                    if c in novos})
    with open(CAMINHO_ENV, "w", encoding="utf-8") as f:
        f.write("# Gerado pela tela /config do Radar de Licitações\n")
        for chave in CHAVES:
            f.write(f"{chave}={valores[chave]}\n")

    # Aplica em memória (sem reiniciar)
    config.APP_SENHA = valores["APP_SENHA"]
    config.TELEGRAM_BOT_TOKEN = valores["TELEGRAM_BOT_TOKEN"]
    config.TELEGRAM_CHAT_ID = valores["TELEGRAM_CHAT_ID"]
    config.EMAIL_ATIVO = valores["EMAIL_ATIVO"].lower() == "true"
    config.SMTP_HOST = valores["SMTP_HOST"]
    try:
        config.SMTP_PORT = int(valores["SMTP_PORT"] or 587)
    except ValueError:
        config.SMTP_PORT = 587
    config.SMTP_USER = valores["SMTP_USER"]
    config.SMTP_PASSWORD = valores["SMTP_PASSWORD"]
    config.EMAIL_DESTINO = valores["EMAIL_DESTINO"]
    config.HORA_COLETA = _hora(valores["HORA_COLETA"], (6, 0))
    config.HORA_ALERTA = _hora(valores["HORA_ALERTA"], (7, 0))
    try:
        config.DIAS_JANELA_FUTURA = int(valores["DIAS_JANELA_FUTURA"] or 90)
    except ValueError:
        config.DIAS_JANELA_FUTURA = 90
    return valores
