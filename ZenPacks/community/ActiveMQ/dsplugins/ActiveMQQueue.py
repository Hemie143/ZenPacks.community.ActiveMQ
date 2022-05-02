
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
log = logging.getLogger('zen.PythonAMQQueue')


class ActiveMQQueue(PythonDataSourcePlugin):

    proxy_attributes = (
        'zJolokiaPort',
        'zJolokiaUsername',
        'zJolokiaPassword',
    )

    urls = {
        'broker': 'http://{}:{}/api/jolokia/read/{},service=Health/CurrentStatus',
        'queue': 'http://{}:{}/api/jolokia/read/{}/ConsumerCount,DequeueCount,EnqueueCount,ExpiredCount,QueueSize,AverageMessageSize,MaxMessageSize',
        }

    # TODO: check config_key queue
    @classmethod
    def config_key(cls, datasource, context):
        log.debug('In config_key {} {} {} {}'.format(context.device().id, datasource.getCycleTime(context),
                                                     context.id, 'amq-queue'))
        return (
            context.device().id,
            datasource.getCycleTime(context),
            context.id,
            'amq-queue'
        )

    @classmethod
    def params(cls, datasource, context):
        log.debug('Starting AMQQueue params')
        params = {}
        params['objectName'] = context.objectName
        params['brokerName'] = context.brokerName
        if hasattr(context, 'queueSize'):
            # First method based on property, but shouldn't update as quickly as the others
            # queueSize = context.queueSize()
            # Second method, based on getRRDValue, therefore reading the RRD file (slower, normally)
            # queueSize = context.getRRDValue('queue_queueSize', cf="LAST")
            # Third method, fetching the latest value from the cache, but it's not refreshing as fast as expected
            queueSize = context.cacheRRDValue('queue_queueSize')
            params['queueSize'] = queueSize
        log.debug('params is {}'.format(params))
        return params

    @staticmethod
    def html_unescape(s):
        s = s.replace("&ast;", "*")
        s = s.replace("&lt;", "<")
        s = s.replace("&gt;", ">")
        return s

    @inlineCallbacks
    def collect(self, config):
        log.debug('Starting AMQQueue collect')

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
                   }
        results = {}
        agent = Agent(reactor)

        for datasource in config.datasources:
            object_name = datasource.params['objectName']
            if '&' in object_name:
                object_name = self.html_unescape(object_name)
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

        ds0 = config.datasources[0]

        # TODO: what if multiple brokers
        data = self.new_data()
        ds0 = config.datasources[0]
        queue_name = ds0.component
        component = prepId(queue_name)
        ds_data = {}

        if 'queue' in result:
            # TODO: check http_code and/or status ?
            values = result['queue']['body']['value']

            if 'ConsumerCount' not in values:
                log.error('AAA Component {} - no ConsumerCount: {}'.format(component, values))

            '''
            if 'ConsumerCount' not in values:
                mbean = result['queue']['body']['request']['mbean']
                for k, v in values.items():
                    if self.html_unescape(k) == mbean:
                        values = v
                        break
                else:
                    continue
            '''

            data['values'][component]['consumerCount'] = values['ConsumerCount']
            data['values'][component]['enqueueCount'] = values['EnqueueCount']
            data['values'][component]['dequeueCount'] = values['DequeueCount']
            data['values'][component]['expiredCount'] = values['ExpiredCount']
            data['values'][component]['averageMessageSize'] = values['AverageMessageSize']
            data['values'][component]['maxMessageSize'] = values['MaxMessageSize']

            queueSize = float(values['QueueSize'])
            if ds0.template == 'ActiveMQQueueDLQ':
                queueSize_prev = ds0.params.get('queueSize', queueSize)
                if queueSize_prev == 'Unknown':
                    queueSize_prev = queueSize
                else:
                    queueSize_prev = float(queueSize_prev)
                log.debug(
                    'DLQ QueueSize {}/{}: Size:{} - Prev:{}'.format(config.id, component, queueSize, queueSize_prev))
                queueSizeDelta = queueSize - queueSize_prev
                data['values'][component]['queueSizeDelta'] = queueSizeDelta
                if queueSizeDelta > 0:
                    severity = 2
                    summary = 'There is a new message in the DLQ {}'.format(component)
                    message = 'There is a new message in the DLQ {}\r\nTotal number of messages: {}'.format(component,
                                                                                                            queueSize)
                else:
                    severity = 0
                    summary = 'There is no new message in the DLQ {}'.format(component),
                    message = 'There is no new message in the DLQ {}\r\nTotal number of messages: {}'.format(component,
                                                                                                             queueSize)

                data['events'].append({
                    'device': config.id,
                    'component': component,
                    'severity': severity,
                    'eventKey': 'AMQQueueDLQ_{}'.format(queueSize),
                    'eventClassKey': 'AMQQueueDLQDelta',
                    'summary': summary,
                    'message': message,
                    'eventClass': '/Status/ActiveMQ/DLQ',
                })
            data['values'][component]['queueSize'] = queueSize
        log.debug('ActiveMQQueue onSuccess data: {}'.format(data))
        return data

    def onError(self, result, config):
        log.error('Error - result is {}'.format(result))
        # TODO: send event of collection failure
        return {}
