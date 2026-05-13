---------------------------------------------------------------------------
-- Snort 3 Configuration Snippet for Quarantine VNF
---------------------------------------------------------------------------

-- Define network variables (using 'any' since this is a quarantine honeypot)
HOME_NET = 'any'
EXTERNAL_NET = 'any'

-- Configure the IPS module to load our local rules
ips =
{
    enable_builtin_rules = false,
    include = 'local.rules',
}

-- DAQ Configuration for passive interface sniffing (IDS mode)
-- If you need inline mode (IPS) to actively drop packets within the VNF, 
-- change mode to 'inline' and use afpacket with two interfaces.
daq =
{
    modules =
    {
        { name = 'afpacket', mode = 'passive' }
    }
}

-- Alert configuration (output alerts to fast.log)
alert_fast = {
    file = true
}
