# stdlib Imports
import base64
import json

import zope.component
# Zenoss Imports
from Products.DataCollector.plugins.CollectorPlugin import PythonPlugin
from Products.DataCollector.plugins.DataMaps import ObjectMap, RelationshipMap
from Products.ZenCollector.interfaces import IEventService
from ZenPacks.community.ActiveMQ.lib.util import StringProtocol

# Twisted Imports
from twisted.internet import reactor
from twisted.internet.defer import Deferred, inlineCallbacks, returnValue
from twisted.internet.protocol import Protocol
from twisted.web.client import Agent
from twisted.web.http_headers import Headers


class ActiveMQ(PythonPlugin):
    """
    Doc about this plugin
    """

    _eventService = zope.component.queryUtility(IEventService)

    requiredProperties = (
        'zJolokiaPort',
        'zJolokiaUsername',
        'zJolokiaPassword',
    )

    deviceProperties = PythonPlugin.deviceProperties + requiredProperties

    components = [
        ['brokers', 'http://{}:{}/api/jolokia/read/org.apache.activemq:type=Broker,brokerName=*/'
                    'BrokerName,BrokerVersion,BrokerId,Queues'],
        ['queues', 'http://{}:{}/api/jolokia/read/org.apache.activemq:*,type=Broker,destinationType=Queue'],
    ]

    @inlineCallbacks
    def collect(self, device, log):
        log.debug('{}: Modeling collect'.format(device.id))

        port = getattr(device, 'zJolokiaPort', None)
        username = getattr(device, 'zJolokiaUsername', None)
        password = getattr(device, 'zJolokiaPassword', None)

        ip_address = device.manageIp
        if not ip_address:
            log.error("%s: IP Address cannot be empty", device.id)
            returnValue(None)

        basic_auth = base64.encodestring('{}:{}'.format(username, password))
        auth_header = "Basic " + basic_auth.strip()
        results = {}
        agent = Agent(reactor)
        headers = {
                   "Accept": ['application/json'],
                   "Authorization": [auth_header],
                   }

        for component, url_pattern in self.components:
            url = url_pattern.format(ip_address, port)
            log.debug('collect url: {}'.format(url))

            try:
                response = yield agent.request('GET', url, Headers(headers))
                proto = StringProtocol()
                response.deliverBody(proto)
                body = yield proto.d
                log.debug('body: {}'.format(body))
                results[component] = json.loads(body)
            except Exception, e:
                log.error('%s: %s', device.id, e)
        returnValue(results)

    def process(self, device, results, log):
        """
        Must return one of :
            - None, changes nothing. Good in error cases.
            - A RelationshipMap, for the device to component information
            - An ObjectMap, for the device device information
            - A list of RelationshipMaps and ObjectMaps, both
        """
        log.debug('process results: {}'.format(results.keys()))

        brokers_data = results.get('brokers', '')
        if brokers_data and brokers_data['status'] == 200:
            brokers_data = brokers_data.get('value', '')
        else:
            return []

        queues_data = results.get('queues', '')
        if queues_data and queues_data['status'] == 200:
            queues_data = queues_data.get('value', '')

        broker_maps = []
        jvm_maps = []
        rm = []
        rm_queues = []
        rm_queuesdlq = []

        for broker, brokerAttr in brokers_data.items():
            om_broker = ObjectMap()
            om_jvm = ObjectMap()
            queue_maps = []
            queuedlq_maps = []

            broker_name = brokerAttr.get('BrokerName')
            om_broker.id = self.prepId(broker_name)
            om_broker.title = broker_name
            om_broker.brokerId = brokerAttr.get('BrokerId')
            om_broker.version = brokerAttr.get('BrokerVersion')
            om_broker.objectName = broker
            broker_maps.append(om_broker)
            om_jvm.id = self.prepId(broker_name)
            om_jvm.title = broker_name
            jvm_maps.append(om_jvm)

            compname_broker = 'activeMQBrokers/{}'.format(om_broker.id)
            queues = brokerAttr.get('Queues')

            # log.debug('XXX Modeler queues: {}'.format(queues))

            for _, queue in [(_, queue) for q in queues for (_, queue) in q.items()]:
                # TODO: What if queue with same name in different broker ?
                # TODO: create queue id with broker id included
                queue_data = queues_data.get(queue, '')
                if queue_data:
                    '''
                    if 'mos' in queue:
                        log.debug('Modeler queue: {}'.format(queue))
                        log.debug('Modeler queue_data: {}'.format(queue_data))
                    '''
                    om_queue = ObjectMap()
                    queue_name = queue_data['Name']
                    om_queue.id = self.prepId(queue_name)
                    om_queue.title = queue_name
                    om_queue.objectName = queue
                    om_queue.brokerName = broker_name

                    # DLQ detection based on attribute
                    # queue_dlq = queue_data['DLQ']
                    queue_dlq = queue_name.startswith('DLQ')
                    if queue_dlq:
                        queuedlq_maps.append(om_queue)
                    else:
                        queue_maps.append(om_queue)

            rm_queues.append(RelationshipMap(relname='activeMQQueues',
                                             modname='ZenPacks.community.ActiveMQ.ActiveMQQueue',
                                             compname=compname_broker,
                                             objmaps=queue_maps))
            rm_queuesdlq.append(RelationshipMap(relname='activeMQQueueDLQs',
                                                modname='ZenPacks.community.ActiveMQ.ActiveMQQueueDLQ',
                                                compname=compname_broker,
                                                objmaps=queuedlq_maps))

        rm.append(RelationshipMap(relname='activeMQBrokers',
                                  modname='ZenPacks.community.ActiveMQ.ActiveMQBroker',
                                  compname='',
                                  objmaps=broker_maps))

        rm.append(RelationshipMap(relname='activeMQJVMs',
                                  modname='ZenPacks.community.ActiveMQ.ActiveMQJVM',
                                  compname='',
                                  objmaps=jvm_maps))


        rm.extend(rm_queues)
        rm.extend(rm_queuesdlq)
        return rm
