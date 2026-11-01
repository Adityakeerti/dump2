FROM python:3.11.9-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000 \
    HF_HOME=/opt/hf-cache TRANSFORMERS_OFFLINE=0
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# CPU-only torch keeps the image ~1 GB instead of pulling CUDA wheels via sentence-transformers.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.5.1
COPY requirements/base.txt requirements/base.txt
RUN pip install --no-cache-dir -r requirements/base.txt

# Bake the 384-d multilingual E5 model into the image so start-up never depends on the Hub.
ARG EMBED_MODEL=intfloat/multilingual-e5-small
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBED_MODEL}')"

COPY . .
RUN useradd --create-home app && mkdir -p data/uploads && chown -R app /app /opt/hf-cache
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=5 \
  CMD curl -fsS http://localhost:${PORT}/ready || exit 1
ENTRYPOINT ["./docker-entrypoint.sh"]
