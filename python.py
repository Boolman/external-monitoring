#!/usr/bin/python

import argparse
import psycopg2
from yamlconfig import YamlConfig
from twisted.web.server import Site, NOT_DONE_YET
from twisted.web.resource import Resource
from twisted.internet import reactor
from twisted.internet.task import deferLater
import time
from zabbix_api import ZabbixAPI


class ExternalMonitoring(Resource):
    isLeaf = True

    def __init__(self, args):
        try:
            self.config = YamlConfig(args.config_file)
        except Exception as e:
            raise SystemExit(f'ERROR - {e}')

    def render_GET(self, request):
        path = request.path.decode()
        request.setHeader("Content-Type", "text/plain; charset=UTF-8")
        if path == '/zabbixdb':
            defer = deferLater(reactor, 0, lambda: request)
            defer.addCallback(self.ZabbixDB)
            defer.addErrback(self.errback, request)
            return NOT_DONE_YET
        elif path == '/zabbixapi':
            defer = deferLater(reactor, 0, lambda: request)
            defer.addCallback(self.Zabbix)
            defer.addErrback(self.errback, request)
            return NOT_DONE_YET

        else:
            request.setResponseCode(404)
            return '404'.encode()

    def errback(self, failure, request):
        failure.printTraceback()
        request.processingFailed(failure)
        return None

    def ZabbixDB(self, request):
        """
        self.config['zabbix']['database']['dbname']
        self.config['zabbix']['database']['username']
        self.config['zabbix']['database']['host']
        self.config['zabbix']['database']['port']
        self.config['zabbix']['database']['password']
        """
        try:
            with psycopg2.connect(
                    dbname=self.config['zabbix']['database']['dbname'],
                    user=self.config['zabbix']['database']['username'],
                    password=self.config['zabbix']['database']['password'],
                    host=self.config['zabbix']['database']['host'],
                    port=self.config['zabbix']['database']['port']) as conn:
                with conn.cursor() as curs:
                    curs.execute(
                        "SELECT clock FROM events ORDER BY clock DESC LIMIT 1;"
                    )
                    result = curs.fetchone()
        except Exception as e:
            request.setResponseCode(500)
            request.write(f'DB ERROR: {e}'.encode())
            request.finish()
            return

        if int(result[0]) < (time.time() - (11 * 60)):
            request.setResponsCode(201)
            request.write(f"NOT OK - Last entry in db: {result[0]}".encode())
            request.finish()
            return

        request.write('OK'.encode())
        request.finish()

    def Zabbix(self, request):
        """
        self.config['zabbix']['api']['username']
        self.config['zabbix']['api']['password']
        self.config['zabbix']['api']['server']
        self.config['zabbix']['api']['verify_tls']
        """
        try:
            zapi = ZabbixAPI(
                server=self.config['zabbix']['api']['server'],
                validate_certs=self.config['zabbix']['api']['verify_tls'])
            zapi.login(self.config['zabbix']['api']['username'],
                       self.config['zabbix']['api']['password'])
            hosts = zapi.host.get({
                'monitored_hosts': True,
                'extendoutput': True
            })
        except ZabbixAPIException as e:
            request.setResponseCode(201)
            request.write(f'ERROR {e}'.encode())
            request.finish()
            return

        if len(hosts) < 1:
            request.setResponseCode(201)
            request.write('NOT OK'.encode())
            request.finish()
            return

        request.write('OK'.encode())
        request.finish()


def main():

    parser = argparse.ArgumentParser(description='External Monitoring')
    parser.add_argument(
        '-c',
        '--config',
        dest='config_file',
        default='config.yml',
        help="configuration file")
    parser.add_argument(
        '-p',
        '--port',
        dest='port',
        type=int,
        default=8080,
        help="HTTP port to expose metrics")

    args = parser.parse_args()

    root = Resource()
    root.putChild(b'zabbixdb', ExternalMonitoring(args))
    root.putChild(b'zabbixapi', ExternalMonitoring(args))

    factory = Site(root)
    print(f"Starting web server on port {args.port}")
    reactor.listenTCP(args.port, factory)
    reactor.run()


if __name__ == '__main__':
    main()
