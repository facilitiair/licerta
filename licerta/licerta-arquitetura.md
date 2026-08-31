# Licerta — Arquitetura da Plataforma

**Versão 1.0 · Agosto/2026**
Documento de referência para desenvolvimento. Tudo aqui assume: um desenvolvedor, zero equipe, IA e agentes fazendo o trabalho pesado, custo por cliente controlado desde o dia 1.

---

## 1. Princípios inegociáveis

Estas cinco regras resolvem, antecipadamente, as decisões que mais destroem produtos desse tipo. Quando houver dúvida em qualquer ponto do desenvolvimento, volte aqui.

1. **Processa uma vez, serve para todos.** Edital, ata, análise e histórico de preço são ativos globais da plataforma, nunca dado por cliente. O custo de IA é por documento, não por usuário.
2. **IA lê, código calcula.** LLM extrai informação de texto. Prazo, dia útil, validade de certidão e valor são sempre calculados por código determinístico. Um alerta de prazo errado encerra a confiança do cliente.
3. **E-mail é o sensor; o portal é intocável.** Nada de login automatizado, lance automático, CAPTCHA ou custódia de credencial gov.br. O acompanhamento em tempo real vem da caixa de e-mail do próprio cliente (OAuth) + consultas públicas.
4. **O sistema vigia a si mesmo.** Todo pipeline tem detector de anomalia (captura zerada, parse falhando, campo nulo em massa). Falha silenciosa = cliente perdendo pregão sem ninguém saber.
5. **Peça jurídica é minuta, nunca peça final.** Todo output dos agentes de impugnação/recurso sai marcado como rascunho com aviso de revisão obrigatória.

---

## 2. Arquitetura macro

**Monolito modular + workers.** Uma única aplicação, um único banco, um único deploy — mas dois tipos de processo:

```
┌─────────────────────────────────────────────────────┐
│                      LICERTA                        │
│                                                     │
│  ┌──────────────┐         ┌──────────────────────┐  │
│  │   WEB (API   │         │  WORKERS (agentes)   │  │
│  │  + frontend) │         │  captura · análise   │  │
│  │              │         │  e-mail · validades  │  │
│  │  responde ao │         │  digest · watchdog   │  │
│  │  navegador   │         │                      │  │
│  └──────┬───────┘         └──────────┬───────────┘  │
│         │                            │              │
│         └──────────┬─────────────────┘              │
│                    │                                │
│      ┌─────────────┴──────────────┐                 │
│      │  PostgreSQL  │  Fila/Redis │                 │
│      └────────────────────────────┘                 │
└─────────────────────────────────────────────────────┘
```

- **Web e workers compartilham o mesmo código e o mesmo banco**, mas rodam como processos separados. A análise de 300 editais nunca acontece dentro de um request.
- **Sem microserviços.** Um dev com microserviços passa o dia depurando rede.
- Comunicação entre módulos: chamada de função via interface fina ou evento na fila. **Módulo não importa modelo de outro módulo diretamente.**

### Stack recomendado (se ainda couber mudar)

| Camada | Escolha | Por quê |
|---|---|---|
| Backend | Python + FastAPI | Melhor ecossistema para pipelines de dados + IA; Claude Code é muito produtivo nele |
| Fila | Redis + RQ (ou Celery) | Simples, suficiente, roda no mesmo servidor |
| Banco | PostgreSQL | JSONB para fichas de edital, full-text search nativo, um banco só para tudo |
| Frontend | O que você já tem funcionando | Trocar frontend agora é custo sem retorno; a estrutura abaixo é agnóstica |
| Infra | 1 VPS (web) + 1 VPS (workers) ou um só no início | Railway/Render/Hetzner; evite AWS complexa agora |
| Notificações | E-mail (Resend/SES) + WhatsApp (API oficial via BSP, ex. Z-API/360dialog) | WhatsApp é o canal que o seu cliente realmente lê |

> Se o radar já está em outro stack e funciona, **não migre**. Aplique a estrutura de módulos no que existe.

---

## 3. Estrutura de pastas

```
licerta/
├── app/
│   ├── core/            # empresa, usuário, permissão, plano, notificação
│   │   ├── models.py
│   │   ├── auth.py
│   │   ├── notify.py    # abstração: envia por e-mail/WhatsApp/push
│   │   └── routes.py
│   │
│   ├── ingestao/        # entrada de dados públicos
│   │   ├── pncp.py      # cliente da API do PNCP
│   │   ├── comprasgov.py# dados abertos / consultas públicas
│   │   ├── tce_pi.py    # mural do TCE-PI (fase 2+)
│   │   └── parsers/     # cada fonte tem parser isolado e testável
│   │
│   ├── editais/         # ativo global: o edital analisado
│   │   ├── models.py    # Edital, FichaEdital, VersaoEdital
│   │   ├── analise.py   # orquestra extração via LLM → ficha estruturada
│   │   └── diff.py      # detecção de republicação/alteração
│   │
│   ├── radar/           # matching edital ↔ empresa
│   │   ├── perfil.py    # critérios da empresa (CNAE, valor, região, palavras)
│   │   ├── matching.py  # código puro, sem LLM
│   │   └── digest.py    # composição do resumo diário
│   │
│   ├── acompanhamento/  # sessão, prazos, sensor de e-mail
│   │   ├── email_sensor.py   # OAuth Gmail/Outlook do cliente + parsers
│   │   ├── prazos.py         # cálculo determinístico (dias úteis, feriados)
│   │   ├── fases.py          # polling público best-effort de fase/ata
│   │   └── previsao.py       # previsão de horário do item (atas históricas)
│   │
│   ├── documentos/      # dossiê da empresa cliente
│   │   ├── models.py    # Documento, Validade, ChecklistHabilitacao
│   │   ├── validades.py # vigia de vencimento (código, não IA)
│   │   └── checklist.py # cruza ficha do edital × documentos da empresa
│   │
│   ├── pecas/           # minutas jurídicas (fase tardia)
│   │   ├── impugnacao.py
│   │   ├── recurso.py
│   │   └── contrarrazoes.py
│   │
│   ├── conteudo/        # tutor contextual (micro-ajuda just-in-time)
│   │   ├── blocos/      # cada bloco = 1 arquivo md pequeno e versionado
│   │   └── contexto.py  # decide qual bloco mostrar em qual tela/estado
│   │
│   └── painel/          # a "fila de ações do dia"
│       └── acoes.py     # agrega urgências de todos os módulos
│
├── workers/
│   ├── scheduler.py     # agenda (cron) de todos os jobs
│   ├── jobs/            # um arquivo por agente (ver seção 6)
│   └── watchdog.py      # monitor do próprio pipeline
│
├── ia/
│   ├── cliente.py       # wrapper único de chamadas a LLM (log de custo aqui)
│   ├── prompts/         # prompts versionados em arquivos, nunca inline
│   └── camadas.py       # roteamento barato/caro (ver seção 7)
│
├── tests/
└── migrations/
```

Regra de ouro da estrutura: **`radar` pode ler `editais`, mas `editais` não sabe que `radar` existe.** A dependência flui sempre de quem consome para o ativo global, nunca o contrário.

---

## 4. Modelo de dados essencial

### Dados globais (sem dono — o ativo da Licerta)

| Tabela | Conteúdo | Observação |
|---|---|---|
| `edital` | id PNCP, órgão, UASG, modalidade, objeto, valores, datas, URL, PDF | Fonte da verdade |
| `edital_versao` | snapshot de cada versão publicada | Alimenta o diff de republicação |
| `edital_ficha` | JSONB com a extração estruturada (exigências, prazos, cláusulas de risco) | Gerada 1× por versão via LLM |
| `ata` | atas históricas parseadas, com timestamps de eventos por item | Alimenta previsão de horário e inteligência de preço |
| `resultado_item` | quem venceu, valor, desconto, por órgão | Inteligência de preço |
| `orgao` / `pregoeiro` | perfil de ritmo (itens/hora médio) | Alimenta previsão |

### Dados por cliente (tudo carrega `empresa_id`)

| Tabela | Conteúdo |
|---|---|
| `empresa` | CNPJ, CNAEs, porte, região — **a entidade central; usuário pertence à empresa** |
| `usuario` | login, papel, empresa_id |
| `perfil_radar` | critérios de matching da empresa |
| `interesse` | relação empresa ↔ edital (status: visto/analisando/participando/ganhou/perdeu) |
| `documento_empresa` | certidões, atestados, balanços, com data de validade |
| `conexao_email` | tokens OAuth da caixa do cliente (criptografados) |
| `alerta` | fila de notificações com estado de entrega |

**As duas regras que não podem ser violadas:**
1. Toda query de dado de cliente filtra `empresa_id` **por padrão** (middleware/escopo automático), não por disciplina do programador.
2. Edital nunca é duplicado para dentro do espaço do cliente. O cliente tem `interesse` apontando para o edital global.

---

## 5. Módulos e o que cada um entrega

| Módulo | Entrega ao cliente | Fonte de dado | Usa LLM? |
|---|---|---|---|
| **Radar** | "Saiu edital que serve pra você" | PNCP | Só na análise global (1× por edital) |
| **Editais** | Ficha do edital: exigências, prazos, riscos, resumo | PDF do edital | Sim — o maior custo de IA da plataforma |
| **Acompanhamento** | Alertas de sessão, convocação, republicação, fase; previsão de horário do item | E-mail do cliente + consultas públicas + atas | Parser de e-mail sim (barato); prazos não |
| **Documentos** | "Sua CND vence em 5 dias"; checklist de habilitação por edital | Upload do cliente + ficha do edital | Extração de dados do documento no upload (1×) |
| **Painel** | Fila de ações do dia (máx. 3–5 itens, ordenados por consequência) | Agrega os demais | Não |
| **Peças** | Minutas de impugnação/recurso/contrarrazões | Ficha + contexto do caso | Sim (sob demanda, dá para cobrar à parte) |
| **Conteúdo** | Micro-ajuda contextual de 40s no ponto de fricção | Blocos md próprios | Não em runtime (blocos pré-escritos) |

---

## 6. Agentes (workers) e agenda

| Agente | Frequência | O que faz | Falha detectável |
|---|---|---|---|
| `capturar_pncp` | a cada 2h (madrugada: 1×) | Busca novos editais e alterações no PNCP | Captura zerada vs média móvel |
| `analisar_edital` | fila (disparado pela captura) | Baixa PDF → extrai ficha via LLM → grava `edital_ficha` | Taxa de erro de parse |
| `detectar_republicacao` | junto da captura | Diff de versões → alerta clientes com interesse | — |
| `matching_radar` | após captura | Cruza fichas novas × perfis → cria alertas | Zero matches em dia com captura normal |
| `digest_diario` | 06h30 | Monta e envia o resumo do dia por empresa | Envios falhados |
| `ler_emails` | a cada 5 min | Lê caixas conectadas → classifica e-mails de portal → converte em alerta/prazo | Queda na taxa de classificação |
| `vigiar_validades` | 1× ao dia | Varre `documento_empresa` → alertas 30/15/7/3 dias antes | — |
| `vigiar_fases` | a cada 30 min (só editais com interesse ativo e sessão no dia) | Consulta pública de fase/ata, best-effort | Latência alta → degrada sem alarde |
| `processar_atas` | 1× ao dia | Baixa atas encerradas → parseia eventos → atualiza ritmo de órgão/pregoeiro e `resultado_item` | Taxa de parse |
| `prever_horario` | manhã dos dias com sessão | Estima janela de chamada do item do cliente + alerta H-20min | Intervalo de confiança largo no início — comunicar como estimativa |
| `watchdog` | a cada 15 min | Checa saúde de todos os acima e **te** avisa no WhatsApp | É ele quem detecta |

---

## 7. Uso de IA: camadas e custo

**Camada 1 — Triagem (modelo barato, ex. Haiku).** Classificação de edital ("é obra? porte compatível? região?") e classificação de e-mail ("é convocação? republicação? spam do portal?"). Descarta ~90% do volume antes da camada cara.

**Camada 2 — Extração profunda (modelo forte, ex. Sonnet).** Só para editais que passaram na triagem e têm pelo menos 1 empresa com perfil compatível. Gera a `edital_ficha` completa. **1× por versão de edital, nunca por cliente.**

**Camada 3 — Geração sob demanda (modelo forte).** Minutas de peças e respostas do tutor quando o bloco pré-escrito não cobre. Disparada por ação explícita do usuário — aqui o custo é atribuível e pode ser limitado por plano (ex.: X peças/mês).

**Regras de contenção de custo:**
- Todo call de LLM passa por `ia/cliente.py`, que loga tokens e custo por job → você sabe o custo real por edital e por cliente desde o dia 1.
- Prompts em arquivos versionados (`ia/prompts/`), com exemplos de saída em JSON estrito; parse com validação de schema e retry limitado (2).
- Cache agressivo: mesma pergunta do tutor sobre o mesmo bloco → resposta cacheada.
- Nada de LLM em loop sobre linhas de planilha ou itens de lista quando um prompt único resolve.

---

## 8. Notificações

Um único serviço (`core/notify.py`) com três canais e regras de escalonamento:

- **Digest diário** → e-mail (e resumo no painel).
- **Urgente** (convocação, sessão em 2h, republicação, certidão a 3 dias) → **WhatsApp**.
- **Informativo** → sino no painel.

Regra anti-fadiga: máximo de N WhatsApps/dia por empresa (configurável, padrão 5); o resto agrupa. Cliente que recebe 20 alertas por dia desativa tudo e depois cancela.

---

## 9. Painel — a fila de ações do dia

A tela inicial **não é um menu**; é uma fila ordenada. `painel/acoes.py` coleta candidatos de todos os módulos e ordena por `(consequência de ignorar) × (proximidade do prazo)`:

1. Convocação pendente com prazo de horas → topo absoluto, sempre.
2. Sessão de pregão hoje (com horário previsto do item).
3. Certidão vencendo ≤ 7 dias.
4. Republicação de edital com interesse ativo.
5. Edital novo com match alto.
6. Prazo de impugnação/recurso abrindo ou fechando.

Se não houver nada: "Tudo em dia. Próxima sessão: {data}." — isso também é valor.

Cada ação vem com botão de resolução em 1 clique e, quando fizer sentido, o bloco de micro-ajuda do módulo `conteudo` acoplado ("o que é uma convocação e o que fazer agora — 40s").

---

## 10. Segurança e LGPD (o mínimo que não pode faltar)

- Tokens OAuth de e-mail criptografados em repouso (chave fora do banco); escopo **somente leitura**.
- O sensor de e-mail processa apenas remetentes de portais conhecidos (allowlist); o resto da caixa nem é lido.
- Nunca armazenar senha de portal, certificado digital ou credencial gov.br de cliente. Isso é linha vermelha de produto, não só técnica.
- Log de acesso por `empresa_id`; exportação e exclusão de dados do cliente implementadas desde cedo (são pedidos LGPD que chegarão).
- Backups diários do Postgres testados com restore real 1× por mês.

---

## 11. Roadmap por fases

**F0 — Radar sólido (você já está aqui)**
Captura PNCP → análise → matching → digest por e-mail. Watchdog junto. *Critério de pronto: 2 semanas sem falha silenciosa, custo de IA por edital conhecido.*

**F1 — Acompanhamento (o diferencial)**
Sensor de e-mail (Gmail primeiro) → alertas WhatsApp de convocação/republicação → cálculo de prazos → painel com fila de ações. *É a fase que justifica assinatura.*

**F2 — Documentos**
Upload de certidões com extração de validade → vigia de vencimentos → checklist de habilitação cruzando com a ficha do edital.

**F3 — Inteligência**
Processamento de atas históricas → previsão de horário do item → inteligência de preço por órgão/região. *É a fase que diferencia da concorrência barata.*

**F4 — Peças e conteúdo pleno**
Minutas de impugnação/recurso/contrarrazões (com trava de "minuta") → biblioteca completa de blocos contextuais. *Possível cobrar como add-on.*

Monetização entra no fim da F1: F0+F1 é o produto mínimo vendável ("nunca mais perca uma convocação").

---

## 12. Decisões já tomadas (para não rediscutir)

| Decisão | Resolução |
|---|---|
| Robô de lances | Não. Reavaliar só com produto validado, caixa e assessoria jurídica. |
| Login automatizado em portal | Nunca. |
| Custódia de credencial gov.br | Nunca. |
| Migrar stack do radar atual | Não, reorganizar no que existe. |
| Microserviços | Não. Monolito modular + workers. |
| IA para calcular datas | Nunca. Código determinístico. |
| Análise de edital por cliente | Nunca. 1× global, matching por código. |
| Nome | Licerta (pendente: registro.br + INPI 42/9/35). |
