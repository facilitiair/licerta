# Radar de Licitações — imagem para Railway/Render/VPS
FROM python:3.12-slim

WORKDIR /radar
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
# A camada de IA é pacote irmão de app/ (main.py importa `ia.cliente`).
# Esquecê-la aqui derrubou o site: ModuleNotFoundError no boot = 502 até
# alguém notar. Se nascer outro pacote de topo, ele entra NESTA lista.
COPY ia ./ia
COPY .env.example .

# O banco fica em /radar/data — no Railway, monte um Volume nesse caminho
EXPOSE 8000
# Railway/Render injetam a porta na variável PORT; local usa 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
