"""Configuração do app: lê o arquivo .env e expõe as opções num objeto único."""
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASTA_DADOS = os.path.join(RAIZ, "data")
os.makedirs(PASTA_DADOS, exist_ok=True)
CAMINHO_DB = os.path.join(PASTA_DADOS, "radar.db")

# O .env da raiz é o de sempre. O de data/ vem depois e tem prioridade porque
# data/ é o volume do Railway: sem ele, tudo que a tela /config grava morre no
# próximo deploy — inclusive a APP_SENHA, e sem senha o painel fica ABERTO na
# internet, mostrando o token do Telegram e a senha do e-mail.
CAMINHO_ENV = os.path.join(PASTA_DADOS, ".env")
load_dotenv(os.path.join(RAIZ, ".env"))
load_dotenv(CAMINHO_ENV, override=True)


def _inteiro(valor, padrao, minimo, maximo):
    """Lê um número do .env, preso a uma faixa segura."""
    try:
        return max(minimo, min(maximo, int(valor)))
    except (TypeError, ValueError):
        return padrao


def _hora(valor, padrao):
    """Interpreta 'HH:MM' do .env; volta ao padrão se estiver malformado.

    A faixa é obrigatória, não zelo: os campos de horário em /config são texto
    livre. Um '06:99' salvo ali virava `minute=99` no agendador, que recusa o
    gatilho — e o app deixava de iniciar, com o valor ruim já gravado no .env.
    Um '25:00' na hora do alerta calava todos os alertas para sempre.
    """
    try:
        h, m = valor.split(":")
        h, m = int(h), int(m)
    except (ValueError, AttributeError):
        return padrao
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return padrao
    return h, m


# Versão do produto — bump manual a cada leva de mudanças relevante.
VERSAO = "0.26.0"


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
    # Cookie só por HTTPS. Ligado quando o app está publicado (o Railway
    # sempre serve por HTTPS); desligado em rede local, onde é http://.
    COOKIE_SEGURO = bool(os.environ.get("RAILWAY_PUBLIC_DOMAIN")
                         or os.environ.get("APP_URL", "").startswith("https://"))
    HORA_COLETA = _hora(os.environ.get("HORA_COLETA"), (6, 0))
    HORA_ALERTA = _hora(os.environ.get("HORA_ALERTA"), (7, 0))
    # Editais saem o dia inteiro. Coletar só de manhã atrasa o aviso em até
    # um dia; repetindo a cada N horas o banco fica fresco o dia todo.
    HORAS_ENTRE_COLETAS = _inteiro(os.environ.get("HORAS_ENTRE_COLETAS"), 3, 1, 24)
    # Faxina: licitação encerrada há mais de N dias sem interação é removida
    # (o banco viaja para o GitHub, que corta o push em 100 MB).
    DIAS_RETER_ENCERRADAS = _inteiro(os.environ.get("DIAS_RETER_ENCERRADAS"),
                                     30, 7, 365)
    # Teto do cache de PDFs de edital em data/editais/. Sem teto, o download
    # automático ENCHEU o volume de 5 GB do Railway em um dia (31/08/2026):
    # disco 100% = até gravar o .env falhava com erro 500.
    EDITAIS_CACHE_MB = _inteiro(os.environ.get("EDITAIS_CACHE_MB"),
                                1024, 100, 100_000)
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
