FROM python:3.8

RUN apt-get update && apt-get install openssl curl
RUN pip3.8 install --upgrade pip 
RUN pip3.8 install pycurl pyopenssl pyyaml

RUN mkdir -p /app
COPY config.yml /app/config.yml
COPY exporter.py /app/exporter.py

EXPOSE 10080

WORKDIR /app
CMD ["python3", "exporter.py"]
