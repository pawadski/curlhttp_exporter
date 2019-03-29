#!/usr/bin/env python3
# install with openssl export PYCURL_SSL_LIBRARY=openssl
# packages: python3-devel openssl-devel
import pycurl, json, yaml, concurrent, dateparser
from datetime import datetime
import time 
import sanic.response
from sanic.log import logger
from sanic import Sanic 

daemon_options = {}
options = {}
stats = {}

def getConfig(path = "config.yml"):
    global stats, options, daemon_options

    stream = open(path, "r")
    docs = yaml.load_all(stream)
    for doc in docs:
        stats = doc['curl_attributes']
        options = doc['curl_settings']
        daemon_options = doc['options']
    stream.close()

def setOptions(handler):
    global options 

    for name, value in options.items():
        # first, check if this property name exists
        attr = None
        try:
            attr = getattr(pycurl, name.upper())
        except AttributeError:
            raise 

        if type(value) in [int, float]:
            handler.setopt(attr, value)

        if type(value) == str:
            # check if this maps to a property
            try:
                prop = getattr(pycurl, value.upper())
            except AttributeError:
                # it's ok, we'll use a string value
                prop = value

            handler.setopt(attr, prop)

def getSslInfo(handler):
    explode = ['subject', 'issuer']        # to sort into a sub-dict
    dates = ['start_date', 'expire_date']
    strings = ['version', 'signature', 'public key algorithm', 'serial number', 'signature algorithm']

    certStats = []
    for certificate in handler.getinfo(pycurl.INFO_CERTINFO):
        cert = { 'metrics': {}, 'labels': {} }
        for item in certificate:
            attribute = item[0].replace(' ', '_').lower()

            if attribute in explode:
                for entry in item[1].split(', '):
                    key, value = entry.split(' = ')
                    cert['labels'][ f"{attribute}_{key.lower()}" ] = value
                # cert[item[0]] = dict( k.split('=') for k in item[1].split(', ') )
                continue 
            if attribute in strings:
                cert['labels'][attribute] = item[1]
                continue
            if attribute in dates:
                cert['labels'][attribute] = item[1] # human-readable date
                cert['metrics'][attribute] = int(dateparser.parse(item[1]).timestamp())
                continue
                
        certStats.append(cert)

    return certStats 

def getStats(handler):
    output_stats = { 'stats': {} }

    if 'opt_certinfo' in options.keys():
        output_stats['certinfo'] = getSslInfo(handler)

    for stat in stats:
        try:
            attr = getattr(handler, stat.upper())
            attr = handler.getinfo( attr )
        except AttributeError:
            attr = "NaN" 

        output_stats['stats'][stat] = attr

    return output_stats

def convertToMetrics(addr, data):
    output = []

    if 'certinfo' in data.keys():
        output.append(f'# TYPE curlhttp_certinfo gauge\n# HELP curlhttp_certinfo Details from curl certinfo\n')
        for certificate in data['certinfo']:
            labels = ','.join([f'{key}="{value}"' for key, value in certificate['labels'].items()])
            output.append(f'curlhttp_certinfo{{target="{addr}",{labels}}} 1')
            output.append(f'curlhttp_certinfo_expire_date{{target="{addr}",signature="{certificate["labels"]["signature"]}"}} {certificate["metrics"]["expire_date"]}')
            output.append(f'curlhttp_certinfo_start_date{{target="{addr}",signature="{certificate["labels"]["signature"]}"}} {certificate["metrics"]["start_date"]}')

    for name, value in data['stats'].items():
        output.append(f'# TYPE curlhttp_{name} gauge\n# HELP curlhttp_{name} https://curl.haxx.se/libcurl/c/curl_easy_getinfo.html\ncurlhttp_{name}{{target="{addr}"}} {value}')

    output.append("\n")

    return "\n".join(output)

def handleRequest(addr):
    c = pycurl.Curl()

    setOptions(c)

    c.setopt(pycurl.URL, addr)
    c.setopt(pycurl.WRITEFUNCTION, lambda x: None)

    try:
        content = c.perform()
    except pycurl.error as e:
        c.close()
        print (addr, e.args[1])
        return convertToMetrics(addr, { 'curl_errno': e.args[0] })

    stats = getStats(c)
    stats['stats']['curl_errno'] = 0
    c.close()

    return convertToMetrics(addr, stats)

getConfig()
webServer = Sanic()
executor = concurrent.futures.ThreadPoolExecutor(max_workers=daemon_options['max_threads'])

@webServer.route('/')
async def print_request(request):
    global executor 
    try:
        probe = request.args['target']
    except KeyError:
        logger.warning("Invalid target in request")
        return sanic.response.text("Invalid target in request")

    probe = probe[0]
    data = executor.submit(handleRequest, probe)

    return sanic.response.text(data.result())

if __name__ == '__main__':
    webServer.run(host='0.0.0.0', port=daemon_options['port'], workers=daemon_options['max_threads'])



