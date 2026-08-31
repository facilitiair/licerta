# Licerta

SaaS de licitações para micro e pequenas empresas venderem para o governo sem analista.

- Arquitetura completa: `licerta-arquitetura.md` (leia antes de qualquer mudança estrutural)
- Regras para agentes de IA: `AGENTS.md`

## Rodar (dev)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # preencha as chaves
uvicorn app.main:app --reload          # processo web
python -m workers.scheduler            # processo de workers (outro terminal)
```
