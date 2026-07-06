FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Render передаёт свой PORT через переменную окружения во время запуска контейнера
EXPOSE 8080

CMD ["python", "main.py"]
