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

# Regras de UI — Licerta

> Estas regras valem para TODA tela, componente ou ajuste visual. Em caso
> de conflito entre uma instrução pontual e estas regras, estas regras
> vencem — pergunte antes de violar.

## 1. Componentes base (obrigatório)

- Existe UM arquivo de componentes base (`app/templates/_componentes.html`
  + `app/static/tokens.css`): Botão, Card, Badge, Input, Select, Tabela,
  EstadoVazio, Modal.
- **PROIBIDO criar variações locais** de botão, card ou badge dentro de
  uma tela. Se o componente base não atende, altere o componente base —
  nunca crie um paralelo.
- Antes de escrever qualquer HTML/CSS novo, verifique se já existe
  componente para aquilo.

## 2. Tokens de design (usar sempre, nunca valores soltos)

- **Espaçamento:** múltiplos de 8px (8 / 16 / 24 / 32). Nenhum
  padding/margin fora dessa escala.
- **Cores:** definidas uma única vez como variáveis CSS. Paleta: 1 cor
  primária (azul atual), tons de cinza para texto/superfícies, verde
  (sucesso), âmbar (atenção), vermelho (crítico). PROIBIDO introduzir nova
  cor ou novo tom sem alterar o arquivo de tokens.
- **Tipografia:** 1 família de fonte. Tamanhos: 13 / 14 / 16 / 20 / 24px.
  Peso: regular e semibold apenas.
- **Bordas e raio:** raio de 8px em cards e inputs, 6px em botões e
  badges. Sombra: uma única definição, sutil.

## 3. Ícones

- Somente **Lucide**. **PROIBIDO emoji como ícone** em menus, botões,
  badges, KPIs ou títulos.
- Tamanho padrão 16px (inline) e 20px (menu). Cor herda do texto.
- Emoji é permitido apenas dentro de texto de conteúdo educativo, nunca
  como elemento de interface.

## 4. Botões

- **Máximo 1 botão primário por card ou seção** — a ação mais provável.
  Demais ações: botão secundário (outline) ou menu "⋯".
- Ações destrutivas (Excluir, Descartar em massa): nunca na mesma fileira
  dos botões comuns; ficam dentro do menu "⋯" e exigem confirmação.
- Rótulo diz o que acontece: "Salvar interesse", "Gerar minuta" — nunca
  "OK", "Enviar", "Sim".

## 5. Cor vermelha e badges (disciplina rígida)

- **Vermelho é reservado** para: prazo em risco de licitação que o usuário
  marcou "vou participar" e certidão vencendo em ≤ 7 dias. Nada mais é
  vermelho (nem contadores, nem horários de itens não triados, nem
  botões, exceto confirmação destrutiva).
- Badge "novo": apenas itens captados nas últimas 24h **e** que casam com
  um perfil ativo. Nunca em todas as linhas.
- Contadores numéricos no menu/KPIs: apenas quando representam **ação
  pendente do usuário**. Números de estoque total (ex.: milhares de
  editais no banco) não aparecem como KPI.

## 6. Texto e normalização

- Objetos/títulos vindos do PNCP são exibidos em **sentence case**
  (normalizados via função utilitária única); o original em caixa alta
  fica só no banco. Siglas conhecidas (SRP, CND, ME/EPP, UASG)
  preservadas.
- Truncar títulos longos com reticências + tooltip com o texto completo.
- Datas no padrão "hoje 07:30", "amanhã 13:59", "qui 04/09" — nunca
  timestamp cru.
- Valores: "R$ 1,6 mi", "R$ 182 mil". Ausência de valor = célula vazia
  (sem "—" empilhados).

## 7. Linguagem (voz do produto)

- Falamos a língua do cliente leigo, nunca a do sistema. **PROIBIDO na
  interface:** "coleta", "parse", "triagem automática", "calculado por
  código/IA", "job", "worker", "cache", ids técnicos, mensagens de erro
  cruas (stack trace, códigos HTTP).
- Substituições: "Última coleta" → "Atualizado às HH:MM". Erro técnico →
  "Não conseguimos atualizar agora. Tentaremos de novo em instantes."
- Jargão licitatório só quando inevitável, e sempre com micro-explicação
  disponível (tooltip ou bloco de 40s do módulo `conteudo`).
- Nomes de telas: Painel do dia · Oportunidades · Funil de oportunidades ·
  Agenda de disputas · Dossiê da empresa · Minha conta. Não criar novos
  nomes sem aprovação.

## 8. Tabelas e listas

- Colunas com largura mínima definida; texto de órgão/município trunca
  com reticências (nunca quebra palavra a palavra).
- Linhas com altura consistente. Ordenação padrão: mais urgente/relevante
  primeiro.
- Toda lista abre com **filtro padrão sensato** (UF dos perfis ativos +
  situação aberta + encerramento ≤ 30 dias), com filtros visíveis e
  removíveis pelo usuário. A mangueira completa existe, mas nunca é a
  visão inicial.

## 9. Estados obrigatórios de toda tela

Toda tela/listagem nova só está pronta com os 4 estados implementados:
1. **Com dados** (caminho feliz);
2. **Vazio** — com frase útil + próxima ação ("Nenhuma licitação salva
   ainda — veja as oportunidades de hoje" + botão);
3. **Carregando** — skeleton, nunca tela branca;
4. **Erro** — mensagem em linguagem humana + ação de repetir.

## 10. Hierarquia de atenção do produto

- O produto **filtra, não repassa**. KPIs e destaques mostram o acionável
  (matches do perfil, prazos do que ele disputa), nunca o volume bruto.
- Itens descartados: acessíveis por link discreto ("ver descartadas"),
  nunca como coluna/lista de mesmo peso das ativas.
- Máximo de 3–5 itens em destaque no Painel do dia. O resto fica atrás de
  "ver tudo".

## 11. Responsivo

- Toda tela funciona a 380px de largura. Tabelas viram cards empilhados
  no mobile.
- Alvos de toque ≥ 44px. Barra inferior no mobile: Hoje · Oportunidades ·
  Funil · Mais.
- Links de alerta (WhatsApp/e-mail) abrem direto na tela do item
  específico, nunca na home.

## 12. Checklist antes de dar por concluída qualquer mudança de UI

- [ ] Usou apenas componentes base e tokens (nenhuma cor/espaçamento solto)?
- [ ] Nenhum emoji como ícone?
- [ ] No máximo 1 primário por card? Destrutivas escondidas?
- [ ] Vermelho e "novo" dentro das regras da seção 5?
- [ ] Títulos normalizados (sem caixa alta em massa)?
- [ ] Nenhuma linguagem de sistema vazando?
- [ ] Os 4 estados implementados?
- [ ] Testado a 380px?
