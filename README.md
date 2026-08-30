# 📡 Radar de Editais

Aplicativo local para **pesquisar e monitorar licitações públicas** de qualquer
estado e qualquer objeto, com radar automático, dashboard e digest por e-mail.

## O que ele faz

| Parte | O quê |
|---|---|
| **Pesquisar** (dashboard) | Busca livre no PNCP: qualquer palavra, Brasil inteiro, com "salvar no radar" |
| **Radar** (`radar.py`) | Coleta diária do PNCP + Mural TCE-PI, filtra pelo seu perfil e grava novidades |
| **Meu radar** (dashboard) | Lista o que o radar achou; marque interesse, visto ou descarte |
| **Configurações** (dashboard) | Estados, cidades, categorias/termos, exclusões, modalidades, valor mínimo, e-mail |
| **Digest** | E-mail diário com as novidades (ou HTML em `digests/` se e-mail desativado) |

## Como usar

```powershell
pip install -r requirements.txt
python app.py        # dashboard em http://localhost:8765
python radar.py      # coleta manual (o agendador roda isso sozinho)
```

## Fontes de dados

- **PNCP** — API pública de consulta (radar) e API de busca textual (aba Pesquisar).
  Rate-limit tratado com pausa e backoff automático.
- **Mural de Licitações TCE-PI** — raspagem best-effort da aplicação JSF.
  Se o TCE mudar o site, o radar avisa no log e segue só com o PNCP.

## Configuração

Tudo em `config.yaml` (editável também pela aba Configurações do dashboard):

- `ufs: []` = Brasil inteiro; `municipios: []` = todas as cidades
- `categorias:` vazio = **tudo interessa** (radar sem filtro de objeto)
- E-mail: use uma *senha de app* do Gmail (myaccount.google.com/apppasswords)
  e marque `habilitado: true`

## Agendamento

Tarefa do Windows `RadarEditais` roda `python radar.py` todo dia às 08:00
(criada por `instalar_tarefa.ps1`; remova com
`schtasks /delete /tn RadarEditais /f`). O PC precisa estar ligado no horário —
a tarefa roda assim que possível caso ele esteja desligado às 08:00.

## Estrutura

```
radar.py                  coleta + classificação + digest
app.py                    dashboard Flask
config.yaml               configuração (estados, termos, e-mail...)
editais.db                banco SQLite
busca_editais/
  matcher.py              normalização e casamento de termos
  db.py                   esquema e upsert
  digest.py               e-mail/HTML do digest
  fontes/pncp.py          coletor PNCP (API consulta)
  fontes/pncp_busca.py    busca textual PNCP (API do portal)
  fontes/tcepi.py         raspador do Mural TCE-PI
```
