FROM python:3.11-slim

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

ENV BOT_TOKEN=""

CMD ["python", "bot.py"]

EXPOSE 8080

COPY materials/ ./materials/
