Curl HTTP exporter for Prometheus. Provides some useful metrics similar to the BlackBox exporter, but includes some useful information such as curl error numbers, to give you some more insight as to why a request might have failed.

# Configure

Edit `config.yml`

# Build and run

You can build and run manually, or use the `build-run` script to wipe and create the exporter image.

# Quickstart

1. `git clone https://github.com/pawadski/curlhttp-exporter.git`
2. `bash build-run`

Then check port 10080 or `docker logs curlhttp-exporter`
