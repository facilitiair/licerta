"""Tela /config: grava o .env e aplica as mudanças sem reiniciar o app."""
import os

from .config import CAMINHO_ENV, _fuso_valido, _hora, _inteiro, config

# Chaves editáveis pela interface, na ordem em que aparecem no arquivo
CHAVES = ["APP_SENHA", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
          "EMAIL_ATIVO", "SMTP_HOST", "SMTP_PORT", "SMTP_USER",
          "SMTP_PASSWORD", "EMAIL_DESTINO", "TZ",
          "HORA_COLETA", "HORAS_ENTRE_COLETAS", "HORA_ALERTA",
          "DIAS_JANELA_FUTURA", "ANTHROPIC_API_KEY"]


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
        "HORAS_ENTRE_COLETAS": str(config.HORAS_ENTRE_COLETAS),
        "HORA_ALERTA": "%02d:%02d" % config.HORA_ALERTA,
        "DIAS_JANELA_FUTURA": str(config.DIAS_JANELA_FUTURA),
        # A chave de IA vive no ambiente (ia/cliente.py a lê na hora da
        # chamada), não no objeto config — por isso os.environ aqui.
        "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY", ""),
    }


SEGREDOS = {"APP_SENHA", "TELEGRAM_BOT_TOKEN", "SMTP_PASSWORD",
            "ANTHROPIC_API_KEY"}


def _citar(valor):
    """Valor pronto para o .env: entre aspas duplas, com escape.

    Sem aspas, uma senha com ' ou " invalidava a linha (e o leitor
    engolia as seguintes até a próxima aspa), " #" cortava o resto e
    ${x} sumia por interpolação — tudo em silêncio, só no reinício
    seguinte. O leitor em config.py carrega sem interpolar, então o valor
    volta byte a byte.
    """
    return '"' + valor.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _outras_chaves():
    """Chaves que já estão no arquivo e a tela não conhece.

    Sem isto, salvar qualquer horário apagava, por exemplo, o APP_URL que o
    usuário tivesse posto à mão — e todos os alertas passavam a mandar um
    link que não abre no celular, sem nenhum aviso.
    """
    guardadas = {}
    try:
        with open(CAMINHO_ENV, encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if linha and not linha.startswith("#") and "=" in linha:
                    chave, valor = linha.split("=", 1)
                    if chave.strip() not in CHAVES:
                        guardadas[chave.strip()] = valor
    except OSError:
        pass
    return guardadas


def valores_para_tela():
    """Os mesmos valores, mas com os segredos fora do HTML.

    A tela imprimia a senha do painel, o token do Telegram e a senha do e-mail
    dentro do atributo `value`. O `type="password"` só esconde na tela: quem
    abrisse "ver código-fonte" — ou qualquer script rodando na página — lia os
    três em texto puro. Agora só informamos SE existe algo guardado.
    """
    valores = dict(valores_atuais())
    for chave in SEGREDOS:
        valores[f"{chave}_DEFINIDO"] = bool(valores[chave])
        valores[chave] = ""
    return valores


def salvar(novos):
    """Reescreve o .env e atualiza o objeto config em memória."""
    valores = valores_atuais()
    for c in CHAVES:
        if c not in novos:
            continue
        novo = str(novos[c]).strip()
        # Campo de segredo em branco = "mantenha o que já está lá". A tela não
        # devolve mais o valor no HTML, então em branco significa 'não mexi'.
        if not novo and c in SEGREDOS:
            continue
        valores[c] = novo
    # Números, horários e fuso entram no arquivo já validados: um "587a"
    # ou "Brasil" gravado cru passava pela tela e derrubava o app no
    # próximo reinício (mesma classe do "06:99" de antes).
    valores["SMTP_PORT"] = str(_inteiro(valores["SMTP_PORT"], 587, 1, 65535))
    valores["DIAS_JANELA_FUTURA"] = str(
        _inteiro(valores["DIAS_JANELA_FUTURA"], 90, 1, 3650))
    valores["HORAS_ENTRE_COLETAS"] = str(
        _inteiro(valores["HORAS_ENTRE_COLETAS"], 3, 1, 24))
    valores["HORA_COLETA"] = "%02d:%02d" % _hora(valores["HORA_COLETA"],
                                                 (6, 0))
    valores["HORA_ALERTA"] = "%02d:%02d" % _hora(valores["HORA_ALERTA"],
                                                 (7, 0))
    valores["TZ"] = _fuso_valido(valores["TZ"], config.TZ)
    guardadas = _outras_chaves()
    # Escreve num arquivo ao lado e troca de uma vez: abrir o .env com "w"
    # zerava o arquivo ANTES de escrever, e com o disco cheio (31/08/2026)
    # sobrava um .env vazio — senha, token e chaves sumiam no reinício.
    temporario = CAMINHO_ENV + ".tmp"
    with open(temporario, "w", encoding="utf-8") as f:
        f.write("# Gerado pela tela /config da Licerta\n")
        for chave in CHAVES:
            f.write(f"{chave}={_citar(valores[chave])}\n")
        for chave, valor in guardadas.items():
            f.write(f"{chave}={valor}\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporario, CAMINHO_ENV)

    # Aplica em memória (sem reiniciar)
    config.APP_SENHA = valores["APP_SENHA"]
    config.TELEGRAM_BOT_TOKEN = valores["TELEGRAM_BOT_TOKEN"]
    config.TELEGRAM_CHAT_ID = valores["TELEGRAM_CHAT_ID"]
    config.EMAIL_ATIVO = valores["EMAIL_ATIVO"].lower() == "true"
    config.SMTP_HOST = valores["SMTP_HOST"]
    config.SMTP_PORT = int(valores["SMTP_PORT"])
    config.SMTP_USER = valores["SMTP_USER"]
    config.SMTP_PASSWORD = valores["SMTP_PASSWORD"]
    config.EMAIL_DESTINO = valores["EMAIL_DESTINO"]
    config.TZ = valores["TZ"]
    config.HORA_COLETA = _hora(valores["HORA_COLETA"], (6, 0))
    config.HORAS_ENTRE_COLETAS = int(valores["HORAS_ENTRE_COLETAS"])
    config.HORA_ALERTA = _hora(valores["HORA_ALERTA"], (7, 0))
    config.DIAS_JANELA_FUTURA = int(valores["DIAS_JANELA_FUTURA"])
    os.environ["ANTHROPIC_API_KEY"] = valores["ANTHROPIC_API_KEY"]
    return valores
