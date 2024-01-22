
# stdlib Imports
import base64
import json
import logging

from Products.ZenUtils.Utils import prepId
from ZenPacks.community.ActiveMQ.lib.util import StringProtocol

# Zenoss imports
from ZenPacks.zenoss.PythonCollector.datasources.PythonDataSource import PythonDataSourcePlugin

# Twisted Imports
from twisted.internet import reactor
from twisted.internet.defer import returnValue, inlineCallbacks
from twisted.web.client import Agent
from twisted.web.http_headers import Headers

# Setup logging
log = logging.getLogger('zen.PythonAMQBroker')


class ActiveMQBroker(PythonDataSourcePlugin):

    proxy_attributes = (
        'zJolokiaPort',
        'zJolokiaUsername',
        'zJolokiaPassword',
    )

    urls = {
        # 'jolokia': 'http://{}:{}/',
        'brokerhealth': 'http://{}:{}/api/jolokia/read/{},service=Health/CurrentStatus',
        'broker': 'http://{}:{}/api/jolokia/read/{}/UptimeMillis,StorePercentUsage,TempPercentUsage,CurrentConnectionsCount,MemoryPercentUsage',
    }

    @classmethod
    def config_key(cls, datasource, context):
        log.debug('In config_key {} {} {} {}'.format(context.device().id, datasource.getCycleTime(context),
                                                     context.id, 'amq-broker'))
        return (
            context.device().id,
            datasource.getCycleTime(context),
            context.id,
            'amq-broker'
        )

    @classmethod
    def params(cls, datasource, context):
        log.debug('Starting AMQDevice params')
        params = {'objectName': context.objectName}
        log.debug('params is {}'.format(params))
        return params

    @inlineCallbacks
    def collect(self, config):
        log.debug('Starting ActiveMQ Broker collect')

        ip_address = config.manageIp
        if not ip_address:
            log.error("%s: IP Address cannot be empty", device.id)
            returnValue(None)

        ds0 = config.datasources[0]
        basic_auth = base64.encodestring('{}:{}'.format(ds0.zJolokiaUsername, ds0.zJolokiaPassword))
        auth_header = "Basic " + basic_auth.strip()
        headers = {
                   "Accept": ['application/json'],
                   "Authorization": [auth_header],
                   "User-Agent": ["Mozilla/3.0Gold"],
                   "Origin": ["null"],
                   }
        results = {}
        agent = Agent(reactor)

        for datasource in config.datasources:
            object_name = datasource.params['objectName']
            url = self.urls[datasource.datasource].format(ip_address, datasource.zJolokiaPort, object_name)
            try:
                response = yield agent.request('GET', url, Headers(headers))
                results[datasource.datasource] = {}
                results[datasource.datasource]['http_code'] = response.code
                # Jolokia doesn't reply with a Content-Length header.
                proto = StringProtocol()
                response.deliverBody(proto)
                body = yield proto.d
                results[datasource.datasource]['body'] = json.loads(body)
            except Exception, e:
                log.error('%s: %s', datasource.datasource, e)
        returnValue(results)

    def onSuccess(self, result, config):
        log.debug('Success - result is {}'.format(result))

        # TODO: Move following block under next loop, in case of multiple brokers
        data = self.new_data()
        broker_name = config.datasources[0].component
        component = prepId(broker_name)

        # Check that all data has been received correctly
        if 'brokerhealth' in result:
            broker_health = result['brokerhealth']['body']['value']
            if broker_health.startswith('Good'):
                data['values'][component]['health'] = 0
                data['events'].append({
                    'device': config.id,
                    'component': component,
                    'severity': 0,
                    'eventKey': 'AMQBrokerHealth',
                    'eventClassKey': 'AMQBrokerHealth',
                    'summary': 'Broker "{}" - Status is OK'.format(component),
                    'message': broker_health,
                    'eventClass': '/Status/ActiveMQ/Broker',
                    'amqHealth': broker_health
                })
            else:
                data['values'][component]['health'] = 3
                data['events'].append({
                    'device': config.id,
                    'component': component,
                    'severity': 3,
                    'eventKey': 'AMQBrokerHealth',
                    'eventClassKey': 'AMQBrokerHealth',
                    'summary': 'Broker "{}" - Status failure'.format(component),
                    'message': broker_health,
                    'eventClass': '/Status/ActiveMQ/Broker',
                    'amqHealth': broker_health
                })

        if 'broker' in result:
            broker_values = result['broker']['body']['value']
            uptimemillis = broker_values['UptimeMillis']
            data['values'][component]['uptime'] = uptimemillis / 1000 / 60
            data['values'][component]['memoryusage'] = broker_values['MemoryPercentUsage']
            data['values'][component]['storeusage'] = broker_values['StorePercentUsage']
            data['values'][component]['tempusage'] = broker_values['TempPercentUsage']
            data['values'][component]['currentconnections'] = broker_values['CurrentConnectionsCount']

        log.debug('ActiveMQBroker onSuccess data: {}'.format(data))
        return data

    def onError(self, result, config):
        log.error('Error - result is {}'.format(result))
        # TODO: send event of collection failure
        return {}
