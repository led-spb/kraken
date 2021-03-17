#!/usr/bin/python
import platform
import socket
import re
import fcntl
import struct
import array
from ansible.module_utils.basic import AnsibleModule


def format_ip(addr):
    return str(ord(addr[0])) + '.' + \
           str(ord(addr[1])) + '.' + \
           str(ord(addr[2])) + '.' + \
           str(ord(addr[3]))


def parse_conn(conn):
    conn = conn.split(":", 2)
    ip_addr = conn[0]
    port = int(conn[1], 16)
    ip_addr = [
        str(int(x[0]+x[1], 16))
        for x in zip(ip_addr[0::2], ip_addr[1::2])
    ]
    ip_addr.reverse()
    ip_addr = ".".join(ip_addr)
    # ip_addr = format_ip(ip_addr)
    hostname = None
    try:
        hostname = socket.gethostbyaddr(ip_addr)[0]
    except Exception:
        pass
    return (ip_addr, hostname, port)


def get_tcp_links():
    links = []
    f = open("/proc/net/tcp", "rt")
    was_header = False
    for line in f:
        if not was_header:
            was_header = True
            continue

        data = re.split("\\s+", line.strip())
        info = {
            'src': parse_conn(data[1]),
            'dst': parse_conn(data[2]),
            'state': int(data[3], 16)
        }
        links.append(info)
    return links


def all_interfaces():
    max_possible = 128  # arbitrary. raise if needed.
    bytes = max_possible * 32
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    names = array.array('B', '\0' * bytes)
    outbytes = struct.unpack('iL', fcntl.ioctl(
        s.fileno(),
        0x8912,  # SIOCGIFCONF
        struct.pack('iL', bytes, names.buffer_info()[0])
    ))[0]
    namestr = names.tostring()
    lst = []
    for i in range(0, outbytes, 40):
        name = namestr[i:i+16].split('\0', 1)[0]
        ip = namestr[i+20:i+24]
        lst.append((name, format_ip(ip)))
    return lst


def main():
    module = AnsibleModule(argument_spec={})

    interfaces = all_interfaces()
    tcp = get_tcp_links()
    links = {}

    listen = [x['src'][2] for x in tcp if x['state'] == 10]
    neightbours = {}

    for x in tcp:
        source = x['src'][0]
        source_port = x['src'][2]

        target = x['dst'][0]
        target_port = x['dst'][2]

        if x['state'] == 1 and target != source:

            if source_port not in listen:
                direction = 'out'
                port = target_port
            else:
                direction = 'in'
                port = source_port

            idx = "%s_%s_%s" % (target, port, direction)
            links[idx] = {
                "target": target,
                "mode": "tcp",
                "dst_port": port,
                "direction": direction
            }

            if target not in neightbours:
                neightbours[target] = socket.gethostbyname(target)

    result = {
        'host': {
            'listen': listen,
            'os': ' '.join(platform.dist()) +
                  ' ['+' '.join(platform.uname())+']',
            'hostname': platform.node(),
            'ip_address': [x[1] for x in interfaces if x[1] != '127.0.0.1'],
            'branch': platform.node()[:3].strip("-").upper(),
        },
        'neightbours': neightbours,
        'links': links.values()
    }
    module.exit_json(changed=False, kraken_facts=result)


if __name__ == "__main__":
    main()
