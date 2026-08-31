"""Rotina diária para a nuvem (GitHub Actions): coleta + alerta, uma vez.

Uso: python -m app.rotina
As credenciais (Telegram/SMTP) vêm de variáveis de ambiente — nos Actions,
dos Secrets do repositório.
"""
import logging
import os

from .notificacoes.alerta import enviar_alertas_devidos
from .radar.coleta import coletar
from .db import criar_tabelas
from .seed import semear
from .sincronizar import baixar_do_site
from .vigia import checar_site_publicado

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")

# Endereço do app publicado — vem do ambiente (no GitHub Actions, do env do
# workflow). Nada de URL de uma instalação específica cravada no código: este
# produto roda para qualquer empresa, em qualquer endereço.
SITE = os.environ.get("APP_URL") or None

if __name__ == "__main__":
    criar_tabelas()
    semear()
    if not SITE:
        print("AVISO: APP_URL não definido no ambiente — os links dos "
              "alertas sairão errados e a sincronização de perfis não roda.")
    # Puxa os perfis do site antes de tudo: o app publicado é onde os perfis
    # são editados, e sem isto o e-mail alertava por critérios velhos. Melhor
    # esforço — precisa do secret APP_SENHA no GitHub; sem ele, só avisa.
    if SITE and os.environ.get("APP_SENHA"):
        sincronizado = baixar_do_site(site=SITE)
        print(f"Perfis sincronizados do site: {'sim' if sincronizado else 'NÃO'}")
    else:
        print("APP_SENHA ausente nos secrets: rodando com os perfis do repositório")
    registro = coletar()
    if registro:
        print(f"Coleta: sucesso={registro.sucesso} novas={registro.qtd_novas} "
              f"erros={registro.qtd_erros}")
    # Aqui a hora do perfil não vale: este job roda uma vez por dia, no
    # horário do GitHub Actions. O que continua valendo é a frequência.
    enviados = enviar_alertas_devidos(host=SITE, respeitar_hora=False)
    print(f"Alertas enviados: {enviados}")
    # Vigilância cruzada: o vigia interno do site não enxerga o site fora do
    # ar — só alguém de fora enxerga. Este job roda fora, então confere e
    # avisa os admins (por aqui o e-mail funciona; no Railway, não).
    if SITE:
        ok, detalhe = checar_site_publicado(SITE)
        print(f"Site publicado: {'de pé' if ok else 'FORA DO AR'} — {detalhe}")
