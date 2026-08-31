# 📡 Radar de Licitações

Aplicativo pessoal que monitora licitações públicas do Brasil inteiro pela API
oficial do **PNCP**, com perfis de busca configuráveis, coleta automática
diária e alerta no **Telegram**. Construído conforme o `SPEC.md`.

> O PNCP agrega por lei as licitações de todos os portais (Compras.gov.br,
> Licitanet, BLL, BNC, Portal de Compras Públicas, sistemas próprios de
> prefeituras...). Cada licitação mostra o link do sistema de origem.

---

## 1. Como instalar (Windows, Mac ou Linux)

1. Instale o Python 3.11 ou mais novo: https://python.org/downloads
   (no Windows, marque "Add Python to PATH" na instalação).
2. Baixe esta pasta (ou `git clone`), abra o terminal dentro dela e rode:

```
pip install -r requirements.txt
copy .env.example .env        (no Mac/Linux: cp .env.example .env)
```

## 2. Como rodar

```
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Abra **http://localhost:8000** no navegador. Na primeira vez o app baixa a
lista de municípios do IBGE e cria um perfil de exemplo (ar-condicionado no
Piauí). Clique em **"Coletar agora"** para a primeira carga.

A coleta automática roda todo dia às **06:00** e o alerta às **07:00**
(horário de Fortaleza; mude no `.env`). Basta o programa ficar aberto.

## 3. Como criar o bot do Telegram (5 minutos)

1. No Telegram, procure **@BotFather** e envie `/newbot`. Dê um nome
   (ex.: "Meu Radar de Licitações") e um usuário (ex.: `meu_radar_lic_bot`).
2. O BotFather responde com o **token** (algo como
   `7123456789:AAH...xyz`). Copie para `TELEGRAM_BOT_TOKEN=` no `.env`.
3. Envie qualquer mensagem ("oi") para o SEU bot recém-criado.
4. Abra no navegador:
   `https://api.telegram.org/bot<SEU_TOKEN>/getUpdates`
   e procure `"chat":{"id":123456789...` — esse número é o seu
   **chat_id**. Copie para `TELEGRAM_CHAT_ID=` no `.env`.
5. Reinicie o app. Pronto: os alertas chegam no seu Telegram.

### Como configurar cada alerta

Em **Perfis e alertas** cada perfil é também um alerta independente, com:

- **Estados, municípios, modalidades e palavras** — o recorte do que interessa.
- **Situação** — por padrão só *Divulgada* e *Aberta*, as que dá para disputar.
  Cancelada, anulada e revogada ficam de fora.
- **Só o que ainda está em aberto** — descarta o que já passou do prazo de
  proposta. Deixe ligado: é o que impede edital vencido de virar mensagem.
- **Frequência e hora** — várias vezes por dia (a cada 1 a 12 horas, a partir
  de um horário, para não tocar de madrugada), todo dia, uma vez por semana
  (escolhendo o dia), uma vez por mês (escolhendo o dia) ou uma vez por ano
  (dia e mês).
- **Receber alerta deste perfil** — desmarque para o perfil continuar
  garimpando para o painel sem mandar nada no Telegram.

Um ciclo sem nada novo não gera mensagem. O botão **Enviar agora** dispara o
alerta fora da agenda, útil para conferir se está tudo certo.

> **Por que a coleta repete durante o dia:** editais são publicados a qualquer
> hora. Como a coleta pergunta ao PNCP "o que está com proposta aberta agora?",
> nada se perde — mas com uma coleta só de manhã, um edital lançado às 9h só
> apareceria no aviso do dia seguinte, cerca de 22 horas depois. Na base atual
> a mediana da janela de proposta é de quase 15 dias e menos de 1% fecha em
> até 72 horas, então o risco de perder é mínimo; o que se perde é tempo de
> preparação, e é isso que a coleta a cada 3 horas devolve.

> **Dica de recorte:** uma palavra genérica sozinha (ex.: `manutenção`) no modo
> "qualquer uma basta" casa manutenção de elevador, de frota, de prédio.
> Prefira `manutenção + ar condicionado`, que exige as duas no mesmo objeto.

## 4. O arquivo .env (configurações)

| Chave | Para quê |
|---|---|
| `APP_SENHA` | Senha do painel. Vazia só é aceita em rede local — publicado, o app se recusa a abrir sem senha. |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Alertas no Telegram. |
| `EMAIL_ATIVO` + `SMTP_*` | Alerta também por e-mail (opcional, Fase 2). |
| `HORA_COLETA` | Hora da **primeira** coleta do dia (HH:MM). |
| `HORAS_ENTRE_COLETAS` | Repete a coleta de N em N horas (padrão 3; use 24 para uma só). |
| `HORA_ALERTA` | Hora padrão dos alertas que não escolheram uma própria. |
| `DIAS_JANELA_FUTURA` | Busca propostas que encerram em até N dias (padrão 90). |

> **Sobre os campos de segredo na tela de Configurações:** a senha do painel,
> o token do Telegram e a senha do e-mail **não** aparecem mais preenchidos —
> deixá-los em branco mantém o que já está guardado. Só digite algo quando
> quiser de fato trocar. No Railway, essas configurações passam a ser gravadas
> dentro do volume (`data/.env`), então sobrevivem a um redeploy.

**Nunca envie o `.env` para ninguém nem para o GitHub** (o `.gitignore` já
o protege).

## 5. Perfis de busca

Em **Perfis → Novo perfil** você define: estados (nenhum = Brasil inteiro),
municípios (busca por digitação), modalidades, palavras-chave de inclusão e
exclusão (aspas = expressão exata; `pavimenta*` = curinga), faixa de valor,
só-SRP e ordenação. O botão **Pré-visualizar** mostra quantas licitações já
gravadas casariam, sem salvar.

## 6. Publicar na nuvem (Railway)

1. Crie conta em https://railway.app (login com GitHub).
2. "New Project" → "Deploy from GitHub repo" → escolha este repositório
   (o `Dockerfile` é detectado sozinho).
3. Em **Variables**, cadastre as mesmas chaves do seu `.env`.
4. Em **Settings → Volumes**, monte um volume em `/radar/data`
   (é onde vive o banco — sem isso os dados somem a cada deploy).
5. Gere o domínio público em Settings → Networking. Defina `APP_SENHA`!

Render e VPS funcionam igual: é um contêiner Docker comum na porta 8000.

## 6.1 Atas, editais em PDF e Mural TCE-PI (Fase 3)

- **Atas** (menu "Atas"): atas de registro de preços vigentes cujo objeto casa
  com as palavras dos seus perfis — candidatas a adesão/carona. A coleta
  diária varre as atas publicadas/alteradas no PNCP (a primeira vez olha 30
  dias para trás; depois, incremental).
- **PDFs de edital**: quando uma licitação nova casa com um perfil, o app
  baixa automaticamente os documentos publicados (edital e anexos) para
  `data/editais/`. No detalhe da licitação há o botão
  "Buscar documentos no PNCP" para baixar na hora.
- **Mural TCE-PI**: se algum perfil cobrir o Piauí, a coleta também varre o
  Mural de Licitações do TCE-PI (prefeituras que atrasam a publicação
  nacional). Registros próprios aparecem com fonte "tcepi"; duplicados do
  PNCP são descartados. Se o site do TCE mudar, o erro aparece em /logs e o
  resto segue normal.

## 7. Backup

Todo o seu histórico está num único arquivo: **`data/radar.db`**.
Copie-o de vez em quando para um pendrive ou para o Google Drive.
Para restaurar, basta colocar o arquivo de volta em `data/`.

## 8. Testes

```
python -m pytest tests -q
```

## 9. Estrutura

```
app/main.py       servidor web + agendador          app/matcher.py  regras de busca
app/pncp.py       cliente da API do PNCP            app/coleta.py   motor de coleta
app/alerta.py     alerta Telegram                   app/seed.py     cargas iniciais
app/db.py         tabelas (SQLAlchemy)              app/templates/  telas (Jinja2+HTMX)
data/radar.db     SEU BANCO (faça backup!)          tests/          testes automáticos
SPEC.md           especificação completa            Dockerfile      deploy na nuvem
```

### Onde editar os perfis (importante)

O sistema roda em três lugares com três bancos: o site no Railway (manda o
Telegram), o robô do GitHub Actions (manda o e-mail) e o seu PC. **Edite os
perfis no site** — ele é a fonte da verdade. Os outros dois puxam de lá:

- O robô do e-mail sincroniza sozinho antes de cada rodada, desde que o
  secret `APP_SENHA` exista no GitHub (Settings → Secrets → Actions).
- No PC, o `enviar_para_nuvem.bat` sincroniza antes de enviar, e você também
  pode rodar `python -m app.sincronizar` a qualquer momento.

A sincronização atualiza perfis de mesmo nome e cria os que faltam; um
perfil que só existe localmente **nunca** é apagado nem desativado por ela.

### Produção

- **App completo 24h**: https://radar-editais-production-67c1.up.railway.app
  (Railway; confere os alertas a cada 10 min e manda cada um na hora marcada
  no **Telegram**).
- **Robô do GitHub** (`.github/workflows/radar.yml`): roda às 06:00 e manda por
  **e-mail** os alertas cuja frequência venceu — a hora escolhida no perfil não
  vale aqui, porque o robô só acorda uma vez por dia (o Railway bloqueia SMTP
  na plataforma).
- No celular: abra o endereço do app no Chrome → ⋮ → "Adicionar à tela inicial".
