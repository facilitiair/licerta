# ESPECIFICAÇÃO — Radar de Licitações (app de monitoramento PNCP)

> **Como usar este arquivo:** salve-o como `SPEC.md` dentro da pasta do projeto e, no Claude Code, digite:
> `Leia o SPEC.md e construa o projeto inteiro seguindo exatamente a especificação. Comece pela Fase 1.`

---

## 1. Objetivo

Aplicativo web pessoal para monitorar licitações públicas em todo o Brasil, a partir da API pública do PNCP, com:

- **Perfis de busca configuráveis pelo usuário** (estado, município, modalidade, objeto/palavras-chave, faixa de valor, ordenação).
- **Coleta automática diária**.
- **Alerta diário** com as licitações novas que casaram com cada perfil.
- **Painel web** para criar/editar perfis e navegar nos resultados.

Usuário único (não há cadastro público). Login simples por senha.

---

## 2. Stack obrigatória

Escolhida para ser simples de manter por quem **não é programador**. Não substitua sem avisar.

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.11+ com **FastAPI** |
| Banco | **SQLite** (arquivo local `data/radar.db`), via SQLAlchemy |
| Interface | Templates **Jinja2 + HTMX + Tailwind (CDN)** — sem build, sem Node |
| Agendador | **APScheduler** dentro do próprio processo (sem cron externo) |
| Alertas | **Telegram Bot** (principal) + **e-mail SMTP** (opcional) |
| Config | Arquivo `.env` |
| Deploy | Rodar com `uvicorn`; incluir `Dockerfile` e instruções para Railway/Render/VPS |

Requisitos: um único comando sobe tudo (`python -m app.main` ou `uvicorn app.main:app`). Sem microserviços, sem fila, sem Redis.

---

## 3. Fonte de dados — API PNCP (regras críticas)

Base: `https://pncp.gov.br/api/consulta` — GET, pública, **sem autenticação**.
Swagger oficial: `https://pncp.gov.br/api/consulta/swagger-ui/index.html`

**Antes de escrever o código, abra o Swagger e confirme os nomes exatos dos campos da resposta.** Não invente nomes de campo.

### 3.1 Endpoints usados

**A) Contratações com propostas em aberto** (principal — são as ainda disputáveis)
```
GET /v1/contratacoes/proposta
```
- Parâmetros: `dataFinal` (AAAAMMDD), `codigoModalidadeContratacao`, `pagina`, `tamanhoPagina`, `uf`, `codigoMunicipioIbge`, `cnpj`
- **ATENÇÃO: este endpoint aceita apenas `dataFinal`. Enviar `dataInicial` aqui causa erro.**

**B) Contratações por data de publicação** (histórico / varredura retroativa)
```
GET /v1/contratacoes/publicacao
```
- Obrigatórios: `dataInicial`, `dataFinal`, `codigoModalidadeContratacao`, `pagina`
- Opcionais: `uf`, `codigoMunicipioIbge`, `cnpj`, `codigoUnidadeAdministrativa`, `codigoModoDisputa`, `tamanhoPagina`

**C) Atas de registro de preços** (`/v1/atas`) — Fase 3, para monitorar atas vigentes passíveis de adesão/carona.

### 3.2 Restrições que definem a arquitetura

1. **Não existe consulta "todas as modalidades" numa chamada só.** É obrigatório informar `codigoModalidadeContratacao`. Para varrer tudo, **itere sobre cada código de modalidade**.
2. **A API não filtra por palavra-chave.** O filtro por objeto é feito **localmente**, no campo de objeto da resposta, depois de baixar os registros. Isso significa: baixe amplo (por UF/modalidade/data), grave tudo no banco, e aplique os filtros de texto no banco.
3. **Paginação:** 50 registros por padrão, até 500 via `tamanhoPagina`. Use 500 e itere até acabar.
4. **Rate limit por IP.** Implemente: pausa de ~300 ms entre chamadas, retry com backoff exponencial (3 tentativas), timeout de 30 s. Se falhar, registre erro no log e siga para a próxima combinação — nunca derrube a rotina inteira.
5. A API cai com alguma frequência. O app deve continuar servindo os dados já gravados no banco e mostrar no painel a data/hora da última coleta bem-sucedida.

### 3.3 Códigos de modalidade

Use esta tabela como padrão, mas **confirme na tabela de domínio do Manual de APIs de Consulta do PNCP e corrija se divergir**:

`1` Leilão eletrônico · `2` Diálogo competitivo · `3` Concurso · `4` Concorrência eletrônica · `5` Concorrência presencial · `6` Pregão eletrônico · `7` Pregão presencial · `8` Dispensa de licitação · `9` Inexigibilidade · `10` Manifestação de interesse · `11` Pré-qualificação · `12` Credenciamento · `13` Leilão presencial

Grave-os numa tabela do banco (`modalidades`) para aparecerem como checkbox na interface.

### 3.4 Municípios

Baixe a lista oficial de municípios do IBGE (`https://servicodados.ibge.gov.br/api/v1/localidades/municipios`) uma vez, na instalação, e grave numa tabela `municipios` (código IBGE, nome, UF). A interface usa essa tabela no seletor de municípios com busca por digitação.

---

## 4. Modelo de dados

### `perfis_busca`
| campo | tipo | observação |
|---|---|---|
| id | int | PK |
| nome | text | ex.: "AC — Piauí" |
| ativo | bool | |
| ufs | json | lista de siglas; vazio = Brasil inteiro |
| municipios_ibge | json | lista de códigos; vazio = todos da UF |
| modalidades | json | lista de códigos; vazio = todas |
| palavras_incluir | json | lista; casa se **qualquer uma** aparecer no objeto |
| palavras_excluir | json | lista; descarta se **qualquer uma** aparecer |
| valor_min / valor_max | decimal | nulo = sem limite |
| somente_srp | bool | só registro de preços |
| ordenacao | text | `abertura_asc`, `encerramento_asc`, `publicacao_desc`, `valor_desc` |
| notificar | bool | entra ou não no alerta diário |
| criado_em | datetime | |

### `licitacoes`
Espelha a resposta do PNCP. Campos mínimos (confirme os nomes no Swagger):
`numero_controle_pncp` (**chave única — use para deduplicar**), `objeto`, `modalidade_codigo`, `modalidade_nome`, `orgao_cnpj`, `orgao_nome`, `unidade_nome`, `municipio_nome`, `uf`, `municipio_ibge`, `numero_compra`, `ano_compra`, `processo`, `valor_total_estimado`, `srp` (bool), `data_publicacao_pncp`, `data_abertura_proposta`, `data_encerramento_proposta`, `link_sistema_origem`, `link_pncp`, `payload_json` (resposta bruta completa), `coletado_em`.

O link para a página no portal deve ser montado no padrão do PNCP a partir de CNPJ do órgão, ano e sequencial — **verifique o formato correto acessando uma licitação real no portal antes de implementar**.

### `perfil_matches`
`perfil_id`, `licitacao_id`, `data_match`, `notificado` (bool), `lido` (bool), `favorito` (bool), `status` (`novo` / `analisando` / `vou_participar` / `descartado`), `anotacao` (text).
Chave única composta (`perfil_id`, `licitacao_id`).

### `coletas_log`
`inicio`, `fim`, `sucesso` (bool), `qtd_novas`, `qtd_erros`, `detalhe_erro`.

---

## 5. Motor de coleta

Rotina `coletar()`:

1. Monta o conjunto de combinações a consultar a partir da **união** dos perfis ativos: UFs distintas × modalidades distintas. (Se algum perfil pedir Brasil inteiro, consulte sem o parâmetro `uf`.)
2. Para cada combinação, chama `/v1/contratacoes/proposta` com `dataFinal` = hoje + 90 dias, paginando até o fim.
3. Faz **upsert** em `licitacoes` por `numero_controle_pncp` (atualiza registros já existentes — editais são retificados com frequência).
4. Roda o **matcher**: para cada perfil ativo, avalia todas as licitações e cria linhas em `perfil_matches` que ainda não existam.
5. Grava em `coletas_log`.

**Matcher — regras de texto:** normalize objeto e palavras-chave (minúsculas, sem acentos) antes de comparar. Suporte a aspas para expressão exata (`"ar condicionado"`) e a curingas simples (`pavimenta*`). Um match exige: passar no filtro geográfico **E** de modalidade **E** de valor **E** ter ao menos uma palavra de inclusão (ou lista vazia) **E** nenhuma palavra de exclusão.

**Agendamento:** APScheduler com dois jobs —
- coleta às **06:00** (America/Fortaleza),
- envio do alerta às **07:00** (America/Fortaleza).

Ambos os horários configuráveis no `.env`. Botão "Coletar agora" no painel dispara a coleta manualmente.

---

## 6. Alerta diário

Envia **um resumo por dia**, agrupado por perfil, contendo apenas matches com `notificado = false`. Após o envio, marca como notificados. Se não houver nada novo, envia uma linha curta informando isso (para você saber que o sistema está vivo).

Formato da mensagem (Telegram, Markdown):

```
📡 Radar de Licitações — 30/08/2026

🔹 PERFIL: AC — Piauí (4 novas)

1. Pregão Eletrônico 023/2026 — Prefeitura de Altos/PI
   Objeto: manutenção preventiva e corretiva de ar-condicionado...
   Valor estimado: R$ 850.233,30 · SRP: sim
   Abertura: 08/09/2026 09:00 · Encerra: 08/09/2026 08:59
   🔗 <link do PNCP>

2. ...

🔹 PERFIL: Pavimentação — MA/PI (1 nova)
...

Ver todas: http://<seu-host>/
```

Trunque o objeto em 180 caracteres. Se um perfil tiver mais de 10 novidades, mostre as 10 primeiras conforme a ordenação do perfil e informe o total restante.

**E-mail:** mesma estrutura em HTML, via SMTP configurado no `.env`. Enviar só se `EMAIL_ATIVO=true`.

---

## 7. Interface web

Todas as páginas em português, layout limpo, responsivo (vou usar no celular).

- **`/` Painel:** cartões com contagem de novidades por perfil, data/hora da última coleta, botão "Coletar agora", lista das últimas 20 licitações captadas.
- **`/perfis`:** lista de perfis com ativar/desativar, editar, duplicar, excluir.
- **`/perfis/novo` e `/perfis/{id}`:** formulário com todos os campos da tabela `perfis_busca`. Seletores de UF (multi) e município (busca por digitação, filtrado pela UF escolhida), checkbox de modalidades, campos de palavras-chave que aceitam vários termos, faixa de valor, ordenação. Botão **"Pré-visualizar"** que roda o matcher contra o banco atual e mostra quantas licitações já gravadas casariam — sem salvar.
- **`/licitacoes`:** tabela com filtro por perfil, status, UF, período e busca livre no objeto. Colunas ordenáveis. Cada linha abre um detalhe com todos os campos, o JSON bruto, links para o PNCP e para o sistema de origem, e controles de status/favorito/anotação.
- **`/config`:** dados do Telegram e e-mail, horários dos jobs, teste de envio ("Enviar mensagem de teste").
- **`/logs`:** histórico de coletas com erros.

Exportação **CSV e XLSX** dos resultados filtrados.

---

## 8. Configuração (`.env`)

```
APP_SENHA=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
EMAIL_ATIVO=false
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
EMAIL_DESTINO=
TZ=America/Fortaleza
HORA_COLETA=06:00
HORA_ALERTA=07:00
DIAS_JANELA_FUTURA=90
```

Gere também um `.env.example` e **nunca** faça commit do `.env`.

---

## 9. Fases de entrega

**Fase 1 — núcleo funcional (entregar e testar antes de seguir)**
Cliente da API PNCP + banco + coleta + matcher + alerta no Telegram + painel e CRUD de perfis. Um perfil de exemplo já cadastrado: UF = PI, modalidades 6 e 8, palavras: `ar condicionado`, `climatização`, `refrigeração`, `split`.

**Fase 2** — filtros avançados na listagem, status/anotações, exportação CSV/XLSX, e-mail, `/logs`, tela de configuração.

**Fase 3** — monitoramento de atas de registro de preços (`/v1/atas`), download automático dos PDFs de edital quando disponíveis na API de documentos do PNCP, e coleta complementar do Mural de Licitações do TCE-PI (`sistemas.tce.pi.gov.br/licitacoesweb/mural`).

---

## 10. Qualidade e entrega

- **Testes:** teste unitário do matcher (palavras com acento, expressão exata, exclusão, faixa de valor) e teste do cliente da API com resposta mockada. Rode os testes e mostre o resultado antes de declarar cada fase concluída.
- **Robustez:** nenhuma exceção pode derrubar o agendador. Todo erro vai para log e para `coletas_log`.
- **README.md** obrigatório, escrito para leigo, com: como instalar, como criar o bot no Telegram e descobrir o `chat_id`, como preencher o `.env`, como rodar local, como publicar no Railway, e como fazer backup do `radar.db`.
- **Comentários no código em português.**
- Ao final de cada fase: liste os arquivos criados, o comando exato para rodar e o que eu preciso testar manualmente.
