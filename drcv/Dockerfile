FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY backend/requirements*.txt backend/
RUN pip install --no-cache-dir -r backend/requirements.txt -r backend/requirements-ocr.txt -r backend/requirements-postgres.txt
COPY backend backend
COPY frontend/dist frontend/dist
WORKDIR /app/backend
ENV DRCV_HOST=0.0.0.0 DRCV_NO_BROWSER=1
EXPOSE 8000
CMD ["python", "run.py"]
