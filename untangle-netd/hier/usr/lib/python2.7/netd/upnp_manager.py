import os
import sys
import subprocess
import datetime
import traceback
import re
from shutil import move
from netd.network_util import NetworkUtil

# This class is responsible for writing 
# based on the settings object passed from sync-settings.py
class UpnpManager:
    upnpDaemonConfFilename = "/etc/miniupnpd/miniupnpd.conf"
    restartHookFilename = "/etc/untangle-netd/post-network-hook.d/990-restart-upnp"
    iptablesFilename = "/etc/untangle-netd/iptables-rules.d/741-upnp"
    upnpDaemonInitFilename = "/etc/init.d/miniupnpd"

    init_start_daemon_regex = re.compile(r'^if \[ "\${START_DAEMON}" != "1" \]')
    init_default_check_interface_regex = re.compile(r'^if \[ -z "\${MiniUPnPd_EXTERNAL_INTERFACE}" \]')
    init_default_check_listening_ip_regex = re.compile(r'^if \[ -z "\${MiniUPnPd_LISTENING_IP}" \]')
    init_init_iptables_regex = re.compile(r'^(\s+iptables_init_nat_tables)')
    init_init_ip6tables_regex = re.compile(r'^(\s+if \[ "\${MiniUPnPd_ip6tables_enable}" = "yes" \] ; then ip6tables_init_fw_tables ; fi)')
    init_stop_iptables_regex = re.compile(r'^(\s+iptables_stop_nat_tables)')
    init_stop_ip6tables_regex = re.compile(r'^(\s+if \[ "\${MiniUPnPd_ip6tables_enable}" = "yes" \] ; then ip6tables_stop_fw_tables ; fi)')
    init_daemon_start_regex = re.compile(r'^(\s+start-stop-daemon -q --start --exec "/usr/sbin/miniupnpd" --)')

    def write_upnp_daemon_conf( self, settings, prefix="", verbosity=0 ):
        """
        Create UPnP configuration file
        """
        filename = prefix + self.upnpDaemonConfFilename
        fileDir = os.path.dirname( filename )
        if not os.path.exists( fileDir ):
            os.makedirs( fileDir )

        file = open( filename, "w+" )
        file.write("## Auto Generated\n");
        file.write("## DO NOT EDIT. Changes will be overwritten.\n");

        wan_interfaces = []
        lan_interfaces = []
        for intf in settings['interfaces']['list']:
        	if intf.get('disabled'):
        		continue
        	if intf.get('isWan'):
        		wan_interfaces.append(intf.get('physicalDev'))
        	else:
        		lan_interfaces.append(intf.get('physicalDev'))
        file.write("# Server options\n");
        # WAN interface
        file.write("ext_ifname=%s\n" % " ".join(wan_interfaces))
        # LAN interface
        file.write("listening_ip=%s\n" % " ".join(lan_interfaces))

        if settings['upnpSettings'].get('upnpEnabled') is False:
            file.flush()
            file.close()
            os.system("chmod a+x %s" % filename)
            if verbosity > 0: print "UpnpManager: Wrote %s" % filename
            return

        file.write("port=%d\n" % settings['upnpSettings'].get('listenPort'))
        file.write("enable_natpmp=yes\n")
        file.write("enable_upnp=yes\n")
        # Secure mode
        file.write("secure_mode=%s\n" % "yes" if settings['upnpSettings'].get('secureMode') else "no")
        # Minimum lifetime
        file.write("min_lifetime=%d\n" % settings['upnpSettings'].get('minimumLifetime'))
        # Maximium lifetime
        file.write("max_lifetime=%d\n" % settings['upnpSettings'].get('maximumLifetime'))
        # file.write("lease_file=/var/lib/misc/upnp.leases\n")
        file.write("system_uptime=yes\n")

        file.write("upnp_forward_chain=UPnP\n")
        file.write("upnp_nat_chain=UPnP\n")

        file.write("\n# Client notifications\n");
        file.write("notify_interval=60\n")
        # Notify download speed
        notify_download_speed = settings['upnpSettings'].get('downloadSpeed')
        file.write("%sbitrate_down=%d\n" % ("#" if notify_download_speed == 0 else "", notify_download_speed) )
        # Notify upload speed
        notify_upload_speed = settings['upnpSettings'].get('uploadSpeed')
        file.write("%sbitrate_up=%d\n" % ("#" if notify_upload_speed == 0 else "", notify_upload_speed) )
        file.write("uuid=b014febc-1170-4421-9f04-852de5742a80\n")
        file.write("serial=12345678\n")
        file.write("model_number=1\n")

        file.write("\n# Rules\n");
        # Rules
        for rule in settings['upnpSettings']['upnpRules']['list']:
            if rule.get('enabled') is False:
                continue
            upnp_rule_action = "allow" if rule.get('allow') else "deny"
            upnp_rule_external_ports = "0-65535"
            upnp_rule_internal_address = "0.0.0.0/0"
            upnp_rule_internal_ports = "0-65535"
            for condition in rule['conditions']['list']:
                if condition.get('conditionType') == "DST_PORT":
                    upnp_rule_external_ports = condition.get('value')
                elif condition.get('conditionType') == "SRC_ADDR":
                    upnp_rule_internal_address = condition.get('value')
                elif condition.get('conditionType') == "SRC_PORT":
                    upnp_rule_internal_ports = condition.get('value')
            upnp_rule = " ".join([upnp_rule_action, upnp_rule_external_ports, upnp_rule_internal_address, upnp_rule_internal_ports])
            file.write("%s\n" % upnp_rule )

        # Write custom advanced options
        if settings['upnpSettings'].get('cystomOptions') != None:
            file.write("\# Custom  options\n");
            file.write("%s\b" % ( settings['upnpSettings'].get('cystomOptions') ) )
            file.write("\n");

        file.write("\n");
        file.flush()
        file.close()

        if verbosity > 0: print "UpnpManager: Wrote %s" % filename
        return

    def write_restart_upnp_daemon_hook( self, settings, prefix="", verbosity=0 ):
        """
        Create network process extension to restart or stop daemon
        """
        filename = prefix + self.restartHookFilename
        fileDir = os.path.dirname( filename )
        if not os.path.exists( fileDir ):
            os.makedirs( fileDir )

        file = open( filename, "w+" )
        file.write("#!/bin/dash");
        file.write("\n\n");

        file.write("## Auto Generated\n");
        file.write("## DO NOT EDIT. Changes will be overwritten.\n");
        file.write("\n");

        if settings['upnpSettings'].get('upnpEnabled') is False:
            file.write(r"""
UPNPD_PID="`pidof miniupnpd`"

# Restart dnsmasq if it isnt found
# Or if dnsmasq.conf or hosts.dnsmasq has been written since dnsmasq was started
if [ ! -z "$UPNPD_PID" ] ; then
    /etc/init.d/miniupnpd stop
fi
""")
        else:
            file.write(r"""
UPNPD_PID="`pidof miniupnpd`"

# Restart dnsmasq if it isnt found
# Or if dnsmasq.conf or hosts.dnsmasq has been written since dnsmasq was started
if [ -z "$UPNPD_PID" ] ; then
    /etc/untangle-netd/iptables-rules.d/741-upnp
    /etc/init.d/miniupnpd restart
# use not older than (instead of newer than) because it compares seconds and we want an equal value to still do a restart
elif [ ! /etc/miniupnpd/miniupnpd.conf -ot /proc/$UPNPD_PID ] ; then
    /etc/untangle-netd/iptables-rules.d/741-upnp
    /etc/init.d/miniupnpd restart
fi
""")

        file.write("\n");
        file.flush()
        file.close()
    
        os.system("chmod a+x %s" % filename)
        if verbosity > 0: print "UpnpManager: Wrote %s" % filename
        return

    def write_iptables_hook( self, settings, prefix="", verbosity=0 ):
        """
        Create iptables configuraton for daemon
        """
        filename = prefix + self.iptablesFilename
        fileDir = os.path.dirname( filename )
        if not os.path.exists( fileDir ):
            os.makedirs( fileDir )

        file = open( filename, "w+" )
        file.write("#!/bin/dash");
        file.write("\n\n");

        file.write("## Auto Generated\n");
        file.write("## DO NOT EDIT. Changes will be overwritten.\n");
        file.write("\n");

        file.write(r"""
IPTABLES=${IPTABLES:-iptables}
IP="/bin/ip"
CHAIN=UPnP

MINIUPNPD_CONF=/etc/miniupnpd/miniupnpd.conf
LISTENING_PORT=UNKNOWN
EXTERNAL_INTERFACE=UNKNOWN
EXTERNAL_IP_ADDRESS=UNKNOWN

get_listening_port()
{
    LISTENING_PORT="$(LC_ALL=C grep ^port /etc/miniupnpd/miniupnpd.conf | cut -d= -f2)"
}

get_external_interface()
{
        EXTERNAL_INTERFACE="$(LC_ALL=C grep ^ext_ifname /etc/miniupnpd/miniupnpd.conf | cut -d= -f2)"
}

get_external_ip_address()
{
        EXTERNAL_IP_ADDRESS="$(LC_ALL=C ${IP} addr show ${EXTERNAL_INTERFACE} | grep "inet " | awk '{ print $2 }' | cut -d"/" -f1)"
}

flush_upnp_iptables_rules()
{
        ${IPTABLES} -t filter -D filter-rules-input  --protocol tcp  -m comment --comment "UPNP daemon listener"  -m multiport  --destination-ports ${LISTENING_PORT}  -j RETURN >/dev/null 2>&1

        # Clean the nat tables
        ${IPTABLES} -t nat -F ${CHAIN} || true
        ${IPTABLES} -t nat -D PREROUTING -d ${EXTERNAL_IP_ADDRESS} -i ${EXTERNAL_INTERFACE} -j ${CHAIN} || true
        ${IPTABLES} -t nat -X ${CHAIN} || true

        # Clean the filter tables
        ${IPTABLES} -t filter -F ${CHAIN} || true
        ${IPTABLES} -t filter -D FORWARD -i ${EXTERNAL_INTERFACE} ! -o ${EXTERNAL_INTERFACE} -j ${CHAIN} || true
        ${IPTABLES} -t filter -X ${CHAIN} || true

}

insert_upnp_iptables_rules()
{
        ${IPTABLES} -t filter -I filter-rules-input  --protocol tcp  -m comment --comment "UPNP daemon listener"  -m multiport  --destination-ports ${LISTENING_PORT}  -j RETURN >/dev/null 2>&1

        # Initialize the PREROUTING chain first
        ${IPTABLES} -t nat -N ${CHAIN}
        ${IPTABLES} -t nat -A PREROUTING -d ${EXTERNAL_IP_ADDRESS} -i ${EXTERNAL_INTERFACE} -j ${CHAIN}
        ${IPTABLES} -t nat -F ${CHAIN}

        # then do the FORWARD chain
        ${IPTABLES} -t filter -N ${CHAIN}
        ${IPTABLES} -t filter -I FORWARD -i ${EXTERNAL_INTERFACE} ! -o ${EXTERNAL_INTERFACE} -j ${CHAIN}
        ${IPTABLES} -t filter -F ${CHAIN}
}

get_listening_port
get_external_interface
get_external_ip_address

flush_upnp_iptables_rules

if [ "${LISTENING_PORT}" != "
" ] ; then
    echo "[`date`] upnp is running. Inserting rules."
    insert_upnp_iptables_rules
fi
""")


        file.write("\n");
        file.flush()
        file.close()
    
        os.system("chmod a+x %s" % filename)
        if verbosity > 0: print "UpnpManager: Wrote %s" % filename
        return

    def write_upnp_daemon_init_hook( self, settings, prefix="", verbosity=0 ):
        """
        Modify miniupnpd's daemon to not manage iptables and not to use /etc/default/minipnpd
        """
        filename = self.upnpDaemonInitFilename
        tempFilename = prefix + self.upnpDaemonInitFilename + ".tmp"

        fileDir = os.path.dirname( tempFilename )
        if not os.path.exists( fileDir ):
            os.makedirs( fileDir )

        file = open( tempFilename, "w+" )
        readFile = open( filename, "r" )

        for line in readFile:
            matches = re.search(self.init_start_daemon_regex, line)
            if matches:
                line =  "if [ \"\" = \"x\" ] \n"
            matches = re.search(self.init_default_check_interface_regex, line)
            if matches:
                line =  "if [ \"\" = \"x\" ] \n"
            matches = re.search(self.init_default_check_listening_ip_regex, line)
            if matches:
                line =  "if [ \"\" = \"x\" ] \n"
            matches = re.search(self.init_init_iptables_regex, line)
            if matches:
                line =  "#" + matches.group(1) + "\n"
            matches = re.search(self.init_init_ip6tables_regex, line)
            if matches:
                line =  "#" + matches.group(1) + "\n"
            matches = re.search(self.init_stop_iptables_regex, line)
            if matches:
                line =  "#" + matches.group(1) + "\n"
            matches = re.search(self.init_stop_ip6tables_regex, line)
            if matches:
                line =  "#" + matches.group(1) + "\n"
            matches = re.search(self.init_daemon_start_regex, line)
            if matches:
                line =  matches.group(1) + " -N -f /etc/miniupnpd/miniupnpd.conf\n"
            file.write(line)

        readFile.close()

        file.write("\n");
        file.flush()
        file.close()

        move(tempFilename, filename)
    
        os.system("chmod a+x %s" % filename)
        if verbosity > 0: print "UpnpManager: Wrote %s" % filename
        return

    def sync_settings( self, settings, prefix="", verbosity=0 ):

        if verbosity > 1: print "UpnpManager: sync_settings()"
        
        self.write_upnp_daemon_conf( settings, prefix, verbosity )
        self.write_restart_upnp_daemon_hook( settings, prefix, verbosity )
        self.write_iptables_hook( settings, prefix, verbosity )
        self.write_upnp_daemon_init_hook( settings, prefix, verbosity )

        return
