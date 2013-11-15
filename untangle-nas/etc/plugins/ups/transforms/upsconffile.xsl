<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
    
<xsl:output method="text" omit-xml-declaration="yes" encoding="UTF-8" indent="no"/>
    
<xsl:template match="upsdevices">
<xsl:text>#####   WARNING!!! - This configuration file generated by Untangle NAS. DO NOT MANUALLY EDIT.  #####
            
            
</xsl:text>
<xsl:apply-templates select="ups" />
</xsl:template>
    
  
    
<xsl:template match="ups">
     
<xsl:if test="@enabled = 1">
<xsl:text>[</xsl:text><xsl:value-of select="@id"/><xsl:text>]</xsl:text><xsl:text>            
</xsl:text>
<xsl:text>    driver  = </xsl:text><xsl:value-of select="@driver"/><xsl:text>
</xsl:text>
<xsl:text>    port    = /dev/</xsl:text><xsl:value-of select="@port"/><xsl:text>
</xsl:text>
<xsl:text>    desc    = </xsl:text><xsl:value-of select="@desc"/><xsl:text>
</xsl:text>
<xsl:text>    sdorder = </xsl:text><xsl:value-of select="@sorder"/><xsl:text>
</xsl:text>
<xsl:for-each select="extrasettings/extrasetting">
<xsl:text>    </xsl:text><xsl:value-of select="@name"/><xsl:text>    =    </xsl:text><xsl:value-of select="@value"/><xsl:text>
</xsl:text>
</xsl:for-each>
<xsl:text>
              
              
             
</xsl:text>
</xsl:if>
</xsl:template>
  
    
 </xsl:stylesheet>