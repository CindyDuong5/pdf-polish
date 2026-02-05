FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

ENV PORT=8080
CMD ["uvicorn", "app.web.server:app", "--host", "0.0.0.0", "--port", "8080"]
