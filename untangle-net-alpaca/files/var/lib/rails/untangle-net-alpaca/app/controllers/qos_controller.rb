# $HeadURL$
# Copyright (c) 2007-2008 Untangle, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License, version 2,
# as published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but
# AS-IS and WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE, TITLE, or
# NONINFRINGEMENT.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301 USA.
#
class QosController < ApplicationController
  def get_settings
    settings = {}

    qos_settings = QosSettings.find( :first )
    qos_settings = QosSettings.new if qos_settings.nil?
    settings["qos_settings"] = qos_settings

    wan_interfaces = Interface.wan_interfaces
    settings["bandwidth"] = wan_interfaces
    
    settings["qos_rules"] = QosRule.find( :all )

    qos_classes = QosClass.find( :first )
    if qos_classes.nil?
      QosClass.new( :class_id => 0, :upload_reserved => 80, :upload_limit => 100, :download_limit =>   0 ).save
      QosClass.new( :class_id => 1, :upload_reserved => 10, :upload_limit => 100, :download_limit => 100 ).save
      QosClass.new( :class_id => 2, :upload_reserved =>  5, :upload_limit => 100, :download_limit => 100 ).save
      QosClass.new( :class_id => 3, :upload_reserved =>  1, :upload_limit => 100, :download_limit => 100 ).save
      QosClass.new( :class_id => 4, :upload_reserved =>  1, :upload_limit => 100, :download_limit => 100 ).save
      QosClass.new( :class_id => 5, :upload_reserved =>  1, :upload_limit =>  75, :download_limit =>  75 ).save
      QosClass.new( :class_id => 6, :upload_reserved =>  1, :upload_limit =>  50, :download_limit =>  50 ).save
      QosClass.new( :class_id => 7, :upload_reserved =>  1, :upload_limit =>  10, :download_limit =>  10 ).save
    end
    settings["qos_classes"] = QosClass.find( :all )

    settings["status"] = os["qos_manager"].status( wan_interfaces )
    settings["sessions"] = os["qos_manager"].sessions
    settings["start_time"] = os["qos_manager"].start_time

    ## Interface enumeration
    settings["interface_enum"] = build_interface_enum()

    json_result( :values => settings )
  end

  def get_statistics
    json_result( :values => os["qos_manager"].status )
  end

  def get_sessions
    json_result( :values => os["qos_manager"].sessions )
  end
  
  def set_settings
    s = json_params
        
    wan_interfaces = s["bandwidth"]
    wan_interfaces.each do |w|
      conditions = [ "os_name = ? AND name = ? AND mac_address = ? AND wan = ? AND id = ?", 
                     w["os_name"], w["name"], w["mac_address"], true, w["id"]]
      wan_interface = Interface.find( :all, :conditions => conditions )
      if ( wan_interface.length != 1 )
        logger.warn "Unable to find WAN interface for #{w.inspect}"
        next
      end

      wan_interface = wan_interface[0]
      wan_interface.upload_bandwidth = w["upload_bandwidth"]
      wan_interface.download_bandwidth = w["download_bandwidth"]
      wan_interface.save
    end

    qos_settings = QosSettings.find( :first )
    qos_settings = QosSettings.new if qos_settings.nil?
    qos_settings.update_attributes( s["qos_settings"] )
    qos_settings.save

    QosRule.destroy_all
    position = 0
    s["qos_rules"].each do |entry| 
      qos_rule = QosRule.new( entry )
      qos_rule.position = position
      position += 1
      qos_rule.save
    end

    QosClass.destroy_all
    s["qos_classes"].each do |entry| 
      QosClass.new( entry ).save
    end

    os["packet_filter_manager"].commit

    json_result
  end

  alias_method :index, :extjs
end
