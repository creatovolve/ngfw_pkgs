import os
import sys
import subprocess
import datetime
import traceback
import string
import re
from sync.network_util import NetworkUtil

# This class is a utility class with utility functions providing
# useful tools for dealing with nftables rules
def condition_ip_protocol_expression(value, op):
    if value == None:
        raise Exception("Invalid value " + str(value))
    value = value.lower()
    if "any" in value:
        return ""

    if op != "IS" and op != "IS_NOT":
        raise Exception("Unsupported operation " + str(op))
    if op == "IS":
        op_str = ""
    elif op == "IS_NOT":
        op_str = "!= "

    protos = value.split(",")
    if len(protos) == 1:
        return "ip protocol " + op_str + value
    else:
        return "ip protocol " + op_str + "\"{" + value + "}\""

def condition_interface_expression(mark_exp, wan_mark, intf_mark, value, op):
    if "any" in value:
        return ""

    if op != "IS" and op != "IS_NOT":
        raise Exception("Unsupported operation " + str(op))
    intfs = value.split(",")
    if "wan" in intfs and len(intfs) != 1:
        # Because wan isn't a specific interface we can't use sets
        # We have no ability to check that mark and logical OR that with checking another mark
        raise Exception("\"wan\" interface condition value can not be used with other values")
    if "non_wan" in intfs and len(intfs) != 1:
        # Because non_wan isn't a specific interface we can't use sets
        # We have no ability to check that mark and logical OR that with checking another mark
        raise Exception("\"non_wan\" interface condition value can not be used with other values")

    if "wan" in intfs:
        if op == "IS":
            return mark_exp + " and " + wan_mark + " != 0"
        else:
            return mark_exp + "  and " + wan_mark + " == 0"
    elif "non_wan" in intfs:
        if op == "IS":
            return mark_exp + " and " + wan_mark + " == 0"
        else:
            return mark_exp + " and " + wan_mark + " != 0"
    else:
        try:
            intf_indexs = [ int(x) for x in intfs ]
            if len(intf_indexs) == 1:
                value_str = str(intf_indexs[0])
            else:
                value_str = "\"{" + value + "}\""
            if op == "IS":
                return mark_exp + " and " + intf_mark + " " + value_str
            else:
                return mark_exp + " and " + intf_mark + " != " + value_str
        except ValueError as e:
            raise Exception("Invalid interface condition value: " + value)

def condition_source_interface_expression(value, op):
    return condition_interface_expression("mark", "0x01000000", "0x000000ff", value, op)

def condition_destination_interface_expression(value, op):
    return condition_interface_expression("mark", "0x02000000", "0x0000ff00", value, op)

def condition_client_interface_expression(value, op):
    return condition_interface_expression("ct mark", "0x01000000", "0x000000ff", value, op)

def condition_server_interface_expression(value, op):
    return condition_interface_expression("ct mark", "0x02000000", "0x0000ff00", value, op)

def condition_address_expression(addr_str, value, op):
    if "any" in value:
        return ""

    if op != "IS" and op != "IS_NOT":
        raise Exception("Unsupported operation " + str(op))
    if "." in value and ":" in value:
        raise Exception("Can not mix IPv4 and IPv6 address is same rule/condition.")
    exp = "ip " + addr_str
    if ":" in value:
        exp = "ip6 " + addr_str

    addrs = value.split(",")

    if op == "IS":
        op_str = ""
    elif op == "IS_NOT":
        op_str = "!= "

    if len(addrs) == 1:
        return exp + " " + op_str + value
    else:
        return exp + " " + op_str + "\"{" + value + "}\""


def condition_source_address_expression(value, op):
    return condition_address_expression("saddr", value, op)

def condition_destination_address_expression(value, op):
    return condition_address_expression("daddr", value, op)

def condition_dict_address_expression(addr_str, value, op):
    if "any" in value:
        return ""

    if op != "IS" and op != "IS_NOT":
        raise Exception("Unsupported operation " + str(op))
    if "." in value and ":" in value:
        raise Exception("Can not mix IPv4 and IPv6 address is same rule/condition.")
    exp = "dict session ct id " + addr_str + " ipv4_addr"
    if ":" in value:
        exp = "dict session ct id " + addr_str + " ipv6_addr"

    addrs = value.split(",")

    if op == "IS":
        op_str = ""
    elif op == "IS_NOT":
        op_str = "!= "

    if len(addrs) == 1:
        return exp + " " + op_str + value
    else:
        return exp + " " + op_str + "\"{" + value + "}\""

def condition_client_address_expression(value, op):
    return condition_dict_address_expression("client_address",value, op)

def condition_server_address_expression(value, op):
    return condition_dict_address_expression("server_address",value, op)

def condition_port_expression(port_str, ip_protocol, value, op):
    if "any" in value:
        return ""

    if ip_protocol == None:
        raise Exception("Undefined protocol with port condition")
    if op != "IS" and op != "IS_NOT":
        raise Exception("Unsupported operation " + str(op))
    exp = ip_protocol + " " + port_str
    addrs = value.split(",")

    if op == "IS":
        op_str = ""
    elif op == "IS_NOT":
        op_str = "!= "

    if len(addrs) == 1:
        return exp + " " + op_str + value
    else:
        return exp + " " + op_str + "\"{" + value + "}\""

def condition_source_port_expression(value, op, ip_protocol):
    return condition_port_expression("sport", ip_protocol, value, op)

def condition_destination_port_expression(value, op, ip_protocol):
    return condition_port_expression("dport", ip_protocol, value, op)

def condition_dict_port_expression(port_str, value, op):
    if "any" in value:
        return ""

    if op != "IS" and op != "IS_NOT":
        raise Exception("Unsupported operation " + str(op))
    exp = "dict session ct id " + port_str + " integer"
    addrs = value.split(",")

    if op == "IS":
        op_str = ""
    elif op == "IS_NOT":
        op_str = "!= "

    if len(addrs) == 1:
        return exp + " " + op_str + value
    else:
        return exp + " " + op_str + "\"{" + value + "}\""

def condition_client_port_expression(value, op):
    return condition_dict_port_expression("client_port", value, op)

def condition_server_port_expression(value, op):
    return condition_dict_port_expression("server_port", value, op)

def condition_expression(condition, ip_protocol=None):
    type = condition.get('type')
    op = condition.get('op')
    value = condition.get('value')

    if type == None or value == None:
        raise Exception("Rule missing required fields " + str(condition.get('ruleId')))

    # if op is missing, assume "IS"
    if op == None:
        op = "IS"

    if type == "IP_PROTOCOL":
        return condition_ip_protocol_expression(value, op)
    elif type == "SOURCE_INTERFACE":
        return condition_source_interface_expression(value, op)
    elif type == "DESTINATION_INTERFACE":
        return condition_destination_interface_expression(value, op)
    elif type == "CLIENT_INTERFACE":
        return condition_client_interface_expression(value, op)
    elif type == "SERVER_INTERFACE":
        return condition_server_interface_expression(value, op)
    elif type == "SOURCE_ADDRESS":
        return condition_source_address_expression(value, op)
    elif type == "DESTINATION_ADDRESS":
        return condition_destination_address_expression(value, op)
    elif type == "CLIENT_ADDRESS":
        return condition_client_address_expression(value, op)
    elif type == "SERVER_ADDRESS":
        return condition_server_address_expression(value, op)
    elif type == "SOURCE_PORT":
        return condition_source_port_expression(value, op, ip_protocol)
    elif type == "DESTINATION_PORT":
        return condition_destination_port_expression(value, op, ip_protocol)
    elif type == "CLIENT_PORT":
        return condition_client_port_expression(value, op)
    elif type == "SERVER_PORT":
        return condition_server_port_expression(value, op)
    
    raise Exception("Unsupported condition type " + type + " " + str(condition.get('ruleId')))


# This method takes a list of conditions from a rule and translates them into a string containing the nftables conditions
# It returns a list of strings, because some set of conditions require multiple nftables rules
# Example input: ['type':'SOURCE_INTERFACE', 'value':'1'] -> "ct mark and 0xff == 0x01"
# Example input: ['type':'DESTINATION_PORT', 'value':'123'] -> "tcp dport 123"
def conditions_expression(conditions, comment=None):
    if conditions is None:
        return "";

    # FIXME
    # if comment != None:
    #        current_strings = [ current + (" -m comment --comment \"%s\" " % comment)  for current in current_strings ]

    # set has_protocol_condition to True if this rule as an "IP_PROTOCOL" condition        
    has_protocol_condition = False
    ip_protocol = None
    for condition in conditions:
        if condition.get('type') == 'IP_PROTOCOL' and condition.get('op') == 'IS' and condition.get('value') != None and "," not in condition.get('value'):
            has_protocol_condition = True
            ip_protocol=condition.get('value')

    str = ""
    for condition in conditions:
        add_str = condition_expression(condition, ip_protocol=ip_protocol)
        if add_str != "":
            str = str + " " + add_str

    return str.strip()
