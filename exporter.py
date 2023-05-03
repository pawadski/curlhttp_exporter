#!/usr/bin/env python3
#
#  simple exporter based on curl & simplehttpserver
#  code based on implementation from https://docs.python.org/2/library/multiprocessing.html
#

# tested on:
## package versions
# pycurl               7.43.0.2
# pyOpenSSL            19.1.0
# PyYAML               3.13
# urllib3              1.25.8

import os, yaml, pycurl, datetime
import urllib.parse

from OpenSSL import crypto
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
        # if self.path == '/tracemalloc':
        #     return 'tracemalloc'

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
        certStats = []
        certificates = []

        # parsing SSL issuer as CSV in pycurl seems to be unreliable, for example:
        # ('Subject', 'C=US, ST=CA, L=San Francisco, O=Cloudflare, Inc., CN=sni.cloudflaressl.com')
        #              ^^^ that's invalid CSV! :(
        # so I'm going to pipe the cert through pyOpenSSL and extract relevant info from there
        for certificate in handle.getinfo(pycurl.INFO_CERTINFO):
            cert = {}
            for attribute in certificate:
                if attribute[0].lower() == 'signature':
                    cert['signature'] = attribute[1]
                    continue 

                if attribute[0].lower() == 'cert':
                    cert['cert'] = attribute[1]
                
            certificates.append( cert )

        for certificate in certificates:
            cert = crypto.load_certificate(crypto.FILETYPE_PEM, certificate['cert'])
            
            subject = cert.get_subject()
            issuer = cert.get_issuer()

            cert_blob = { 'metrics': {}, 'labels': { 'signature': certificate['signature'] } }

            has_expired = 0
            if cert.has_expired() == True:
                has_expired = 1

            # optimal output:
            # curlhttp_certinfo{
            #     subject_c="GB",
            #     subject_st="Greater Manchester",
            #     subject_l="Salford",
            #     subject_o="COMODO CA Limited",
            #     subject_cn="COMODO RSA Certification Authority",
            #     issuer_c="GB",
            #     issuer_st="Greater Manchester",
            #     issuer_l="Salford",
            #     issuer_o="COMODO CA Limited",
            #     issuer_cn="COMODO RSA Certification Authority",
            #     version="2",
            #     signature="0a:.......:74:"
            # } 1

            for item in ['c', 'st', 'l', 'o', 'cn']:
                issuer_attr = getattr( issuer, item.upper() )
                if not issuer_attr == None:
                    cert_blob['labels'][ f'issuer_{item}' ] = issuer_attr

                subject_attr = getattr( subject, item.upper() )
                if not subject_attr == None:
                    cert_blob['labels'][ f'subject_{item}' ] = subject_attr

            # for the timestamps:
            #     YYYYMMDDhhmmssZ @ https://www.pyopenssl.org/en/stable/api/crypto.html#OpenSSL.crypto.X509.get_notBefore
            # ex: 19980901120000Z
            asn_pattern = '%Y%m%d%H%M%SZ'

            cert_blob['metrics'] = {
                'start_date': int(datetime.datetime.strptime(cert.get_notBefore().decode(), asn_pattern).timestamp()),
                'expire_date': int(datetime.datetime.strptime(cert.get_notAfter().decode(), asn_pattern).timestamp()),
                'expired': has_expired
            }

            certStats.append(cert_blob)

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

        if self.curl_options['opt_certinfo'] == 1:
            if target.startswith('https://'):
                probe_metrics['opt_certinfo'] = self.get_ssl_info(curl_handle)

        curl_handle.close()

        return probe_metrics

    def make_metrics_blob(self, metrics, target):
        blob = []
        for metric, value in metrics.items():
            if metric != 'opt_certinfo':
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

    # docs = yaml.load_all(stream)
    docs = yaml.load(stream, Loader=yaml.FullLoader)
    config_curl_attributes = docs['curl_attributes']
    config_curl_options = docs['curl_settings']
    config_daemon_options = docs['options']

    stream.close()

    start_exporter(
        curl_attributes = config_curl_attributes,
        curl_options = config_curl_options,
        daemon_options = config_daemon_options
    )
