"""Sensor principal do acompanhamento: lê a caixa do cliente via OAuth (somente leitura).

- Allowlist de remetentes de portais; o resto da caixa NEM É LIDO.
- Classificação via LLM barato (camada 1) -> alerta/prazo.
- Tokens criptografados em repouso (TOKEN_ENCRYPTION_KEY).
"""
