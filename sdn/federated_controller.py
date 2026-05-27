import os
import time
from dotenv import load_dotenv

load_dotenv()

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types, ipv4
from ryu.lib import hub

from sdn.utils import DLTManager, TestDLTManager, ThreatStatus

# Snort VNF port is discovered dynamically via OFPPortDescStatsReply
LOCAL_SUBNET_PREFIX = os.environ.get('LOCAL_SUBNET_PREFIX', '10.0.1.')
DROP_HARD_TIMEOUT = 60 # Drop for 60 seconds locally


class FederatedController(app_manager.RyuApp):
    """
    Federated SDN Controller implementing the Zero-Trust Architecture.
    Acts symmetrically as both Victim (detects and drops) and Source (quarantines).
    """
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(FederatedController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.datapaths = {}
        self.snort_ports = {}  # dpid -> port_no (discovered dynamically)
        
        # Configure professional logging with millisecond timestamps for performance validation
        import logging
        log_format = '%(asctime)s.%(msecs)03d [%(levelname)s] [FederatedController] %(message)s'
        formatter = logging.Formatter(log_format, datefmt='%H:%M:%S')
        for handler in logging.root.handlers:
            handler.setFormatter(formatter)
        if not logging.root.handlers:
            logging.basicConfig(level=logging.INFO, format=log_format, datefmt='%H:%M:%S')
        
        self.logger.info("Initialized Controller for Domain Subnet: %s", LOCAL_SUBNET_PREFIX)
        
        # Telemetry state
        # flow_stats[datapath_id][ipv4_src] = (last_packet_count, last_time)
        self.flow_stats = {}
        
        # Threat state: Keep track of IPs we have locally dropped
        self.dropped_ips = set()
        
        # 1. Initialize DLT Manager
        if os.environ.get('USE_TEST_DLT', '0') == '1':
            self.dlt_manager = TestDLTManager()
        else:
            self.dlt_manager = DLTManager()
        
        # 2. Start DLT event listener non-blocking thread
        self.dlt_manager.start_event_listener(self._dlt_event_callback)
        
        # 3. Start Telemetry monitor thread
        self.monitor_thread = hub.spawn(self._monitor)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        self.datapaths[datapath.id] = datapath
        self.flow_stats[datapath.id] = {}

        # Default rule: send unknown packets to controller
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

        # Request port descriptions to discover the Snort VNF port dynamically
        req = parser.OFPPortDescStatsRequest(datapath)
        datapath.send_msg(req)

    @set_ev_cls(ofp_event.EventOFPPortDescStatsReply, MAIN_DISPATCHER)
    def port_desc_stats_reply_handler(self, ev):
        """
        Discovers the Snort VNF port by scanning OVS port names.
        The topology attaches a dummy interface named '<switch>-snort'.
        """
        datapath = ev.msg.datapath
        dpid = datapath.id
        for port in ev.msg.body:
            port_name = port.name.decode() if isinstance(port.name, bytes) else port.name
            if port_name.endswith('-snort'):
                self.snort_ports[dpid] = port.port_no
                self.logger.info("[VNF] Snort VNF discovered on dpid=%s port=%d (name=%s)",
                                 dpid, port.port_no, port_name)

    def add_flow(self, datapath, priority, match, actions, buffer_id=None, hard_timeout=0, idle_timeout=0):
        """
        Helper method to insert OpenFlow rules.
        """
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                    priority=priority, match=match,
                                    instructions=inst, hard_timeout=hard_timeout,
                                    idle_timeout=idle_timeout)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                    match=match, instructions=inst,
                                    hard_timeout=hard_timeout, idle_timeout=idle_timeout)
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        """
        Standard L2 MAC learning and flow installation.
        """
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        dst = eth.dst
        src = eth.src
        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})

        # Learn MAC
        self.mac_to_port[dpid][src] = in_port

        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        # Install flow to avoid packet-in next time
        if out_port != ofproto.OFPP_FLOOD:
            ipv4_pkt = pkt.get_protocol(ipv4.ipv4)
            if ipv4_pkt:
                # Match on IPv4 source/destination to allow fine-grained telemetry tracking
                match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src, eth_type=ether_types.ETH_TYPE_IP, ipv4_src=ipv4_pkt.src, ipv4_dst=ipv4_pkt.dst)
                flow_priority = 10
            else:
                match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src, eth_type=eth.ethertype)
                flow_priority = 1
                
            if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                self.add_flow(datapath, flow_priority, match, actions, msg.buffer_id)
                return
            else:
                self.add_flow(datapath, flow_priority, match, actions)

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)

    def _monitor(self):
        """
        Telemetry Loop: Detects anomalies (e.g., volumetric DDoS).
        Requests flow statistics every 3 seconds.
        """
        self.logger.info("Starting Telemetry monitoring loop...")
        while True:
            for datapath in self.datapaths.values():
                self._request_stats(datapath)
            hub.sleep(3)

    def _request_stats(self, datapath):
        parser = datapath.ofproto_parser
        req = parser.OFPFlowStatsRequest(datapath)
        datapath.send_msg(req)

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def _flow_stats_reply_handler(self, ev):
        """
        Parses statistics, calculates PPS, and mitigates if threshold exceeded.
        """
        # (Periodic healthcheck log silenced to reduce console spam)
        
        body = ev.msg.body
        datapath = ev.msg.datapath
        dpid = datapath.id
        current_time = time.time()

        # Aggregate packet counts by source IP
        src_packet_counts = {}
        for stat in body:
            if stat.priority == 10:
                ipv4_src = stat.match.get('ipv4_src')
                ipv4_dst = stat.match.get('ipv4_dst')
                
                # Only track telemetry if we are the VICTIM (dst is local) and attack is from OUTSIDE (src is external)
                if ipv4_src and ipv4_dst and self._is_local_ip(ipv4_dst) and not self._is_local_ip(ipv4_src):
                    src_packet_counts[ipv4_src] = src_packet_counts.get(ipv4_src, 0) + stat.packet_count

        for ipv4_src, packet_count in src_packet_counts.items():
            # Calculate Packets Per Second (PPS)
            if ipv4_src in self.flow_stats[dpid]:
                last_packet_count, last_time = self.flow_stats[dpid][ipv4_src]
                dt = current_time - last_time
                if dt > 0:
                    pps = (packet_count - last_packet_count) / dt
                    
                    if pps > 0:
                        self.logger.info("[TELEMETRY] IP %s current rate: %.2f pps", ipv4_src, pps)
                    
                    threshold = int(os.environ.get('TELEMETRY_PPS_THRESHOLD', '500'))
                    if pps > threshold and ipv4_src not in self.dropped_ips:
                        self.logger.warning("[STAGE 1: DETECTION] Volumetric anomaly! %s is sending %.2f pps (Threshold: %s).", ipv4_src, pps, threshold)
                        self._trigger_local_mitigation(datapath, ipv4_src)
                        
            self.flow_stats[dpid][ipv4_src] = (packet_count, current_time)

    def _trigger_local_mitigation(self, datapath, attacker_ip):
        """
        Workflow Step 1 (Victim): Detects anomaly -> Pushes DROP -> Publishes 'Pending' to DLT.
        """
        self.logger.info("[STAGE 2: MITIGATION] Enforcing immediate local DROP for %s and publishing to DLT.", attacker_ip)
        self.dropped_ips.add(attacker_ip)
        
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        
        # Push hard timeout DROP rule (actions list is empty to drop)
        match = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_src=attacker_ip)
        self.add_flow(datapath, priority=100, match=match, actions=[], hard_timeout=DROP_HARD_TIMEOUT)
        
        # Publish to the DLT as a Pending threat
        self.dlt_manager.publish_threat(attacker_ip)

    def _dlt_event_callback(self, event):
        """
        Callback handler for smart contract events.
        Executes without blocking the Ryu event loop.
        """
        event_name = event.event
        args = event.args
        
        # Support both real contract events ('ip') and mock test events ('ipAddress')
        attacker_ip = args.get('ip') or args.get('ipAddress')
        
        if event_name == 'ThreatReported':
            self.logger.info("[DLT EVENT] ThreatReported (Pending) received for IP %s", attacker_ip)
            self._handle_pending_threat(attacker_ip)
            
        elif event_name == 'StatusUpdated':
            # Support both real contract events ('newStatus') and mock test events ('status')
            status_val = args.get('newStatus') if args.get('newStatus') is not None else args.get('status')
            
            try:
                status_label = ThreatStatus(status_val).name
            except ValueError:
                status_label = f"UNKNOWN ({status_val})"
                
            self.logger.info("[DLT EVENT] StatusUpdated received. IP %s status changed to %s", attacker_ip, status_label)
            if status_val == ThreatStatus.QUARANTINED:
                self._handle_quarantined_threat(attacker_ip)

    def _is_local_ip(self, ip_address):
        """
        Checks if the reported IP belongs to our specific domain.
        """
        return ip_address.startswith(LOCAL_SUBNET_PREFIX)

    def _handle_pending_threat(self, attacker_ip):
        """
        Workflow Step 2 (Source): Catches 'Pending' -> Redirects local attacker to Snort -> Updates to 'Quarantined'.
        """
        if not self._is_local_ip(attacker_ip):
            self.logger.info("[SFC] IP %s is not in our domain. Ignoring event.", attacker_ip)
            return
            
        self.logger.warning("[STAGE 3: QUARANTINE] Attacker %s belongs to our domain! Tunneling to Snort VNF...", attacker_ip)
        
        for datapath in self.datapaths.values():
            dpid = datapath.id
            parser = datapath.ofproto_parser
            
            # Guard: ensure Snort VNF port was discovered for this switch
            snort_port = self.snort_ports.get(dpid)
            if snort_port is None:
                self.logger.error("[SFC] No Snort VNF port found for dpid=%s. Cannot quarantine.", dpid)
                continue
            
            # Service Function Chaining (SFC): Redirect matching traffic to the Snort VNF
            match = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_src=attacker_ip)
            actions = [parser.OFPActionOutput(snort_port)]
            self.add_flow(datapath, priority=200, match=match, actions=actions)
            
            self.logger.info("[SFC] Traffic from %s tunneled to Snort VNF (dpid=%s, port=%d).",
                             attacker_ip, dpid, snort_port)
        
        # Update DLT Status
        self.dlt_manager.update_threat_status(attacker_ip, ThreatStatus.QUARANTINED)

    def _handle_quarantined_threat(self, attacker_ip):
        """
        Workflow Step 3 (Victim): Catches 'Quarantined' -> Deletes local DROP rule to resume operations.
        """
        if attacker_ip in self.dropped_ips:
            self.logger.info("[STAGE 4: RELEASE] Attacker %s quarantined at source. Removing local DROP rule.", attacker_ip)
            for datapath in self.datapaths.values():
                ofproto = datapath.ofproto
                parser = datapath.ofproto_parser
                
                # Command OFPFC_DELETE removes the flow
                match = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_src=attacker_ip)
                mod = parser.OFPFlowMod(
                    datapath=datapath,
                    command=ofproto.OFPFC_DELETE,
                    out_port=ofproto.OFPP_ANY,
                    out_group=ofproto.OFPG_ANY,
                    priority=100,
                    match=match
                )
                datapath.send_msg(mod)
            
            # Safely remove from tracking set
            self.dropped_ips.remove(attacker_ip)
            self.logger.info("[RELEASE] Local network operations restored.")
