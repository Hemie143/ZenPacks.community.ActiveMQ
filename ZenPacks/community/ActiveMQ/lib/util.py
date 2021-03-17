from twisted.internet.defer import Deferred
from twisted.internet.protocol import Protocol


class StringProtocol(Protocol):

    def __init__(self):
        self.d = Deferred()
        self._data = []

    def dataReceived(self, data):
        self._data.append(data)

    def connectionLost(self, reason):
        self.d.callback(''.join(self._data))
