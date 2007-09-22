## REVIEW.  there should be an observer, or some global management framework
require_dependency "os_library/debian/packet_filter_manager"

class OSLibrary::Debian::NetworkManager < OSLibrary::NetworkManager
  include Singleton

  Service = "/etc/init.d/networking"
  InterfacesConfigFile = "/etc/network/interfaces"
  InterfacesStatusFile = "/etc/network/run/ifstate"

  def interfaces
    logger.debug( "Running inside of the network manager for debian" )

    interfaceArray = []

    devices=`find /sys/devices -name 'net:*' | sed 's|.*net:||'`

    ## This is test code to fake a third interface
    devices << "dummy0" if File.exists?( "/sys/class/net/dummy0" )

    devices.each do |os_name|
      os_name = os_name.strip

      bus_id=""
      mac_address = File.open( "/sys/class/net/#{os_name}/address", "r" ) { |f| f.readline.strip }

      interfaceArray << PhysicalInterface.new( os_name, mac_address, bus_id )
    end
    
    interfaceArray
  end

  def commit
    interfaces_file = []
    interfaces_file << header
    Interface.find( :all ).each do |interface|
      config = interface.current_config
      ## REVIEW refactor me.
      case config
      when IntfStatic
        interfaces_file << static( interface, config )
      when IntfDynamic
        interfaces_file << dynamic( interface, config )
      when IntfBridge
        interfaces_file << bridge( interface, config )
      end
    end

    ## Delete all empty or nil parts
    interfaces_file = interfaces_file.delete_if { |p| p.nil? || p.empty? }

    File.open( InterfacesConfigFile, "w" ) { |f| f.print( interfaces_file.join( "\n" ), "\n" ) }
    
    ## Restart networking
    ## Clear out all of the interface state.
    File.open( InterfacesStatusFile, "w" ) { |f| f.print( "lo=lo" ) }

    raise "Unable to reconfigure network settings." unless Kernel.system( "#{Service} start" )

    ## XXX THIS SHOULDN'T BE HERE ##
    OSLibrary::Debian::PacketFilterManager.instance.commit
  end

  ## Given an interface, this returns the expected bridge name
  def self.bridge_name( interface )
    "br.#{interface.os_name}"
  end

  private

  ## Dump out the configuration for a statically configured interface.
  def static( interface, static )
    i = nil

    ## name of the interface
    name = interface.os_name
    
    if static.nil?
      logger.warn( "The interface #{interface} is not configured" )
      return ""
    end
    
    bridge = bridgeSettings( interface, static.mtu )
    
    mtu = mtuSetting( static.mtu )
    
    ## set the name
    ## update the index to 0 (bridges are configured as the base so they are not deconfigured on restart)
    ## Clear the MTU because that is set in the bridge
    unless bridge.empty?
      name = OSLibrary::Debian::NetworkManager.bridge_name( interface )
      i = 0
      mtu = nil
    end
    
    ## Configure each IP and then join it all together with some newlines.
    static.ip_networks.map do |ip_network|
      ip_network_name = "#{name}#{i.nil? ? "" : ":#{i}"}"
      i = i.nil? ? 0 : i + 1

      base = bridge + "\n"
      
      ## Only add the bridge string on the first one
      bridge = ""

      base += <<EOF
auto #{ip_network_name}
iface #{ip_network_name} inet static
\taddress #{ip_network.ip}
\tnetmask #{OSLibrary::NetworkManager.parseNetmask( ip_network.netmask)}
EOF

      ## Append the MTU
      base += mtu unless mtu.nil?
      mtu = nil

      base
    end.join( "\n" )
  end

  def dynamic( interface, dynamic )
    ## REVIEW this is the first area that requires managers for separate files.
    ## this is updated in /etc/network/interfaces.
    ## The hostname may be modified here, or in /etc/dhcp3/dhclient.conf, ...
    ## overrides definitely go in /etc/dhcp3/dhclient.conf
    ## Default gateway override settings?

    ## REVIEW what should timeout be on configuring the interface

    i = nil

    ## name of the interface
    name = interface.os_name
    
    if dynamic.nil?
      logger.warn( "The interface #{interface} is not configured" )
      return ""
    end
    
    bridge = bridgeSettings( interface, dynamic.mtu, "dhcp" )
    
    mtu = mtuSetting( dynamic.mtu )
    
    ## set the name
    return bridge unless bridge.empty?

    <<EOF
auto #{name}
iface #{name} inet dhcp
EOF
  end

  def bridge( interface, bridge )
    logger.debug( "Nothing needed for a bridge interface" )
    ""
  end

  ## These are the settings that should be appended to the first
  ## interface index that is inside of the interface (if this is in fact a bridge)
  def bridgeSettings( interface, mtu, config_method = "manual"  )
    ## Check if this is a bridge
    bridged_interfaces = interface.bridged_interfaces
    
    ## Create a new set of bridged interfaces
    bridged_interfaces = bridged_interfaces.map { |ib| ib.interface }
    
    ## Delete all of the nil interfaces and the ones where the bridge type isn't set properly.
    bridged_interfaces = bridged_interfaces.delete_if do |ib| 
      ib.nil? || ib.config_type != InterfaceHelper::ConfigType::BRIDGE
    end

    ## If this is nil or empty, it is not a bridge.    
    return "" if ( bridged_interfaces.nil? || bridged_interfaces.empty? )
    
    ## Append this interface
    bridged_interfaces << interface

    bridge_name = self.class.bridge_name( interface )

    ## The bridge is configured as br.<intf> and then all of the ips
    ## are configured as br.<intf>:0 - done this way so restart
    ## doesn't call ifconfig br.intf down, if this happens the
    ## bridge has to relearn creating 30seconds of down time.

    <<EOF
auto #{bridge_name}
iface #{bridge_name} inet #{config_method}
\turchin_bridge_ports #{bridged_interfaces.map{ |i| i.os_name }.join( " " )}
\turchin_debug true
\tbridge_ageing 900
#{mtuSetting( mtu, "urchin_bridge_" )}
EOF
  end

  ## mtu is always set, just in case the user overrides it
  def mtuSetting( mtu, prefix = "" )
    ## MTU of 0 or less is ignored
    mtu = OSLibrary::NetworkManager::DefaultMTU if mtu <= 0

    return "\t#{prefix}mtu #{mtu}"
  end

  def header
    <<EOF
## Auto Generated by the Untangle Net Urchin
## If you modify this file manually, your changes
## may be overriden

auto cleanup
iface cleanup inet manual
\turchin_debug true

## Configuration for the loopback interface
auto lo
iface lo inet loopback
EOF
  end
end
