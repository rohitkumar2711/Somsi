FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# One worker by default: jobs live in this process's memory, so a job must be
# read back from the same worker. Scale with nginx `ip_hash` + WEB_CONCURRENCY>1
# (see deploy/nginx.conf), or keep it at 1 - a single async worker already holds
# thousands of waiting requests.
ENV WEB_CONCURRENCY=1 \
    OUTBOUND_CONCURRENCY=64 \
    SHEET_CONCURRENCY=200 \
    CACHE_TTL=1800 \
    CACHE_SIZE=5000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/healthz',timeout=4).status==200 else 1)"

CMD ["sh", "-c", "uvicorn app.api:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY} --log-level warning"]
