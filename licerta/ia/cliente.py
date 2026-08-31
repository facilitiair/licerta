"""Wrapper ÚNICO de chamadas a LLM. Toda chamada passa por aqui.

- Loga tokens e custo por job/edital/cliente desde o dia 1.
- Roteia camadas: 1 triagem (barato) / 2 extração (forte) / 3 geração sob demanda.
- Valida saída JSON contra schema; retry máx 2.
"""
