# Radar de Licitações — imagem para Railway/Render/VPS
FROM python:3.12-slim

WORKDIR /radar
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY .env.example .

# O banco fica em /radar/data — monte um volume aqui para persistir
VOLUME ["/radar/data"]

EXPOSE 8000
# Railway/Render injetam a porta na variável PORT; local usa 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
