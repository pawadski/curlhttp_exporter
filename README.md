Curl HTTP exporter for Prometheus. Provides some useful information such as curl error numbers, to give you some more insight as to why a request might have failed.

## Metrics

The reported metrics are configurable in `config.yml` and represent metrics from `CURL_EASY_GETINFO`: https://curl.haxx.se/libcurl/c/curl_easy_getinfo.html   

This metric is always reported:
- curl_errno

By default these additional metrics are reported:
- namelookup_time
- connect_time
- starttransfer_time
- total_time
- response_code
- appconnect_time
- pretransfer_time
- redirect_time
- redirect_count
- size_download
- speed_download
- speed_upload
- request_size
- header_size
- ssl_verifyresult
- os_errno

Metrics are prefixed by `curlhttp_`

## More SSL Certificate Metrics Information

The following variables control SSL behavior:
```
  opt_certinfo: 1
  ssl_verifypeer: 0
  ssl_verifyhost: 0
```
Configuring opt_certinfo will enable the exporter to produce information about SSL certificates, the expiry time, start time and expiry state as separate metrics. You can group them by the unique signature extracted from the certificate. Example output:
```
curlhttp_certinfo{target="https://expired.badssl.com/",subject_c="GB",subject_st="Greater Manchester",subject_l="Salford",subject_o="COMODO CA Limited",subject_cn="COMODO RSA Certification Authority",issuer_c="GB",issuer_st="Greater Manchester",issuer_l="Salford",issuer_o="COMODO CA Limited",issuer_cn="COMODO RSA Certification Authority",version="2",start_date="2010-01-19 00:00:00 GMT",expire_date="2038-01-18 23:59:59 GMT",signature="0a:.......:74:"} 1
curlhttp_certinfo_expire_date{target="https://expired.badssl.com/",signature="0a:.......:74:"} 2147468399
curlhttp_certinfo_start_date{target="https://expired.badssl.com/",signature="0a::.......:74:"} 1263855600
curlhttp_certinfo_expired{target="https://expired.badssl.com/",signature="0a::.......:74:"} 1
```

## Use case

I use this exporter to monitor website availability from multiple locations, similarly to how you'd use the BlackBox Exporter.

## Using

Use Docker, really.   

If you cannot use Docker, please ensure your environment meets the tested dependencies:
- Python 3.6
- pycurl 7.43.0.2
- pyopenssl 19.1.0
- urllib3 1.25.8
- pyyaml 5.3.1   

System packages:
- libcurl 7.69.1 (on CentOS 7, this can be fetched from CityFan repo, issue #5)
- openssl 1.0.2

## Configuring

Edit `config.yml`. Options in the file are documented.

## Building (Docker)

You can build and run manually, or use the `build-run` script to wipe and create the exporter image.

## Quickstart (Docker)

1. `git clone https://github.com/pawadski/curlhttp_exporter.git`
2. `cd curlhttp_exporter`
3. `bash build-run`

Then check port 10080 or `docker logs curlhttp_exporter`

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
