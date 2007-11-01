## REVIEW This should be renamed to dhcp_server_controller.
## REVIEW Should create a consistent way to build these tables.
class DhcpController < ApplicationController
  def index
    manage
    render :action => 'manage'
  end

  def register_menu_items
    menu_organizer.register_item( "/main/dhcp_server", Alpaca::Menu::Item.new( 300, "DHCP Server", "/dhcp" ))
  end

  def create_static_entry
    @static_entry = DhcpStaticEntry.new
  end

  def manage
    @dhcp_server_settings = DhcpServerSettings.find( :first )
    @dhcp_server_settings = DhcpServerSettings.new if @dhcp_server_settings.nil?
    @static_entries = DhcpStaticEntry.find( :all )

    ## Retrieve all of the dynamic entries from the DHCP server manager
    refresh_dynamic_entries
  end

  def refresh_dynamic_entries
    ## Retrieve all of the dynamic entries from the DHCP server manager
    @dynamic_entries = os["dhcp_server_manager"].dynamic_entries    
  end

  def stylesheets
    [ "dhcp/static-entry", "dhcp/dynamic-entry", "borax/list-table" ]
  end

  def scripts
    [ "dhcp_server_manager" ] 
  end
end
