FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/data PORT=8080
WORKDIR /app
COPY server/app.py /app/app.py
COPY server/records.py /app/records.py
COPY server/coaching.py /app/coaching.py
COPY server/messaging.py /app/messaging.py
COPY server/nutrition_sources.py server/menu_coach.py server/patient_profile.py /app/
COPY assets/data/taco_4ed.json /app/taco_4ed.json
COPY LICENSE NOTICE.md /app/legal/
COPY assets/data/TACO-NOTICE.txt /app/legal/TACO-NOTICE.txt
RUN groupadd --gid 10001 nutri && useradd --uid 10001 --gid nutri --no-create-home nutri && mkdir /data && chown nutri:nutri /data
USER nutri
EXPOSE 8080
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3)" || exit 1
CMD ["python", "/app/app.py"]
