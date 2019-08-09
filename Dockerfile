FROM python:3

ADD scraper.py /

RUN pip install psycopg2-binary kafka-python

ENTRYPOINT ["python", "./scraper.py"]
