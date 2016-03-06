"""Methods to deal with BGP on an EOS node."""

import re
from collections import defaultdict

from netaddr import IPAddress
from netaddr.core import AddrFormatError


_PROPERTY_TYPE_MAP_ = {
    # used to determine the default value
    # and cast the values
    'remote-as': int,
    'ebgp-multihop': int,
    'local-v4-addr': unicode,
    'local-v6-addr': unicode,
    'local-as': int,
    'remove-private-as': bool,
    'next-hop-self': bool,
    'description': unicode,
    'route-reflector-client': bool,
    'password': unicode,
    'route-map': unicode,
    'apply-groups': list,
    'type': unicode,
    'import-policy': unicode,
    'export-policy': unicode,
    'multipath': bool
}


_GROUP_FIELD_MAP_ = {
    'type': 'type',
    'multipath': 'multipath',
    'apply-groups': 'apply_groups',
    'remove-private-as': 'remove_private_as',
    'ebgp-multihop': 'multihop_ttl',
    'remote-as': 'remote_as',
    'local-v4-addr': 'local_address',
    'local-v6-addr': 'local_address',
    'local-as': 'local_as',
    'description': 'description',
    'import-policy': 'import_policy',
    'export-policy': 'export_policy'
}


_PEER_FIELD_MAP_ = {
    'description': 'description',
    'remote-as': 'remote_as',
    'local-v4-addr': 'local_address',
    'local-v6-addr': 'local_address',
    'local-as': 'local_as',
    'next-hop-self': 'nhs',
    'route-reflector-client': 'route_reflector_client',
    'description': 'description',
    'import-policy': 'import_policy',
    'export-policy': 'export_policy',
    'passwd': 'authentication_key'
}


_PROPERTY_FIELD_MAP_ = _GROUP_FIELD_MAP_.copy()


_PROPERTY_FIELD_MAP_.update(_PEER_FIELD_MAP_)


_DATATYPE_DEFAULT_ = {
    unicode: u'',
    int: 0,
    bool: False,
    list: []
}


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


def _parse_options(options, default_value=False):
    if not options:
        return dict()

    config_property = options[0]
    field_name = _PROPERTY_FIELD_MAP_.get(config_property)
    field_type = _PROPERTY_TYPE_MAP_.get(config_property)
    field_value = _DATATYPE_DEFAULT_.get(field_type)  # to get the default value

    if not field_type:
        # no type specified at all => return empty dictionary
        return dict()

    if not default_value:
        if len(options) > 1:
            field_value = field_type(options[1])
        else:
            if field_type is bool:
                field_value = True
    if field_name is not None:
        return {field_name: field_value}
    elif config_property in ['route-map', 'password']:
        # do not respect the pattern neighbor [IP_ADDRESS] [PROPERTY] [VALUE]
        # or need special output (e.g.: maximum-routes)
        if config_property == 'password':
            return {'authentication_key': unicode(options[2])}
            # returns the MD5 password
        if config_property == 'route-map':
            direction = None
            if len(options) == 3:
                direction = options[2]
                field_value = field_type(options[1])  # the name of the policy
            elif len(options) == 2:
                direction = options[1]
            if direction == 'in':
                field_name = 'import_policy'
            else:
                field_name = 'export_policy'
            return {field_name: field_value}

    return dict()


def get_bgp_config(node, group='', neighbor=''):
    """Implemantation of NAPALM method get_bgp_config."""
    bgp_config = dict()

    commands = list()
    commands.append('show running-config | section router bgp')
    bgp_conf = node.device.run_commands(commands, encoding='text')[0].get('output', '\n\n')
    bgp_conf_lines = bgp_conf.splitlines()[2:]

    bgp_neighbors = dict()

    if not group:
        neighbor = ''

    last_peer_group = ''
    local_as = 0
    for bgp_conf_line in bgp_conf_lines:
        default_value = False
        bgp_conf_line = bgp_conf_line.strip()
        if bgp_conf_line.startswith('router bgp'):
            local_as = int(bgp_conf_line.replace('router bgp', '').strip())
            continue
        if not (bgp_conf_line.startswith('neighbor') or bgp_conf_line.startswith('no neighbor')):
            continue
        if bgp_conf_line.startswith('no'):
            default_value = True
        bgp_conf_line = bgp_conf_line.replace('no neighbor ', '').replace('neighbor ', '')
        bgp_conf_line_details = bgp_conf_line.split()
        group_or_neighbor = unicode(bgp_conf_line_details[0])
        options = bgp_conf_line_details[1:]
        try:
            # will try to parse the neighbor name
            # which sometimes is the IP Address of the neigbor
            # or the name of the BGP group
            IPAddress(group_or_neighbor)
            # if passes the test => it is an IP Address, thus a Neighbor!
            peer_address = group_or_neighbor

            if options[0] == 'peer-group':
                last_peer_group = options[1]

            # if looking for a specific group
            if group and last_peer_group != group:
                continue

            # or even more. a specific neighbor within a group
            if neighbor and peer_address != neighbor:
                continue
            # skip all other except the target

            # in the config, neighbor details are lister after
            # the group is specified for the neighbor:
            #
            # neighbor 192.168.172.36 peer-group 4-public-anycast-peers
            # neighbor 192.168.172.36 remote-as 12392
            # neighbor 192.168.172.36 maximum-routes 200
            #
            # because the lines are parsed sequentially
            # can use the last group detected
            # that way we avoid one more loop to match the neighbors with the group they belong to
            # directly will apend the neighbor in the neighbor list of the group at the end
            if last_peer_group not in bgp_neighbors.keys():
                bgp_neighbors[last_peer_group] = dict()
            if peer_address not in bgp_neighbors[last_peer_group]:
                bgp_neighbors[last_peer_group][peer_address] = dict()
                bgp_neighbors[last_peer_group][peer_address].update({
                    key: _DATATYPE_DEFAULT_.get(_PROPERTY_TYPE_MAP_.get(prop))
                    for prop, key in _PEER_FIELD_MAP_.iteritems()
                })  # populating with default values
                bgp_neighbors[last_peer_group][peer_address].update({
                    'prefix_limit': {},
                    'local_as': local_as,
                    'authentication_key': u''
                })  # few more default values
            bgp_neighbors[last_peer_group][peer_address].update(
                _parse_options(options, default_value)
            )
        except AddrFormatError:
            # exception trying to parse group name
            # group_or_neighbor represents the name of the group
            group_name = group_or_neighbor
            if group and group_name != group:
                continue
            if group_name not in bgp_config.keys():
                bgp_config[group_name] = dict()
                bgp_config[group_name].update({
                    key: _DATATYPE_DEFAULT_.get(_PROPERTY_TYPE_MAP_.get(prop))
                    for prop, key in _GROUP_FIELD_MAP_.iteritems()
                })
                bgp_config[group_name].update({
                    'prefix_limit': {},
                    'neighbors': {},
                    'local_as': local_as
                })  # few more default values
            bgp_config[group_name].update(
                _parse_options(options, default_value)
            )
        except Exception:
            # for other kind of exception pass to next line
            continue

    for group, peers in bgp_neighbors.iteritems():
        if group not in bgp_config.keys():
            continue
        bgp_config[group]['neighbors'] = peers

    return bgp_config
