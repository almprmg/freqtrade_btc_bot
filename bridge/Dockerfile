FROM python:3.11-slim

RUN pip install --no-cache-dir psycopg[binary]==3.2.3

WORKDIR /app
COPY freqtrade_to_trad_bridge.py /app/

CMD ["python", "-u", "/app/freqtrade_to_trad_bridge.py"]
