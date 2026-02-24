FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

# Optional: don't hardcode PORT; Cloud Run sets it.
# ENV PORT=8080

CMD ["sh", "-c", "uvicorn app.web.server:app --host 0.0.0.0 --port ${PORT:-8080}"]
