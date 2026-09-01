"""Roteamento de modelos por camada (arquitetura §7).

Camada 1 — triagem: classificação barata, alto volume, descarta ~90%.
Camada 2 — extração profunda: a ficha do edital, 1× por versão, global.
Camada 3 — geração sob demanda: peças e respostas, disparadas pelo usuário.

Os nomes ficam AQUI, num lugar só: quando um modelo novo sair, muda-se uma
linha — nunca um prompt, nunca um worker.
"""

TRIAGEM = "claude-haiku-4-5-20251001"
EXTRACAO = "claude-sonnet-5"
GERACAO = "claude-sonnet-5"
# Perícia (parecer completo): o modelo forte — análise que orienta a
# decisão de participar merece o melhor cérebro disponível.
PERICIA = "claude-opus-4-8"

# Preço por milhão de tokens (entrada, saída) — para o log de custo.
# Atualizar junto com os modelos acima.
PRECOS = {
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-opus-4-8": (5.00, 25.00),
}


def custo_usd(modelo, tokens_entrada, tokens_saida):
    entrada, saida = PRECOS.get(modelo, (0.0, 0.0))
    return (tokens_entrada * entrada + tokens_saida * saida) / 1_000_000
