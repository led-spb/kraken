#!/usr/bin/python
import argparse
import logging
import json
import time
import platform
import urlparse

import pyorient.ogm
import pyorient.ogm.exceptions
from kraken_ansible import AnsibleRunner
from schema import register_schema, Link, AggregatedLink


# class KrakenHandler(tornado.web.RequestHandler):
class KrakenHandler(object):
    """Base class for kraken requests"""
    def __init__(self, graph):
        self.graph = graph

    def execute(self, **arguments):
        pass


class DiscoveryHandler(KrakenHandler):
    """Class for run discovery agents and write resutls into OrientDB"""

    def execute(self, host):
        # Build inventory data
        inventory_data = {}
        inventory = InventoryHandler(self.graph)

        if host == '[all]':
            inventory_data['node'] = inventory.execute('all')
        elif host == '[new]':
            inventory_data['node'] = inventory.execute('new')
        else:
            inventory_data['node'] = [host]

        # Run discovery agents
        runner = AnsibleRunner(
            hosts=inventory_data,
            playbook='discovery.yaml',
            config={
                'verbosity': 5,
                'connection': 'smart'
            },
            vars_filename='.variables'
        )
        results = runner.run()
        # logging.debug(json.dumps(results, indent=2))

        discovery_data = {}
        stats = results['stats']
        for host in stats.keys():
            info = {
                'unreachable': False,
                'ansible_facts': None,
                'kraken_facts': None
            }
            if stats[host]['unreachable'] > 0 or stats[host]['failures'] > 0:
                info['unreachable'] = True
            discovery_data[host] = info
            pass

        # Gather information from ansible result
        for play in results['plays']:
            for task in play['tasks']:
                for host, info in task['hosts'].iteritems():
                    if 'kraken_facts' in info:
                        discovery_data[host]['kraken_facts'] = \
                            info['kraken_facts']
                    if 'ansible_facts' in info:
                        discovery_data[host]['ansible_facts'] = \
                            info['ansible_facts']
                    pass
        # logging.info(json.dumps(discovery_data, indent=2))

        logging.info('Processed %d hosts', len(discovery_data.keys()))
        for host, host_info in discovery_data.iteritems():
            host_info['hostname'] = host
            self.update_host_info(host_info)
            pass
        pass

    def _search_node(self, node_info, create=False):
        try:
            node = self.graph.hosts.query(
                hostname=str(node_info['hostname'])
            ).one()
            return node
        except pyorient.ogm.exceptions.NoResultFound:
            if create:
                return self._create_node(node_info)
            else:
                return None

    def _update_dict(self, data):
        if type(data) == dict:
            for key, value in data.iteritems():
                if type(value) == unicode:
                    data[key] = str(value)
                if type(value) == dict or type(value) == list:
                    data[key] = self._update_dict(value)
            pass

        if type(data) == list:
            for key, value in enumerate(data):
                if type(value) == unicode:
                    data[key] = str(value)
                if type(value) == dict or type(value) == list:
                    data[key] = self._update_dict(value)
            pass
        return data

    def _create_node(self, node_info):
        return self.graph.hosts.create(**node_info)
        pass

    def _update_node(self, node, node_info):
        node_info = self._update_dict(node_info)
        rec_data = {'@host': node_info}
        self.graph.client.record_update(node._id, node._id, rec_data, 1)

    def _create_link(self, node_out, node_in, link_info):
        self.graph.create_edge(Link, node_out, node_in, **link_info)
        pass

    def _create_agg_link(self, node_out, node_in, ports):
        link = self.graph.client.command(
            "select * from aggregatedlink where out=%s and in=%s" %
            (node_out._id, node_in._id)
        )
        if len(link) == 0:
            self.graph.create_edge(
                AggregatedLink, node_out, node_in, ports=ports
            )
        else:
            # update ports
            link = link[0]
            ports = set(ports)
            ports.update(link.ports)
            ports = ['"%s"' % x[1] for x in enumerate(ports)]
            cmd = "update aggregatedlink set ports = [%s]" \
                  " where out=%s and in=%s" % \
                  (",".join(ports), node_out._id, node_in._id)
            self.graph.client.command(cmd)
        pass

    def _delete_links(self, node):
        # query = "delete edge where @class!='controlledlink' and out=%s" % \
        # self.graph.client.command( query )
        pass

    def update_host_info(self, host_data):
        try:
            # logging.debug(data)
            hostname = host_data['hostname']
            logging.info('Processing host %s' % str(hostname))

            if host_data['unreachable']:
                logging.debug('Set unreachable flag for host %s', hostname)
                host = self.graph.hosts.query(hostname=str(hostname)).one()
                host.unreachable = True
                host.save()
                return

            data = host_data['kraken_facts']
            logging.debug(json.dumps(data, indent=2))
            # return

            host_info = data['host']
            neightbours = data['neightbours']
            host_info['discovered'] = int(time.time()*1000)
            link_info = data['links']

            host = None
            host = self._search_node(host_info, False)
            if host is None:
                host = self._create_node(host_info)
            else:
                self._update_node(host, host_info)

            targets_cached = {}
            for link in link_info:
                target_host = link["target"]
                if target_host in targets_cached:
                    target = targets_cached[target_host]['node']
                else:
                    target_ip = neightbours[target_host]
                    target = self._search_node({
                        'hostname': target_host,
                        'ip_address': [target_ip]
                        },
                        True)
                    targets_cached[target_host] = {
                        'node': target,
                        'out': set(),
                        'in': set()
                    }

                if 'dst_port' in link and 'direction' in link:
                    direction = link['direction']
                    targets_cached[target_host][direction].add(
                        link['dst_port']
                    )

            # create aggregated links
            for key in targets_cached.keys():
                target = targets_cached[key]['node']

                ports = [x[1] for x in enumerate(targets_cached[key]['out'])]
                if len(ports) > 0:
                    self._create_agg_link(host, target, ports)

                ports = [x[1] for x in enumerate(targets_cached[key]['in'])]
                if len(ports) > 0:
                    self._create_agg_link(target, host, ports)
                    pass

        except Exception:
            logging.exception("Processing host")
        return


class ReportHandler(KrakenHandler):
    """Generate reports"""

    def initialize(self, graph):
        self.graph = graph
        self.nodename = platform.node()

    def output_csv(self, result, fields):
        self.set_header('Content-Type', 'text/csv')
        self.write(";".join(fields)+"\r\n")
        for row in result:
            data = []
            for field in fields:
                if field not in row:
                    data.append("")
                else:
                    val = row[field]
                    val = ",".join(val) if type(val) == list else str(val)
                    data.append(val)
            self.write(";".join(data)+"\r\n")
        pass

    def report_links(self, mode, format):
        sql = "select * from( traverse * from aggregatedlink maxdepth 1 )"
        if mode == 'controlled':
            sql = "select * from( traverse * from controlledlink maxdepth 1 )"

        query = self.graph.client.command(sql)
        links = []
        hostnames = {}
        for rec in query:
            if rec._class.endswith('link'):
                data = rec.oRecordData
                data['in'] = '#'+data['in'].get()
                data['out'] = '#'+data['out'].get()
                links.append(data)

            if rec._class.endswith('host'):
                hostnames[rec._rid] = rec
            pass

        fields = set()
        result = []
        for link in links:
            link['external'] = 0
            rid = link['out']
            if rid in hostnames:
                link['out'] = hostnames[rid].hostname

            rid = link['in']
            if rid in hostnames:
                link['in'] = hostnames[rid].hostname
                if hostnames[rid]._class == 'externalhost':
                    link['external'] = 1

            fields.update(link.keys())
            if link['out'] == self.nodename or link['in'] == self.nodename:
                continue
            result.append(link)

        self.set_status(200)
        if format == 'json':
            self.set_header('Content-Type', 'application/json')
            self.write(json.dumps(result))
        if format == 'csv':
            self.output_csv(result, fields)
        pass

    def report_hosts(self, mode, format):
        sql = "select expand(@this.exclude('out_*','in_*')) from host"
        if mode == 'discovered':
            sql = sql + " where discovered is not null"
        query = self.graph.client.command(sql)
        result = []
        fields = set()
        for rec in query:
            fields.update(rec.oRecordData.keys())
            result.append(rec.oRecordData)

        self.set_status(200)
        if format == 'json':
            self.set_header('Content-Type', 'application/json')
            self.write(json.dumps(result))
        if format == 'csv':
            self.output_csv(result, fields)
        pass

    def get(self, *args):
        report = self.get_argument('report', 'links')
        mode = self.get_argument('mode', 'all')
        format = self.get_argument('format', 'json')

        if report == 'links':
            self.report_links(mode, format)
        if report == 'hosts':
            self.report_hosts(mode, format)
        pass


class InventoryHandler(KrakenHandler):
    """Generate ansible inventory"""

    def _ip2num(self, ip):
        data = ip.split("/")[0].split(".")
        data.reverse()
        ip_num = 0
        for x in enumerate(data):
            ip_num = ip_num + int(x[1]) * (2**(x[0]*8))
        return ip_num

    def _check(self, ip, mask):
        ip1_num = self._ip2num(ip)
        ip2_num = self._ip2num(mask)

        num_mask = ~(2**(32-int(mask.split('/')[1]))-1)
        return (ip1_num & num_mask) == (ip2_num & num_mask)

    def check_mask(self, ipaddress, mask):
        for ip in ipaddress:
            if self._check(ip, mask):
                return True
        return False

    def execute(self, mode, mask=None):
        if mode == 'all':
            sql = "select from host"
        else:
            sql = "select from host where discovered is null"\
                  " and (unreachable is null or unreachable==false)"
        query = self.graph.client.command(sql)
        return [
            host.hostname for host in query
            if mask is None or self.check_mask(host.ip_address, mask)
        ]
        pass


class CommandHandler(KrakenHandler):
    """Utility command handler"""

    def execute(self, mode):
        try:
            if mode == 'clear':
                self.graph.client.command(
                    "delete edge where @class!='controlledlink'"
                )
                self.graph.client.command("delete vertex host")
        except Exception:
            logging.exception("Processing cmd")
        pass


class MonitorHandler(KrakenHandler):
    def initialize(self, graph):
        self.graph = graph

    def get(self, *args):
        hostname = self.get_query_argument('host')
        query = self.graph.client.command(
            "select expand(outE('controlledlink')) from host"
            " where hostname = '%s'" % hostname
        )

        targets = set()
        self.set_status(200)
        self.set_header('Content-Type', 'text/plain')
        for link in query:
            host = self.graph.client.command(
                "select hostname from host where @rid = %s" % str(link._in)
            )
            if len(host) == 0:
                logging.warn("Can't find host %s" % str(link._in))
                continue

            ports = link.ports
            target = host[0].hostname

            # Exclude links itself
            if hostname == target:
                continue

            targets.add(target)

            for port in ports:
                self.write("[[inputs.net_response]]\n")
                self.write("protocol=\"tcp\"\n")
                self.write("address=\"%s:%s\"\n" % (target, port))
                self.write("timeout=\"3s\"\n")
                self.write("interval=\"30s\"\n\n")

        ping_targets = ",".join(["\"%s\"" % x[1] for x in enumerate(targets)])
        if len(ping_targets) > 0:
            self.write("[[inputs.ping]]\n")
            self.write("interval=\"30s\"\n")
            self.write("count=3\n")
            self.write("urls = [%s]\n\n" % ping_targets)
        pass


class KrakenApp(object):
    """Main application"""

    def __init__(self):
        pass

    """Parse command line arguments"""
    def parse_args(self):
        parser = argparse.ArgumentParser(
            description='Kraken - network connectivity scanner',
            fromfile_prefix_chars='@',
            formatter_class=argparse.RawTextHelpFormatter
        )
        parser.add_argument(
            '-d', '--database', default='plocal://root:admin@localhost/kraken',
            metavar='URL',
            help='OrientDB URL plocal://user:password@host/database'
        )
        parser.add_argument(
            '-v', '--debug', action='store_true', default=False
        )
        subparsers = parser.add_subparsers(
            title="command",
            dest="action"
        )
        parser_discovery = subparsers.add_parser('discovery')
        parser_discovery.add_argument(
            'host', default="[new]",
            help="[all] - discovery all hosts; "
                 "[new] - discovery only new hosts; "
                 "hostname for specified host only"
        )
        parser_discovery.add_argument('--discovery_mask')

        parser_commands = subparsers.add_parser('command')
        parser_commands.add_argument('what', choices=['clear'])

        self.options = parser.parse_args()
        pass

    """Initialize application"""
    def initialize(self):
        logging.basicConfig(
            format=u'%(asctime)s\t%(name)s\t%(levelname)s\t%(message)s',
            level=logging.DEBUG if self.options.debug else logging.INFO
        )
        # logging.debug(str(self.options))
        try:
            self.graph = None
            parts = urlparse.urlparse(self.options.database)

            self.graph = pyorient.ogm.Graph(
                 pyorient.ogm.Config.from_url(
                     self.options.database, parts.username, parts.password
                 )
            )
            register_schema(self.graph)
        except Exception:
            logging.exception('Error while connecting to OrientDB')
            raise Exception('Unable to connect to OrientDB')
            pass
        logging.info('Connected to OrientDB')
        pass

    def run(self):
        self.parse_args()
        try:
            self.initialize()

            if self.options.action == 'discovery':
                handler = DiscoveryHandler(self.graph)
                handler.execute(self.options.host)
                return

            if self.options.action == 'command':
                handler = CommandHandler(self.graph)
                handler.execute(self.options.what)
                return

        except Exception:
            logging.exception('Error occured')
        pass
        logging.debug('Finished')


if __name__ == "__main__":
    KrakenApp().run()
