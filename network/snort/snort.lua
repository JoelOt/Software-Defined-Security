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

-- Event filtering: rate-limit alert output to avoid log flooding
-- The detection_filter in the rule still fires, but we only LOG once per
-- source IP every 10 seconds. This keeps logs readable during a DDoS.
event_filter =
{
    {
        gid = 1,
        sid = 1000001,
        type = 'limit',
        track = 'by_src',
        count = 1,
        seconds = 10
    }
}

-- Alert configuration: fast alerts to log directory (specified via -l flag)
alert_fast =
{
    file = true
}
