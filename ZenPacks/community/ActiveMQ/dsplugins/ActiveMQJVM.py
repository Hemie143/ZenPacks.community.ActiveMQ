
# stdlib Imports
import base64
import json
import logging
import urllib

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
log = logging.getLogger('zen.PythonAMQJVM')

# https://www.cs.mun.ca/java-api-1.5/guide/management/overview.html

class ActiveMQJVM(PythonDataSourcePlugin):

    proxy_attributes = (
        'zJolokiaPort',
        'zJolokiaUsername',
        'zJolokiaPassword',
    )

    urls = {
        'jvm_memory': 'http://{}:{}/api/jolokia/read/java.lang:type=Memory',
        'jvm_memorypool_codecache': 'http://{}:{}/api/jolokia/read/java.lang:type=MemoryPool,name=Code%20Cache/Usage',
        'jvm_memorypool_compclass': 'http://{}:{}/api/jolokia/read/java.lang:type=MemoryPool,name=Compressed%20Class%20Space/Usage',
        'jvm_memorypool_meta': 'http://{}:{}/api/jolokia/read/java.lang:type=MemoryPool,name=Metaspace/Usage',
        'jvm_memorypool_pseden': 'http://{}:{}/api/jolokia/read/java.lang:type=MemoryPool,name=PS%20Eden%20Space/Usage',
        'jvm_memorypool_psoldgen': 'http://{}:{}/api/jolokia/read/java.lang:type=MemoryPool,name=PS%20Old%20Gen/Usage',
        'jvm_memorypool_pssurvivor': 'http://{}:{}/api/jolokia/read/java.lang:type=MemoryPool,name=PS%20Survivor%20Space/Usage',
    }

    @classmethod
    def config_key(cls, datasource, context):
        log.debug('In config_key {} {} {} {}'.format(context.device().id, datasource.getCycleTime(context),
                                                     context.id, 'amq-jvm'))
        return (
            context.device().id,
            datasource.getCycleTime(context),
            context.id,
            'amq-jvm'
        )

    @classmethod
    def params(cls, datasource, context):
        # TODO: is it required ?
        log.debug('Starting AMQDevice params')
        log.debug('params is {}'.format(params))
        return params

    @inlineCallbacks
    def collect(self, config):
        log.debug('Starting ActiveMQ JVM collect')

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
            url = self.urls[datasource.datasource].format(ip_address, datasource.zJolokiaPort)
            log.debug('XXX url: {}'.format(url))
            try:
                response = yield agent.request('GET', url, Headers(headers))
                results[datasource.datasource] = {}
                results[datasource.datasource]['http_code'] = response.code
                proto = StringProtocol()
                response.deliverBody(proto)
                body = yield proto.d
                results[datasource.datasource]['body'] = json.loads(body)
            except Exception, e:
                log.error('%s: %s', datasource.datasource, e)
        returnValue(results)

    def onSuccess(self, result, config):
        log.debug('Success - result is {}'.format(result))

        data = self.new_data()
        jvm_name = config.datasources[0].component
        component = prepId(jvm_name)
        if 'jvm_memory' in result and result['jvm_memory']['http_code'] < 300:
            jvm_memory_values = result['jvm_memory']['body']['value']
            heap_values = jvm_memory_values['HeapMemoryUsage']
            data['values'][component]['heap_committed'] = heap_values['committed']
            data['values'][component]['heap_max'] = heap_values['max']
            data['values'][component]['heap_used'] = heap_values['used']
            data['values'][component]['heap_used_percent'] = round(float(heap_values['used'])/heap_values['max']*100, 2)
            nonheap_values = jvm_memory_values['NonHeapMemoryUsage']
            data['values'][component]['nonheap_committed'] = nonheap_values['committed']
            data['values'][component]['nonheap_used'] = nonheap_values['used']

        for k, v in result.items():
            if k.startswith('jvm_memorypool_'):
                log.debug('k: {} - v : {}'.format(k, v))


        log.debug('ActiveMQJVM onSuccess data: {}'.format(data))
        return data

    def onError(self, result, config):
        log.error('Error - result is {}'.format(result))
        # TODO: send event of collection failure
        return {}
