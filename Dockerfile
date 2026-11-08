FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=5100
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# SQLite DB + uploads live in /app by default; mount a volume for persistence
EXPOSE 5100
CMD ["python", "serve_online.py"]
