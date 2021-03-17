from pyorient.ogm import declarative
from pyorient.ogm.property import String, Boolean, DateTime, EmbeddedList
import time
import datetime

Node = declarative.declarative_node()
Relationship = declarative.declarative_relationship()


class Host(Node):
    element_plural = 'hosts'

    hostname = String(nullable=False, indexed=True, unique=True)
    branch = String()
    os = String()
    discovered = DateTime()
    ip_address = EmbeddedList(String())
    listen_ports = EmbeddedList(String())
    unreachable = Boolean()

    def to_dict(self):
        props = {
           key: value if type(value) != datetime.datetime
           else int(time.mktime(value.utctimetuple()) * 1000)
           for key, value in self._props.iteritems()
        }
        props.update({"id": self._id})
        return props


class ExternalHost(Node):
    element_plural = 'external'

    hostname = String(nullable=False, indexed=True, unique=True)
    branch = String()


class Link(Relationship):
    element_plural = 'links'

    type = String(nullable=False, default="tcp")
    src_port = String()
    dst_port = String()
    state = Boolean()
    pass


class AggregatedLink(Relationship):
    type = String(nullable=False, default="tcp")
    ports = EmbeddedList(String())
    pass


class ControlledLink(Relationship):
    type = String(nullable=False, default="tcp")
    ports = EmbeddedList(String())
    ticket = String()
    pass


def register_schema(graph):
    graph.create_all(Node.registry)
    graph.create_all(Relationship.registry)
    pass
