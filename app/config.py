"""Configuração do app: lê o arquivo .env e expõe as opções num objeto único."""
import os

from dotenv import load_dotenv

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(RAIZ, ".env"))

PASTA_DADOS = os.path.join(RAIZ, "data")
os.makedirs(PASTA_DADOS, exist_ok=True)
CAMINHO_DB = os.path.join(PASTA_DADOS, "radar.db")


def _hora(valor, padrao):
    """Interpreta 'HH:MM' do .env; volta ao padrão se estiver malformado."""
    try:
        h, m = valor.split(":")
        return int(h), int(m)
    except (ValueError, AttributeError):
        return padrao


class Config:
    APP_SENHA = os.environ.get("APP_SENHA", "")
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
    EMAIL_ATIVO = os.environ.get("EMAIL_ATIVO", "false").lower() == "true"
    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587") or 587)
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    EMAIL_DESTINO = os.environ.get("EMAIL_DESTINO", "")
    TZ = os.environ.get("TZ", "America/Fortaleza")
    HORA_COLETA = _hora(os.environ.get("HORA_COLETA"), (6, 0))
    HORA_ALERTA = _hora(os.environ.get("HORA_ALERTA"), (7, 0))
    DIAS_JANELA_FUTURA = int(os.environ.get("DIAS_JANELA_FUTURA", "90") or 90)


config = Config()
