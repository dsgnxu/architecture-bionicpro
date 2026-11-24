FROM apache/airflow:2.9.1-python3.11

USER root
COPY requirements.txt /requirements.txt
COPY wheels /wheels
RUN pip3 install --no-cache-dir --no-index --find-links=/wheels -r /requirements.txt \
    && rm -rf /wheels
USER airflow
