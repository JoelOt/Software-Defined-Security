#!/usr/bin/env python3
"""
Data Plane: Mininet Topology Setup for Federated SDN.
Creates a single OVS switch with N hosts and a dedicated Snort VNF node.
Connects to a remote Ryu controller.
"""
import argparse
import ipaddress
import os
from dotenv import load_dotenv

load_dotenv()

from mininet.net import Mininet
from mininet.node import RemoteController, OVSKernelSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info


def create_topology(num_hosts: int, base_ip: str, controller_ip: str, domain_code: str = ''):
    """
    Role: Data Plane
    Dynamically generates the Mininet topology, assigning IPs to standard hosts
    and a distinct snort_vnf node, then connects to the Control Plane (Ryu).
    """
    info('*** Creating network\n')
    net = Mininet(controller=RemoteController, switch=OVSKernelSwitch)

    info('*** Adding controller\n')
    # Use environment variable for port, default to 6653 (DOMAIN B)
    controller_port = int(os.environ.get('RYU_LISTEN_PORT_DOMAIN_B', '6653'))
    c0 = net.addController('c0', controller=RemoteController, ip=controller_ip, port=controller_port)

    info('*** Adding switch\n')
    # Explicitly enforce OpenFlow 1.3 protocol as per architectural rules
    s_name = f's{domain_code}1' if domain_code else 's1'
    s1 = net.addSwitch(s_name, protocols='OpenFlow13')

    info('*** Adding hosts\n')
    network = ipaddress.IPv4Network(base_ip, strict=False)
    hosts_iterator = network.hosts()
    
    for i in range(1, num_hosts + 1):
        try:
            ip_obj = next(hosts_iterator)
            ip_str = f"{ip_obj}/{network.prefixlen}"
            h_name = f'h{domain_code}{i}' if domain_code else f'h{i}'
            host = net.addHost(h_name, ip=ip_str)
            net.addLink(host, s1)
        except StopIteration:
            info(f'*** Warning: Not enough IPs in subnet for {num_hosts} hosts.\n')
            break

    info('*** Adding Snort VNF node\n')
    try:
        vnf_ip_obj = next(hosts_iterator)
        vnf_ip_str = f"{vnf_ip_obj}/{network.prefixlen}"
        vnf_name = f'snort{domain_code}' if domain_code else 'snort'
        snort_vnf = net.addHost(vnf_name, ip=vnf_ip_str)
        net.addLink(snort_vnf, s1)
    except StopIteration:
        info('*** Warning: Not enough IPs to assign to snort.\n')

    info('*** Starting network\n')
    net.build()
    c0.start()
    s1.start([c0])

    info('*** Configuring L3 routing bypass (Device Routes)\n')
    for host in net.hosts:
        # Allow L2 direct bridging to any other 10.x.x.x domain without a router
        if host.defaultIntf():
            host.cmd(f'ip route add 10.0.0.0/8 dev {host.defaultIntf().name}')

    info('*** Running CLI\n')
    CLI(net)

    info('*** Stopping network\n')
    net.stop()


if __name__ == '__main__':
    setLogLevel('info')
    parser = argparse.ArgumentParser(description='Data Plane: Federated SDN Topology')
    parser.add_argument('--num-hosts', type=int, default=3, help='Number of client hosts')
    parser.add_argument('--base-ip', type=str, default='10.0.1.0/24', help='Base IP subnet (e.g., 10.0.1.0/24)')
    parser.add_argument('--controller-ip', type=str, default=os.environ.get('MININET_CONTROLLER_IP', '127.0.0.1'), help='Control Plane IP address')
    parser.add_argument('--domain-code', type=str, default='', help='Domain identifier (e.g. "a" or "b") to prevent interface name overlap when running locally')
    
    args = parser.parse_args()
    
    create_topology(args.num_hosts, args.base_ip, args.controller_ip, args.domain_code)
