Ext.ns('Ung');
Ext.ns('Ung.Alpaca');
Ext.ns('Ung.Alpaca.Pages');
Ext.ns('Ung.Alpaca.Pages.Qos');

if ( Ung.Alpaca.Glue.hasPageRenderer( "qos", "index" )) {
    Ung.Alpaca.Util.stopLoading();
}

Ung.Alpaca.Pages.Qos.Index = Ext.extend( Ung.Alpaca.PagePanel, {
    initComponent : function()
    {
        this.priorityStore = [];
        this.priorityMap = {};

        this.addPriority( 10 , this._( "High" ));
        this.addPriority( 20 , this._( "Normal" ));
        this.addPriority( 30 , this._( "Low" ));

        this.qosGrid = this.buildQosGrid();
        this.statisticsGrid = this.buildStatisticsGrid();
                
        var percentageStore = this.buildPercentageStore();

        Ext.apply( this, {
            defaults : {
                xtype : "fieldset"
            },
            items : [{
                autoHeight : true,
                defaults : {
                    xtype : "textfield"
                },
                items : [{
                    xtype : "checkbox",
                    fieldLabel : this._( "Enabled" ),
                    name : "qos_settings.enabled"
                },{
                    xtype : "numberfield",
                    fieldLabel : this._( "Internet Download Bandwidth" ),
                    name : "qos_settings.download",
                    boxLabel : this._( "kbps" )
                },{
                    xtype : "combo",
                    fieldLabel : this._( "Limit Download To" ),
                    name : "qos_settings.download_percentage",
                    mode : "local",
                    triggerAction : "all",
                    editable : false,
                    width : 60,
                    listWidth : 50,
                    store : percentageStore
                }]
            },{
                autoHeight : true,
                defaults : {
                    xtype : "textfield"
                },
                items : [{
                    xtype : "numberfield",
                    fieldLabel : this._( "Internet Upload Bandwidth" ),
                    name : "qos_settings.upload",                    
                    boxLabel : this._( "kbps" )
                },{
                    xtype : "combo",
                    fieldLabel : this._( "Limit Upload To" ),
                    name : "qos_settings.upload_percentage",
                    mode : "local",
                    triggerAction : "all",
                    editable : false,
                    width : 60,
                    listWidth : 50,
                    store : percentageStore
                }]
            },{
                autoHeight : true,
                defaults : {
                    xtype : "textfield"
                },
                items : [{
                    xtype : "combo",
                    fieldLabel : this._( "Ping Priority" ),
                    name : "qos_settings.prioritize_ping",
                    mode : "local",
                    triggerAction : "all",
                    editable : false,
                    width : 70,
                    listWidth : 60,
                    store : this.priorityStore
                },{
                    xtype : "combo",
                    fieldLabel : this._( "ACK Priority" ),
                    boxLabel : this._( "A High ACK Priority speeds up downloads while uploading" ),
                    name : "qos_settings.prioritize_ack",
                    mode : "local",
                    triggerAction : "all",
                    editable : false,
                    width : 70,
                    listWidth : 60,
                    store : this.priorityStore
                },{
                    xtype : "combo",
                    fieldLabel : this._( "Gaming Priority" ),
                    name : "qos_settings.prioritize_gaming",
                    mode : "local",
                    triggerAction : "all",
                    editable : false,
                    width : 70,
                    listWidth : 60,
                    store : this.priorityStore
                }]
            },{
                xtype : "label",
                html : this._( "QoS Rules" )
            }, this.qosGrid, {
                xtype : "label",
                html : this._( "QoS Statistics" )
            }, this.statisticsGrid ]
        });
        
        Ung.Alpaca.Pages.Qos.Index.superclass.initComponent.apply( this, arguments );
    },

    buildPercentageStore : function()
    {
        var percentageStore = [];
        percentageStore.push([ 100, "100%"]);
        percentageStore.push([ 95, "95%"]);

        for ( var c = 0 ; c < 9 ; c++ ) {
            var v = 100 - ( 10 * ( c + 1 ));
            percentageStore[c+2] = [ v, v + "%"  ];
        }

        return percentageStore;
    },

    buildQosGrid : function()
    {
        var enabledColumn = new Ung.Alpaca.grid.CheckColumn({
            header : this._( "On" ),
            dataIndex : 'enabled',
            sortable: false,
            fixed : true
        });

        var qosGrid = new Ung.Alpaca.EditorGridPanel({
            settings : this.settings,

            recordFields : [ "enabled", "description", "filter", "priority" ],
            selectable : true,
            sortable : false,
            hasReorder: true,
            
            name : "qos_rules",

            recordDefaults : {
                enabled : true,
                priority : 20,
                filter : "",
                description : this._( "[New Entry]" )
            },
            
            plugins : [ enabledColumn ],

            columns : [ enabledColumn, {
                header : this._( "Priority" ),
                width: 60,
                sortable: false,
                fixed : true,
                dataIndex : "priority",
                renderer : function( value, metadata, record )
                {
                    return this.priorityMap[value];
                }.createDelegate( this ),
                editor : new Ext.form.ComboBox({
                    store : this.priorityStore,
                    listWidth : 60,
                    width : 60,
                    triggerAction : "all",
                    mode : "local",
                    editable : false
                })
            },{
                header : this._( "Description" ),
                width: 200,
                sortable: false,
                dataIndex : "description",
                editor : new Ext.form.TextField({
                    allowBlank : false 
                })
            }]
        });

        qosGrid.store.load();
        
        return qosGrid;
    },

    buildStatisticsGrid : function()
    {
        var statisticsGrid = new Ung.Alpaca.EditorGridPanel({
            settings : this.settings,

            recordFields : [ "priority", "rate", "burst", "sent", "tokens", "ctokens" ],
            selectable : false,
            sortable : true,
            saveData : false,
            
            name : "status",

            tbar : [{
                text : "Refresh",
                handler : this.refreshStatistics,
                scope : this
            }],

            columns : [{
                header : this._( "Priority" ),
                width: 55,
                sortable: true,
                dataIndex : "priority"
            },{
                header : this._( "Rate" ),
                width: 75,
                sortable: true,
                dataIndex : "rate"
            },{
                header : this._( "Burst" ),
                width: 75,
                sortable: true,
                dataIndex : "burst"
            },{
                header : this._( "Sent" ),
                width: 75,
                sortable: true,
                dataIndex : "sent"
            },{
                header : this._( "Tokens" ),
                width: 75,
                sortable: true,
                dataIndex : "tokens"
            },{
                header : this._( "CTokens" ),
                width: 75,
                sortable: true,
                dataIndex : "ctokens"
            }]
        });

        statisticsGrid.store.load();
        return statisticsGrid;
    },

    saveMethod : "/qos/set_settings",

    refreshStatistics : function()
    {
        var handler = this.completeRefreshStatistics.createDelegate( this );
        Ung.Alpaca.Util.executeRemoteFunction( "/qos/get_statistics", handler );
    },

    completeRefreshStatistics : function( statistics, response, options )
    {
        if ( !statistics ) return;

        this.statisticsGrid.store.loadData( statistics );
    },
    
    addPriority : function( v, name )
    {
        this.priorityMap[v] = name;
        this.priorityStore.push([v,name]);
    }

});

Ung.Alpaca.Pages.Qos.Index.settingsMethod = "/qos/get_settings";
Ung.Alpaca.Glue.registerPageRenderer( "qos", "index", Ung.Alpaca.Pages.Qos.Index );
