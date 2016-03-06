"""Methods to deal with BGP on an EOS node."""

import re
from collections import defaultdict


def _parse_neigbor_info(line):
    m = re.match('BGP neighbor is (?P<neighbor>.*?), remote AS (?P<as>.*?), .*', line)
    return m.group('neighbor'), m.group('as')


def _parse_rid_info(line):
    m = re.match('.*BGP version 4, remote router ID (?P<rid>.*?), VRF (?P<vrf>.*?)$', line)
    return m.group('rid'), m.group('vrf')


def _parse_desc(line):
    m = re.match('\s+Description: (?P<description>.*?)', line)
    if m:
        return m.group('description')
    else:
        return None


def _parse_local_info(line):
    m = re.match('Local AS is (?P<as>.*?),.*', line)
    return m.group('as')


def _parse_prefix_info(line):
    m = re.match('(\s*?)(?P<af>IPv[46]) Unicast:\s*(?P<sent>\d+)\s*(?P<received>\d+)', line)
    return m.group('sent'), m.group('received')


def get_bgp_neighbors(node):
    """Implemantation of NAPALM method get_bgp_neighbors."""
    NEIGHBOR_FILTER = \
        'bgp neighbors vrf all | include remote AS | remote router ID |^\s*IPv[46] Unicast:.*[0-9]+|^Local AS|Desc'
    output_summary_cmds = node.device.run_commands(
        ['show ipv6 bgp summary vrf all', 'show ip bgp summary vrf all'],
        encoding='json')
    output_neighbor_cmds = node.device.run_commands(
        ['show ip ' + NEIGHBOR_FILTER, 'show ipv6 ' + NEIGHBOR_FILTER],
        encoding='text')

    bgp_counters = defaultdict(lambda: dict(peers=dict()))
    for summary in output_summary_cmds:
        """
        Json output looks as follows
        "vrfs": {
            "default": {
                "routerId": 1,
                "asn": 1,
                "peers": {
                    "1.1.1.1": {
                        "msgSent": 1,
                        "inMsgQueue": 0,
                        "prefixReceived": 3926,
                        "upDownTime": 1449501378.418644,
                        "version": 4,
                        "msgReceived": 59616,
                        "prefixAccepted": 3926,
                        "peerState": "Established",
                        "outMsgQueue": 0,
                        "underMaintenance": false,
                        "asn": 1
                    }
                }
            }
        }
        """
        for vrf, vrf_data in summary['vrfs'].iteritems():
            bgp_counters[vrf]['router_id'] = vrf_data['routerId']
            for peer, peer_data in vrf_data['peers'].iteritems():
                peer_info = {
                    'is_up': peer_data['peerState'] == 'Established',
                    'is_enabled': peer_data['peerState'] == 'Established' or peer_data['peerState'] == 'Active',
                    'uptime': int(peer_data['upDownTime'])
                }
                bgp_counters[vrf]['peers'][peer] = peer_info
    lines = []
    [lines.extend(x['output'].splitlines()) for x in output_neighbor_cmds]
    for line in lines:
        """
        Raw output from the command looks like the following:

          BGP neighbor is 1.1.1.1, remote AS 1, external link
            Description: Very info such descriptive
            BGP version 4, remote router ID 1.1.1.1, VRF my_vrf
             IPv4 Unicast:         683        78
             IPv6 Unicast:           0         0
          Local AS is 2, local router ID 2.2.2.2
        """
        if line is '':
            continue
        neighbor, r_as = _parse_neigbor_info(lines.pop(0))
        # this line can be either description or rid info
        next_line = lines.pop(0)
        desc = _parse_desc(next_line)
        if desc is None:
            rid, vrf = _parse_rid_info(next_line)
            desc = ''
        else:
            rid, vrf = _parse_rid_info(lines.pop(0))

        v4_sent, v4_recv = _parse_prefix_info(lines.pop(0))
        v6_sent, v6_recv = _parse_prefix_info(lines.pop(0))
        local_as = _parse_local_info(lines.pop(0))
        data = {
            'remote_as': int(r_as),
            'remote_id': unicode(rid),
            'local_as': int(local_as),
            'description': unicode(desc),
            'address_family': {
                'ipv4': {
                    'sent_prefixes': int(v4_sent),
                    'received_prefixes': int(v4_recv),
                    'accepted_prefixes': -1
                },
                'ipv6': {
                    'sent_prefixes': int(v6_sent),
                    'received_prefixes': int(v6_recv),
                    'accepted_prefixes': -1
                }
            }
        }
        bgp_counters[vrf]['peers'][neighbor].update(data)

    if 'default' in bgp_counters.keys():
        bgp_counters['global'] = bgp_counters.pop('default')
    return bgp_counters
