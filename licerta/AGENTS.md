# Regras para agentes de IA neste repositório

1. Leia `licerta-arquitetura.md` antes de criar ou mover qualquer arquivo. A estrutura de módulos é intencional.
2. Dependência flui de quem consome para o ativo global: `radar` pode importar de `editais`; `editais` NUNCA importa de `radar`.
3. Módulo não importa modelo de outro módulo diretamente — use interfaces finas ou eventos.
4. LLM lê texto; código calcula. NUNCA use LLM para calcular prazos, dias úteis, validades ou valores.
5. Toda chamada a LLM passa por `ia/cliente.py`. Prompts vivem em `ia/prompts/`, nunca inline no código.
6. Toda query de dado de cliente filtra `empresa_id` por padrão.
7. Edital/ata/análise são dados GLOBAIS (processados 1x, servidos a todos). Nunca duplique por cliente.
8. Proibido: login automatizado em portais, robô de lances, resolução de CAPTCHA, custódia de credencial gov.br.
9. Todo worker novo precisa de detector de falha correspondente em `workers/watchdog.py`.
10. Peças jurídicas geradas saem SEMPRE marcadas como minuta com aviso de revisão obrigatória.
