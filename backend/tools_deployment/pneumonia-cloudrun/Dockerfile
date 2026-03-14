FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY model ./model

ENV PORT=8080
CMD ["gunicorn", "--timeout", "300", "-b", "0.0.0.0:8080", "app:app"]