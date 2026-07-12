FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY checkin.py .

ENV RUN_MODE=daemon \
    CHECKIN_TIME=08:30

RUN useradd -m app
USER app

CMD ["python", "checkin.py"]
