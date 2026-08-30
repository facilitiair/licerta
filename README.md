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
5. Reinicie o app. Pronto: o alerta diário chega no seu Telegram.

## 4. O arquivo .env (configurações)

| Chave | Para quê |
|---|---|
| `APP_SENHA` | Senha do painel. Vazia = sem login (só use em casa). |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Alerta diário no Telegram. |
| `EMAIL_ATIVO` + `SMTP_*` | Alerta também por e-mail (opcional, Fase 2). |
| `HORA_COLETA` / `HORA_ALERTA` | Horários dos jobs (HH:MM). |
| `DIAS_JANELA_FUTURA` | Busca propostas que encerram em até N dias (padrão 90). |

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

### Legado (versão anterior)

`radar.py`, `app.py` (Flask), `busca_editais/` e `docs/` são a primeira versão
(site estático em https://facilitiair.github.io/radar-editais/ + coleta via
GitHub Actions). Continuam funcionando de forma independente até você decidir
desativá-los.
