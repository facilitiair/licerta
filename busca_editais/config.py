import os
import yaml

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARQUIVO_CONFIG = os.path.join(RAIZ, "config.yaml")
ARQUIVO_DB = os.path.join(RAIZ, "editais.db")


def carregar():
    with open(ARQUIVO_CONFIG, encoding="utf-8") as f:
        return yaml.safe_load(f)
