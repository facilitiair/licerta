"""Licerta — processo web (API + frontend).

Workers rodam em processo separado: `python -m workers.scheduler`.
"""
from fastapi import FastAPI

app = FastAPI(title="Licerta")

# TODO: incluir routers dos módulos conforme forem nascendo
# from app.core.routes import router as core_router
# app.include_router(core_router)


@app.get("/health")
def health():
    return {"status": "ok"}
