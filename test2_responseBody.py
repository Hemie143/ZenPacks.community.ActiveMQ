from __future__ import print_function

import base64
from sys import argv
from pprint import pformat

from twisted.internet.task import react
from twisted.web.client import Agent, readBody
from twisted.web.http_headers import Headers


def cbRequest(response):
    print('Response version:', response.version)
    print('Response code:', response.code)
    print('Response phrase:', response.phrase)
    print('Response headers:')
    print(pformat(list(response.headers.getAllRawHeaders())))
    d = readBody(response)
    d.addCallback(cbBody)
    return d

def cbBody(body):
    print('Response body:')
    print(body)

def main(reactor):
    agent = Agent(reactor)

    url = 'http://10.1.40.15:8161/api/jolokia/read/org.apache.activemq:type=Broker,brokerName=*/BrokerName,BrokerVersion,BrokerId,Queues'
    basic_auth = base64.encodestring('{}:{}'.format('admin', 'admin'))
    auth_header = "Basic " + basic_auth.strip()

    headers = {"Accept": ['application/json'],
               "Authorization": [auth_header],
               }

    d = agent.request(
        b'GET', url,
        Headers(headers),
        None)
    d.addCallback(cbRequest)
    return d

react(main)