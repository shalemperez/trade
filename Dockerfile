FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default: run backtest. Override with: docker run rsi-bot python bot.py
CMD ["python", "backtest.py"]
