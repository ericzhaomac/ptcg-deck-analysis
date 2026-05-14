FROM python:3.11-slim

WORKDIR /app

COPY services/deck_analysis_service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

RUN mkdir -p /data/config
VOLUME ["/data"]

EXPOSE 8010

CMD ["uvicorn", "services.deck_analysis_service.app.main:app", "--host", "0.0.0.0", "--port", "8010"]
