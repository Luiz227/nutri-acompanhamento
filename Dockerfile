FROM python:3.13-slim AS pof
WORKDIR /build
COPY tool/import_ibge_pof.py .
RUN pip install --no-cache-dir xlrd==2.0.2 && python import_ibge_pof.py food_pof.json

FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/data PORT=8080
WORKDIR /app
COPY server/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY server/app.py /app/app.py
COPY server/records.py /app/records.py
COPY server/coaching.py /app/coaching.py
COPY server/messaging.py /app/messaging.py
COPY server/nutrition_sources.py server/menu_coach.py server/patient_profile.py /app/
COPY server/portions.py /app/
COPY server/meal_pdf.py /app/
COPY server/food_composition.py /app/
COPY server/pof.py /app/
COPY server/menu_foods.py /app/
COPY server/web_accounts.py server/web_http.py /app/
COPY server/web_features.py /app/
COPY web/ /app/web/
COPY server/meal_pdf_template.py /app/
COPY assets/data/menu-cover-fruit.jpg /app/
COPY assets/data/menu-wheel-breakfast.jpg assets/data/menu-wheel-snack.jpg assets/data/menu-wheel-lunch.jpg /app/
COPY --from=pof /build/food_pof.json /app/
COPY assets/data/food_composition_extra.json /app/
COPY assets/data/FOOD-COMPOSITION-NOTICE.txt /app/legal/
COPY server/photo_meals.py server/daily_progress.py /app/
COPY assets/icon/garfofala-symbol.png /app/garfofala-symbol.png
COPY assets/data/taco_4ed.json /app/taco_4ed.json
COPY LICENSE NOTICE.md /app/legal/
COPY assets/data/TACO-NOTICE.txt /app/legal/TACO-NOTICE.txt
RUN groupadd --gid 10001 nutri && useradd --uid 10001 --gid nutri --no-create-home nutri && mkdir /data && chown nutri:nutri /data
USER nutri
EXPOSE 8080
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3)" || exit 1
CMD ["python", "/app/app.py"]
