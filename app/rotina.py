"""Rotina diária para a nuvem (GitHub Actions): coleta + alerta, uma vez.

Uso: python -m app.rotina
As credenciais (Telegram/SMTP) vêm de variáveis de ambiente — nos Actions,
dos Secrets do repositório.
"""
from .alerta import enviar_alerta_diario
from .coleta import coletar
from .db import criar_tabelas
from .seed import semear

SITE = "https://facilitiair.github.io/radar-editais/"

if __name__ == "__main__":
    criar_tabelas()
    semear()
    registro = coletar()
    if registro:
        print(f"Coleta: sucesso={registro.sucesso} novas={registro.qtd_novas} "
              f"erros={registro.qtd_erros}")
    enviar_alerta_diario(host=SITE)
