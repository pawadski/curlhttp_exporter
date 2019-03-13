FROM pawadski/curlhttp-exporter

COPY config.yml /config.yml
COPY exporter.py /exporter.py

EXPOSE 10080

CMD ["python", "/exporter.py"]