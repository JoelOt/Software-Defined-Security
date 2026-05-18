---------------------------------------------------------------------------
-- Snort 3 Configuration for Federated SDN Quarantine VNF
-- Architecture: Data Plane (Security VNF)
--
-- Launched via: sudo ./start_snort.sh <switch_name>
-- Logs written to: network/snort/logs/
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
-- The interface is specified via the -i flag in start_snort.sh
daq =
{
    modules =
    {
        { name = 'afpacket', mode = 'passive' }
    }
}

-- Alert configuration: fast alerts to log directory (specified via -l flag)
alert_fast =
{
    file = true
}
