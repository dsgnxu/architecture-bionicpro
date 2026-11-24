FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
COPY wheels ./wheels

# Offline install from pre-downloaded wheels (avoids flaky DNS in build containers)
RUN pip install --no-cache-dir --no-index --find-links=./wheels -r requirements.txt \
    && rm -rf ./wheels

COPY app ./app

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
