"""Rotina diária para a nuvem (GitHub Actions): coleta + alerta, uma vez.

Uso: python -m app.rotina
As credenciais (Telegram/SMTP) vêm de variáveis de ambiente — nos Actions,
dos Secrets do repositório.
"""
import logging
import os

from .alerta import enviar_alertas_devidos
from .coleta import coletar
from .db import criar_tabelas
from .seed import semear
from .sincronizar import baixar_do_site

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")

SITE = os.environ.get(
    "APP_URL", "https://radar-editais-production-67c1.up.railway.app")

if __name__ == "__main__":
    criar_tabelas()
    semear()
    # Puxa os perfis do site antes de tudo: o app publicado é onde o Paulo
    # edita, e sem isto o e-mail alertava por critérios velhos. Melhor
    # esforço — precisa do secret APP_SENHA no GitHub; sem ele, só avisa.
    if os.environ.get("APP_SENHA"):
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
