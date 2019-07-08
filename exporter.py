#!/usr/bin/env python3.6
#
#  simple exporter based on curl & simplehttpserver
#  code based on implementation from https://docs.python.org/2/library/multiprocessing.html
#

import os, sys, json, yaml, pycurl, dateparser
import urllib.parse

from multiprocessing import Process, current_process
from http.server import HTTPServer
from http.server import BaseHTTPRequestHandler

class RequestHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        # we steal these values from the server
        self.curl_attributes = args[2].config_curl_attributes
        self.curl_options = args[2].config_curl_options
        self.daemon_options = args[2].config_daemon_options

        for option in ['access_log', 'webserver_debug']:
            if self.daemon_options[option] is not False:
                setattr(self, option, True)
            else:
                setattr(self, option, False)
        
        super(RequestHandler, self).__init__(*args, **kwargs)
        

    def set_curl_options(self, curl_handle):
        curl_handle.setopt(pycurl.WRITEFUNCTION, lambda x: None)

        for name, value in self.curl_options.items():
            # first, check if this property name exists
            attr = None
            try:
                attr = getattr(pycurl, name.upper())
            except AttributeError:
                raise 

            if type(value) in [int, float]:
                curl_handle.setopt(attr, value)

            if type(value) == str:
                # check if this maps to a property
                try:
                    prop = getattr(pycurl, value.upper())
                except AttributeError:
                    # it's ok, we'll use a string value
                    prop = value

                curl_handle.setopt(attr, prop)

    def log_request(self, code, *args):
        if self.access_log is True:
            print (f'{self.client_address[0]} [{self.date_time_string()}] "{self.command} {self.path} {self.protocol_version}" {code}')

    def log_debug(self, debug_message):
        if self.webserver_debug is True:
            print (f'{debug_message}')

    def parse_target(self):
        if self.path == '/tracemalloc':
            return 'tracemalloc'

        try:
            location, params = self.path.split('?', 1)
        except:
            self.log_debug("No target specified")
            return None 

        try:
            target_addr = params.split('=', 1)[1]
        except:
            self.log_debug("Unable to parse target")
            return None

        target_addr = urllib.parse.unquote(target_addr)

        if not target_addr.startswith('http://') and not target_addr.startswith('https://'):
            return f"http://{target_addr}"

        return target_addr

    def get_ssl_info(self, handle):
        explode = ['subject', 'issuer']        # to sort into a sub-dict
        dates = ['start_date', 'expire_date']
        strings = ['version', 'signature', 'public key algorithm', 'serial number', 'signature algorithm']

        certStats = []
        for certificate in handle.getinfo(pycurl.INFO_CERTINFO):
            cert = { 'metrics': {}, 'labels': {} }
            for item in certificate:
                attribute = item[0].replace(' ', '_').lower()

                if attribute in explode:
                    for entry in item[1].split(','):
                        entry = entry.strip()
                        key, value = entry.split('=')
                        key = key.strip()
                        value = value.strip()
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

    def probe_go(self, target):
        probe_metrics = { 'curl_errno': 0, 'opt_certinfo': {} }

        curl_handle = pycurl.Curl()
        curl_handle.setopt(pycurl.URL, target)
        self.set_curl_options(curl_handle)

        try:
            curl_handle.perform()
        except pycurl.error as e:
            probe_metrics['curl_errno'] = e.args[0]
            curl_handle.close()
            return probe_metrics

        for stat in config_curl_attributes:
            try:
                attr = getattr(curl_handle, stat.upper())
                attr = curl_handle.getinfo( attr )
            except AttributeError:
                attr = "NaN" 

            probe_metrics[stat] = attr

        if self.curl_options['opt_certinfo'] is 1:
            if target.startswith('https://'):
                probe_metrics['opt_certinfo'] = self.get_ssl_info(curl_handle)

        curl_handle.close()

        return probe_metrics

    def make_metrics_blob(self, metrics, target):
        blob = []
        for metric, value in metrics.items():
            if metric is not 'opt_certinfo':
                blob.extend(
                    [
                        f'# TYPE curlhttp_{metric} gauge',
                        f'# HELP curlhttp_{metric} https://curl.haxx.se/libcurl/c/curl_easy_getinfo.html',
                        f'curlhttp_{metric}{{target="{target}"}} {value}'
                    ]
                )
            else:
                blob.extend(
                    [ 
                        '# TYPE curlhttp_certinfo gauge',
                        '# HELP curlhttp_certinfo Details from curl certinfo'
                    ]
                )

                for certificate in value:
                    labels = ','.join([f'{key}="{value}"' for key, value in certificate['labels'].items()])
                    blob.extend(
                        [
                            f'curlhttp_certinfo{{target="{target}",{labels}}} 1',
                            f'curlhttp_certinfo_expire_date{{target="{target}",signature="{certificate["labels"]["signature"]}"}} {certificate["metrics"]["expire_date"]}',
                            f'curlhttp_certinfo_start_date{{target="{target}",signature="{certificate["labels"]["signature"]}"}} {certificate["metrics"]["start_date"]}'
                        ]
                    )
                    
        blob.append("\n")

        return "\n".join(blob)


#    def get_tracemalloc(self):
#        snapshot = tracemalloc.take_snapshot()
#        top_stats = snapshot.statistics('lineno')

#        del snapshot
        
#        print ("\n\nStats requested:\n")

#        for stat in top_stats[:100]:
#            print (stat)

#        return "Stats logged to console\n"

    def do_GET(self, *args):
        response_code = 200
        response_message = 'OK'
        body = ''

        target = self.parse_target()

#        if target is "tracemalloc":
#            response_code = 200
#            body = self.get_tracemalloc()
        if target is not None:
            metrics = self.probe_go(target)
            body = self.make_metrics_blob(metrics, target)
        else:
            response_code = 400
            response_message = 'Bad Request'

        self.send_response(response_code, response_message)
        self.end_headers()
        self.wfile.write(body.encode('utf-8'))

        return 

class ExporterServer(HTTPServer):
    pass 

def serve_forever(server):
    print ("Starting worker...")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass 

def runpool(address, curl_attributes, curl_options, daemon_options):
    # create a single server object -- children will each inherit a copy
    server = ExporterServer(address, RequestHandler)
    server.config_curl_attributes = curl_attributes
    server.config_curl_options = curl_options
    server.config_daemon_options = daemon_options

    # create child processes to act as workers
    for i in range(daemon_options['max_threads']-1):
        Process(target=serve_forever, args=(server,)).start()

    # main process also acts as a worker
    serve_forever(server)

def start_exporter(curl_attributes, curl_options, daemon_options):
    DIR = os.path.join(os.path.dirname(__file__), '..')
    os.chdir(DIR)
    
    runpool(
        address = (
            '0.0.0.0',
            daemon_options['port']
        ), 
        daemon_options = daemon_options,
        curl_attributes = curl_attributes,
        curl_options = curl_options
    )

if __name__ == '__main__':
    # read config
    stream = open(f"config.yml", "r")

    docs = yaml.load_all(stream)
    for doc in docs:
        config_curl_attributes = doc['curl_attributes']
        config_curl_options = doc['curl_settings']
        config_daemon_options = doc['options']

    stream.close()

    start_exporter(
        curl_attributes = config_curl_attributes,
        curl_options = config_curl_options,
        daemon_options = config_daemon_options
    )
