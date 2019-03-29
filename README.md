Curl HTTP exporter for Prometheus. Provides some useful metrics similar to the BlackBox exporter, but includes some useful information such as curl error numbers, to give you some more insight as to why a request might have failed.

# Configure

Edit `config.yml`

# Build and run

You can build and run manually, or use the `build-run` script to wipe and create the exporter image.

# Quickstart

1. `git clone https://github.com/pawadski/curlhttp-exporter.git`
2. `cd curlhttp-exporter`
3. `bash build-run`

Then check port 10080 or `docker logs curlhttp-exporter`

# Sample Prometheus config

```
- job_name: curlhttp_exporter
    scrape_timeout: 15s
    scrape_interval: 20s
    metrics_path: /
    static_configs:
    - targets:
      - https://www.mysite1.com/
      - https://ihaveasecondsite.com/
    relabel_configs:
    - source_labels: [__address__]
      target_label: __param_target
    - source_labels: [__param_target]
      target_label: instance
    - target_label: __address__
      replacement: IP_ADDR:10080 # exporter location
```
