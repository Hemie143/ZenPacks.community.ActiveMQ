import base64

from twisted.web.client import Agent
from twisted.web.http_headers import Headers
from twisted.internet import reactor, ssl

def cbResponse(ignored):
    print('Response received')

def cbShutdown(ignored):
    reactor.stop()

agent = Agent(reactor)

url = 'http://10.1.40.15:8161/api/jolokia/read/org.apache.activemq:type=Broker,brokerName=*/BrokerName,BrokerVersion,BrokerId,Queues'
basic_auth = base64.encodestring('{}:{}'.format('admin', 'admin'))
auth_header = "Basic " + basic_auth.strip()
headers = {"Accept": ['application/json'],
           "Authorization": [auth_header],
           }

d = agent.request('GET', url, Headers(headers))
d.addCallback(cbResponse)
d.addBoth(cbShutdown)

reactor.run()