#!/usr/bin/env python3

# Sync Settings is takes the netork settings JSON file and "syncs" it to the operating system
# It reads through the settings and writes the appropriate operating system files such as
# /etc/network/interfaces
# /etc/untangle/iptables-rules.d/010-flush
# /etc/untangle/iptables-rules.d/200-nat-rules
# /etc/untangle/iptables-rules.d/210-port-forward-rules
# /etc/untangle/iptables-rules.d/220-bypass-rules
# /etc/dnsmasq.conf
# /etc/hosts
# etc etc
#
# This script should be called after changing the settings file to "sync" the settings to the OS.
# Afterwards it will be necessary to restart certain services so the new settings will take effect

import sys
if sys.version_info[0] == 3 and sys.version_info[1] == 5:
    sys.path.insert(0, sys.path[0] + "/" + "../lib/" + "python3.5/")

import getopt
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import time
import traceback

from   sync import *

class ArgumentParser(object):
    def __init__(self):
        self.filename = '/usr/share/untangle/settings/untangle-vm/network.js'
        self.restart_services = True

    def set_filename( self, arg ):
        self.filename = arg

    def set_norestart( self, arg ):
        self.restart_services = False

    def parse_args( self ):
        handlers = {
            '-f' : self.set_filename,
            '-n' : self.set_norestart,
        }

        try:
            (optlist, args) = getopt.getopt(sys.argv[1:], 'f:n')
            for opt in optlist:
                handlers[opt[0]](opt[1])
            return args
        except getopt.GetoptError as exc:
            print(exc)
            printUsage()
            exit(1)

def cleanup(code):
    global tmpdir
    if tmpdir != None:
        shutil.rmtree(tmpdir)
    exit(code)

def printUsage():
    sys.stderr.write( """\
%s Usage:
  optional args:
    -f <file>   : settings filename to sync to OS
    -n          : do not run restart commands (just copy files onto filesystem)
""" % sys.argv[0] )

# sanity check settings
def checkSettings( settings ):
    if settings is None:
        raise Exception("Invalid Settings: null")

    if 'interfaces' not in settings:
        raise Exception("Invalid Settings: missing interfaces")
    if 'list' not in settings['interfaces']:
        raise Exception("Invalid Settings: missing interfaces list")
    interfaces = settings['interfaces']['list']
    for intf in interfaces:
        for key in ['interfaceId', 'name', 'systemDev', 'symbolicDev', 'physicalDev', 'configType']:
            if key not in intf:
                raise Exception("Invalid Interface Settings: missing key %s" % key)

    if 'virtualInterfaces' not in settings:
        raise Exception("Invalid Settings: missing virtualInterfaces")
    if 'list' not in settings['virtualInterfaces']:
        raise Exception("Invalid Settings: missing virtualInterfaces list")
    virtualInterfaces = settings['virtualInterfaces']['list']
    for intf in virtualInterfaces:
        for key in ['interfaceId', 'name', 'configType']:
            if key not in intf:
                raise Exception("Invalid Virtual Interface Settings: missing key %s" % key)
            

# This removes/disable hidden fields in the interface settings so we are certain they don't apply
# We do these operations here because we don't want to actually modify the settings
# For example, lets say you have DHCP enabled, but then you choose to bridge that interface to another instead.
# The settings will reflect that dhcp is still enabled, but to the user those fields are hidden.
# It is convenient to keep it enabled in the settings so when the user switches back to their previous settings
# everything is still the same. However, we need to make sure that we don't actually enable DHCP on that interface.
# 
# This function runs through the settings and removes/disables settings that are hidden/disabled in the current configuration.
#
def cleanupSettings( settings ):
    interfaces = settings['interfaces']['list']
    virtualInterfaces = settings['virtualInterfaces']['list']

    # Remove disabled interfaces from regular interfaces list
    # Save them in another field in case anyone needs them
    disabled_interfaces = [ intf for intf in interfaces if intf.get('configType') == 'DISABLED' ]
    new_interfaces = [ intf for intf in interfaces if intf.get('configType') != 'DISABLED' ]
    settings['interfaces']['list'] = new_interfaces
    settings['disabledInterfaces'] = { 'list': disabled_interfaces }

    disabled_virtual_interfaces = [ ]
    new_virtual_interfaces = [ intf for intf in virtualInterfaces ]
    settings['virtualInterfaces']['list'] = new_virtual_interfaces
    settings['disabledVirtualInterfaces'] = { 'list': disabled_virtual_interfaces }
    
    # Disable DHCP if if its a WAN or bridged to another interface
    for intf in interfaces:
        if intf['isWan'] or intf['configType'] == 'BRIDGED':
            for key in list(intf.keys()):
                if key.startswith('dhcp'):
                    del intf[key]

    # Disable NAT options on bridged interfaces
    for intf in interfaces:
        if intf['configType'] == 'BRIDGED':
            if 'v4NatEgressTraffic' in intf: del intf['v4NatEgressTraffic']
            if 'v4NatIngressTraffic' in intf: del intf['v4NatIngressTraffic']

    # Disable Gateway for non-WANs
    for intf in interfaces:
        if intf.get('isWan') != True:
            if 'v4StaticGateway' in intf: del intf['v4StaticGateway']
            if 'v6StaticGateway' in intf: del intf['v6StaticGateway']

    # Disable egress NAT on non-WANs
    # Disable ingress NAT on WANs
    for intf in interfaces:
        if intf['isWan']:
            if 'v4NatIngressTraffic' in intf: del intf['v4NatIngressTraffic']
        if not intf['isWan']:
            if 'v4NatEgressTraffic' in intf: del intf['v4NatEgressTraffic']

    # Remove PPPoE settings if not PPPoE intf
    for intf in interfaces:
        if intf['v4ConfigType'] != 'PPPOE':
            for key in list(intf.keys()):
                if key.startswith('v4PPPoE'):
                    del intf[key]

    # Remove static settings if not static intf
    for intf in interfaces:
        if intf['v4ConfigType'] != 'STATIC':
            for key in list(intf.keys()):
                if key.startswith('v4Static'):
                    del intf[key]

    # Remove auto settings if not auto intf
    for intf in interfaces:
        if intf['v4ConfigType'] != 'AUTO':
            for key in list(intf.keys()):
                if key.startswith('v4Auto'):
                    del intf[key]

    # Remove bridgedTo settincgs if not bridged
    for intf in interfaces:
        if intf['configType'] != 'BRIDGED':
            if 'bridgedTo' in intf: del intf['bridgedTo']

    # In 13.1 we renamed inputFilterRules to accessRules
    # Check for safety NGFW-10791
    # This can be removed after 13.1
    if settings.get('inputFilterRules') != None and settings.get('accessRules') == None:
        print("WARNING: accessRules missing - using inputFilterRules")
        settings['accessRules'] = settings.get('inputFilterRules')

    # In 13.1 we renamed forwardFilterRules to filterRules
    # Check for safety NGFW-10791
    # This can be removed after 13.1
    if settings.get('forwardFilterRules') != None and settings.get('filterRules') == None:
        print("WARNING: filterRules missing - using forwardFilterRules")
        settings['filterRules'] = settings.get('forwardFilterRules')
        
    return


def check_registrar(tmpdir):
    """
    This checks that all files written in tmpdir are properly registered
    in the registrar. If a file is missing in the registrar exit(1) is
    called to exit immediately
    """
    for root, dirs, files in os.walk(tmpdir):
        for file in files:
            rootpath = os.path.join(root,file).replace(tmpdir,"")
            result = registrar.registrar_check_file(rootpath)
            if not result:
                print("File missing in registrar: " + filename)
                cleanup(1)

def calculate_changed_files(tmpdir):
    """
    Compares the contents of tmpdir with the existing filesystem
    Returns a list of files that have changed (using root path)
    """
    cmd = "diff -rq / " + tmpdir + " | grep -v '^Only in' | awk '{print $2}'"
    process = subprocess.Popen(["sh","-c",cmd], stdout=subprocess.PIPE);
    out,err = process.communicate()
    
    changed_files = []
    for line in out.decode('ascii').split():
        if line.strip() != '':
            changed_files.append(line.strip())
    new_files = []
    for root, dirs, files in os.walk(tmpdir):
        for file in files:
            rootpath = os.path.join(root,file).replace(tmpdir,"")
            if not os.path.exists(rootpath):
                new_files.append(rootpath)

    if len(changed_files) > 0:
        print("\nChanged files:")
        for f in changed_files:
            print(f)
    if len(new_files) > 0:
        print("\nNew files:")
        for f in new_files:
            print(f)

    changes = []
    changes.extend(changed_files)
    changes.extend(new_files)
    if len(changes) == 0:
        print("\nNo changed files.")

    return changes

def run_cmd(cmd):
    stdin=open(os.devnull, 'rb')
    p = subprocess.Popen(["sh","-c","%s 2>&1" % (cmd)], stdout=subprocess.PIPE, stdin=stdin )
    for line in iter(p.stdout.readline, ''):
        if line == b'':
            break
        print( line.decode('ascii').strip() )
    p.wait()
    return p.returncode

def copy_files(tmpdir):
    """
    Copy the files from tmpdir into the root filesystem
    """
    cmd = "/bin/cp -ar --remove-destination " + tmpdir+"/*" + " /"
    print("\nCopying files...")
    result = run_cmd(cmd)
    if result != 0:
        print("Failed to copy results: " + str(result))
        return result
    return 0

def run_commands(ops, key):
    """
    Run all the commands for the specified operations
    """
    if not parser.restart_services:
        print("\nSkipping operations " + key + "...")
        return 0
    print("\nRunning operations " + key + "...")
    ret = 0
    for op in ops:
        o = registrar.operations.get(op)
        command = o.get(key)
        if command != None:
            print("\n[" + op + "]: " + command)
            result = run_cmd(command)
            print("[" + op + "]: " + command + " done.")
            if result != 0:
                print("Error[" + str(result) + "]: " + command)
            ret += result
    return ret

def tee_stdout_log():
    tee = subprocess.Popen(["tee", "/var/log/sync.log"], stdin=subprocess.PIPE)
    os.dup2(tee.stdin.fileno(), sys.stdout.fileno())
    os.dup2(tee.stdin.fileno(), sys.stderr.fileno())

def init_modules():
    global modules
    for module in modules:
        try:
            module.initialize()
        except Exception as e:
            traceback.print_exc()
            print("Abort. (errors)")
            cleanup(1)

def sync_to_tmpdir(tmpdir):
    global modules
    print("\nSyncing %s to system..." % parser.filename)

    for module in modules:
        try:
            module.sync_settings( settings, prefix=tmpdir, verbosity=2 )
        except Exception as e:
            traceback.print_exc()
            cleanup(1)

def drop_permissions():
    os.setegid(65534) # nogroup
    os.seteuid(65534) # nobody

def call_without_permissions(func, *args, **kw):
    pid = os.fork()
    if pid == 0:
        drop_permissions()
        func(*args, **kw)
        os._exit(0)
    else:
        (xpid, result) = os.waitpid(pid, 0)
        return result




# Duplicate all stdout to log
tee_stdout_log()

# Globals
modules = [ HostsManager(), DnsMasqManager(),
            InterfacesManager(), RouteManager(),
            IptablesManager(), NatRulesManager(),
            FilterRulesManager(), QosManager(),
            PortForwardManager(), BypassRuleManager(),
            EthernetManager(),
            SysctlManager(), ArpManager(),
            DhcpManager(), RadvdManager(),
            PPPoEManager(), DdclientManager(),
            KernelManager(), EbtablesManager(),
            VrrpManager(), WirelessManager(),
            UpnpManager(), NetflowManager()]
parser = ArgumentParser()
settings = None
tmpdir = None

parser.parse_args()

try:
    tmpdir = tempfile.mkdtemp()
    os.chmod(tmpdir, os.stat(tmpdir).st_mode | stat.S_IEXEC | stat.S_IRGRP | stat.S_IWGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IWOTH | stat.S_IXOTH)
except Exception as e:
    print("Error creating tmp directory.",e)
    traceback.print_exc(e)
    cleanup(1)

try:
    settingsFile = open(parser.filename, 'r')
    settingsData = settingsFile.read()
    settingsFile.close()
    settings = json.loads(settingsData)
except IOError as e:
    print("Unable to read settings file: ",e)
    cleanup(1)

try:
    checkSettings(settings)
    cleanupSettings(settings)
except Exception as e:
    traceback.print_exc(e)
    cleanup(1)

# Write the sanitized file for debugging
# sanitized_filename = (os.path.dirname(parser.filename) + "/network-sanitized.js")
# print("Writing sanitized settings: %s " % sanitized_filename)
# sanitized_file = open( sanitized_filename + ".tmp" , 'w' )
# json.dump(settings, sanitized_file)
# sanitized_file.flush()
# sanitized_file.close()
# os.system("python -m simplejson.tool %s.tmp > %s ; rm %s.tmp " % (sanitized_filename, sanitized_filename, sanitized_filename))

NetworkUtil.settings = settings

init_modules()

result = call_without_permissions(sync_to_tmpdir,tmpdir)
if result != 0:
    cleanup(result)

check_registrar(tmpdir)

changed_files = calculate_changed_files(tmpdir)
operations = registrar.calculate_required_operations(changed_files)
operations = registrar.reduce_operations(operations)
if len(operations) < 1:
    copy_files(tmpdir)
    print("\nDone.")
    cleanup(0)

print("\nRequired operations: ")
for op in operations:
    print(op)
    o = registrar.operations.get(op)
    if o == None:
        print("Operation missing from registrar: " + op)
        cleanup(1)

ret = 0

# Run all pre commands
try:
    ret += run_commands(operations, 'pre_command')
except Exception as e:
    traceback.print_exc()

# Copy files to / filesystem
try:
    ret += copy_files(tmpdir)
except Exception as e:
    traceback.print_exc()

# Run all post commands
try:
    ret += run_commands(operations, 'post_command')
except Exception as e:
    traceback.print_exc()

if ret != 0:
    print("\nDone. (with errors)")
    cleanup(1)
else:
    print("\nDone.")
    cleanup(0)


