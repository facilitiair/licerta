"""Configuração do app: lê o arquivo .env e expõe as opções num objeto único."""
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(RAIZ, ".env"))

PASTA_DADOS = os.path.join(RAIZ, "data")
os.makedirs(PASTA_DADOS, exist_ok=True)
CAMINHO_DB = os.path.join(PASTA_DADOS, "radar.db")


def _inteiro(valor, padrao, minimo, maximo):
    """Lê um número do .env, preso a uma faixa segura."""
    try:
        return max(minimo, min(maximo, int(valor)))
    except (TypeError, ValueError):
        return padrao


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
    # Editais saem o dia inteiro. Coletar só de manhã atrasa o aviso em até
    # um dia; repetindo a cada N horas o banco fica fresco o dia todo.
    HORAS_ENTRE_COLETAS = _inteiro(os.environ.get("HORAS_ENTRE_COLETAS"), 3, 1, 24)
    DIAS_JANELA_FUTURA = int(os.environ.get("DIAS_JANELA_FUTURA", "90") or 90)
    # Endereço público do app — usado no rodapé "Ver todas" dos alertas.
    # No Railway, RAILWAY_PUBLIC_DOMAIN já vem preenchido automaticamente.
    APP_URL = (os.environ.get("APP_URL")
               or (f"https://{os.environ['RAILWAY_PUBLIC_DOMAIN']}"
                   if os.environ.get("RAILWAY_PUBLIC_DOMAIN") else None)
               or "http://localhost:8000")


config = Config()

_log = logging.getLogger("radar.config")


def agora():
    """Que horas são AQUI, no fuso do .env — sem tzinfo.

    Nunca use `datetime.now()` direto no app. O relógio do processo não é
    confiável: no Railway o contêiner roda em UTC e no PC do dono ele estava
    3h à frente de Fortaleza. Com `datetime.now()`, um alerta marcado para as
    07:00 tocava às 04:00, e uma licitação que encerrava às 10:00 era
    descartada como vencida às 07:00 — perda silenciosa de oportunidade.

    Devolve datetime ingênuo (sem tzinfo) de propósito: é o que o banco
    guarda em `ultimo_envio`/`coletado_em`, e misturar ingênuo com consciente
    levanta TypeError na comparação.
    """
    try:
        return datetime.now(ZoneInfo(config.TZ)).replace(tzinfo=None)
    except (ZoneInfoNotFoundError, ValueError):
        _log.warning("Fuso '%s' desconhecido; usando o relógio do sistema",
                     config.TZ)
        return datetime.now()


def hoje():
    """A data de hoje no fuso do .env."""
    return agora().date()
