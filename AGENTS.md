# Regras para agentes de IA neste repositório

1. Leia `docs/arquitetura-plataforma.md` antes de criar ou mover qualquer
   arquivo. A estrutura de módulos é intencional.
2. **Produto genérico:** nada de nenhuma empresa cliente no código, nos
   prompts ou nos dados de exemplo — nem nome, nem CNPJ, nem ramo. O que é
   da empresa entra como dado, pela interface ou como entrada de prompt.
3. LLM lê texto; **código calcula**. Nunca use LLM para calcular prazos,
   dias úteis, validades ou valores.
4. Toda chamada a LLM passa por `ia/cliente.py` (custo logado). Prompts
   vivem em `ia/prompts/`, versionados — nunca inline no código.
5. Edital, ata e análise são dados GLOBAIS: processados 1×, servidos a
   todos. Nunca duplique por cliente.
6. Toda consulta de dado de cliente filtra pelo dono (hoje `usuario_id`;
   quando existir, `empresa_id`) — em toda rota, sem exceção.
7. Relógio: use SEMPRE `app.config.agora()/hoje()` — nunca
   `datetime.now()` (o servidor não está no fuso do Brasil).
8. Proibido: login automatizado em portais, robô de lances, resolução de
   CAPTCHA, custódia de credencial gov.br.
9. Todo worker/job novo precisa de detector de falha correspondente
   (nenhuma falha pode ser silenciosa).
10. Peça jurídica gerada sai SEMPRE marcada como minuta, com aviso de
    revisão obrigatória por advogado.
11. Toda correção de defeito ganha teste de regressão; a suíte
    (`python -m pytest tests -q`) fica verde antes de qualquer commit.
