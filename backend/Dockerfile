FROM python:3.11.9-slim

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/app/.hf

WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY backend/ .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
