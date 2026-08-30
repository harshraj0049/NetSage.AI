import re
from ipaddress import ip_address


# ============================================================
# Utility
# ============================================================

def clean_lines(text):
    """Return non-empty, stripped lines from CLI output."""
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]


# ============================================================
# 1. Parse PC ipconfig
# ============================================================

def parse_ipconfig(text):
    """
    Parse Cisco Packet Tracer PC ipconfig output.

    Extracts:
        IPv4 address
        subnet mask
        default gateway
    """

    result = {
        "pc_ip": None,
        "subnet_mask": None,
        "gateway": None
    }

    ipv4_match = re.search(
        r"IPv4 Address.*?:\s*([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)",
        text,
        re.IGNORECASE
    )

    subnet_match = re.search(
        r"Subnet Mask.*?:\s*([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)",
        text,
        re.IGNORECASE
    )

    gateway_match = re.search(
        r"Default Gateway.*?:\s*([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)",
        text,
        re.IGNORECASE
    )

    if ipv4_match:
        result["pc_ip"] = ipv4_match.group(1)

    if subnet_match:
        result["subnet_mask"] = subnet_match.group(1)

    if gateway_match:
        result["gateway"] = gateway_match.group(1)

    return result


# ============================================================
# 2. Parse Router show ip interface brief
# ============================================================

def parse_interface_brief(text):
    """
    Parse Router show ip interface brief evidence.

    Supports both:
    
    Standard Cisco format:
    Interface IP-Address OK? Method Status Protocol

    Simplified evidence format:
    Interface IP-Address Status Protocol
    """

    interfaces = []

    for line in clean_lines(text):

        if line.lower().startswith("interface"):
            continue

        parts = line.split()

        # We need at least:
        # interface, IP, status, protocol
        if len(parts) < 4:
            continue

        interface_name = parts[0]
        ip = parts[1]

        # Ignore non-network entries
        if not (
            interface_name.lower().startswith("gigabitethernet")
            or interface_name.lower().startswith("fastethernet")
            or interface_name.lower().startswith("serial")
        ):
            continue

        # ----------------------------------------------------
        # Simplified format:
        #
        # GigabitEthernet0/0 192.168.10.1 up up
        # ----------------------------------------------------

        if len(parts) == 4:

            status = parts[2]
            protocol = parts[3]

        # ----------------------------------------------------
        # Standard Cisco format:
        #
        # GigabitEthernet0/0 192.168.10.1 YES manual up up
        # ----------------------------------------------------

        else:

            status = parts[-2]
            protocol = parts[-1]

        interfaces.append({
            "name": interface_name,
            "ip": None if ip.lower() == "unassigned" else ip,
            "status": status.lower(),
            "protocol": protocol.lower()
        })

    return interfaces


# ============================================================
# 3. Parse Router show ip route
# ============================================================

def parse_routing_table(text):
    """
    Parse connected network routes from:

        show ip route

    Only C (connected) network routes are returned.
    Local /32 routes are ignored.
    """

    networks = []

    pattern = re.compile(
        r"^C\s+"
        r"(\d+\.\d+\.\d+\.\d+/\d+)"
        r"\s+is directly connected",
        re.IGNORECASE
    )

    for line in clean_lines(text):

        match = pattern.match(line)

        if match:
            networks.append(match.group(1))

    return networks


# ============================================================
# 4. Parse show vlan brief
# ============================================================

def parse_vlan_brief(text):
    """
    Parse:

        show vlan brief

    Returns:

        {
            "Fa0/1": 10,
            "Fa0/2": 20
        }
    """

    port_vlans = {}

    current_vlan = None

    vlan_pattern = re.compile(
        r"^(\d+)\s+\S.*?\s+active\s*(.*)$",
        re.IGNORECASE
    )

    for line in clean_lines(text):

        match = vlan_pattern.match(line)

        if match:
            current_vlan = int(match.group(1))

            ports = match.group(2)

            for port in re.findall(
                r"(Fa\d+/\d+|Gi\d+/\d+)",
                ports,
                re.IGNORECASE
            ):
                port_vlans[port] = current_vlan

            continue

        # Handle continuation lines containing ports
        if current_vlan is not None:

            for port in re.findall(
                r"(Fa\d+/\d+|Gi\d+/\d+)",
                line,
                re.IGNORECASE
            ):
                port_vlans[port] = current_vlan

    return port_vlans


# ============================================================
# 5. Parse show mac address-table
# ============================================================

def parse_mac_address_table(text):
    """
    Parse:

        show mac address-table

    Returns learned MAC addresses with VLAN and port.
    """

    entries = []

    pattern = re.compile(
        r"^\s*(\d+)\s+"
        r"([0-9a-fA-F.]+)\s+"
        r"(\S+)\s+"
        r"(\S+)$"
    )

    for line in clean_lines(text):

        match = pattern.match(line)

        if not match:
            continue

        entries.append({
            "vlan": int(match.group(1)),
            "mac": match.group(2),
            "type": match.group(3),
            "port": match.group(4)
        })

    return entries


# ============================================================
# 6. Parse show access-lists
# ============================================================

def parse_access_lists(text):
    """
    Parse extended ACL entries such as:

        10 deny icmp host 192.168.10.10 host 192.168.20.10
        20 permit ip any any

    Returns structured ACL rules.
    """

    rules = []

    pattern = re.compile(
        r"^\s*(\d+)\s+"
        r"(permit|deny)\s+"
        r"(ip|icmp|tcp|udp)\s+"
        r"(.+?)"
        r"(?:\s+\((\d+)\s+match\(es\)\))?$",
        re.IGNORECASE
    )

    for line in clean_lines(text):

        # Skip ACL header
        if line.lower().startswith("extended ip access list"):
            continue

        match = pattern.match(line)

        if not match:
            continue

        sequence = int(match.group(1))
        action = match.group(2).lower()
        protocol = match.group(3).lower()
        address_part = match.group(4).strip()

        matches = (
            int(match.group(5))
            if match.group(5)
            else 0
        )

        # ----------------------------------------------------
        # Extract addresses
        # ----------------------------------------------------

        hosts = re.findall(
            r"\bhost\s+"
            r"(\d+\.\d+\.\d+\.\d+)",
            address_part,
            re.IGNORECASE
        )

        if len(hosts) >= 2:
            source = hosts[0]
            destination = hosts[1]

        elif len(hosts) == 1:
            source = hosts[0]

            # If only one host is present, determine
            # destination from the remaining text.
            remaining = re.sub(
                r"\bhost\s+\d+\.\d+\.\d+\.\d+",
                "",
                address_part,
                flags=re.IGNORECASE
            ).strip()

            destination = (
                "any"
                if not remaining
                else remaining
            )

        else:
            # Handle simple "any any"
            tokens = address_part.split()

            if len(tokens) >= 2:
                source = tokens[0]
                destination = tokens[1]
            else:
                source = "any"
                destination = "any"

        rules.append({
            "sequence": sequence,
            "action": action,
            "protocol": protocol,
            "source": source,
            "destination": destination,
            "matches": matches
        })

    return rules


# ============================================================
# 7. Parse ping output
# ============================================================

def parse_ping(text):
    """
    Parse multiple Cisco Packet Tracer ping tests.

    Returns each ping as a separate test so that
    the checker can distinguish:

        PC0 -> Server0
        PC0 -> Gateway
    """

    lines = text.splitlines()

    tests = []
    current_destination = None
    current_block = []

    def process_block(destination, block):
        if not destination:
            return

        block_text = "\n".join(block)

        sent_match = re.search(
            r"Packets:\s*Sent\s*=\s*(\d+)",
            block_text,
            re.IGNORECASE
        )

        received_match = re.search(
            r"Received\s*=\s*(\d+)",
            block_text,
            re.IGNORECASE
        )

        if not sent_match or not received_match:
            return

        sent = int(sent_match.group(1))
        received = int(received_match.group(1))

        tests.append({
            "destination": destination,
            "success": received == sent and sent > 0,
            "sent": sent,
            "received": received
        })

    for line in lines:

        ping_match = re.search(
            r"\bping\s+(\d+\.\d+\.\d+\.\d+)",
            line,
            re.IGNORECASE
        )

        if ping_match:

            # Finish previous ping
            process_block(
                current_destination,
                current_block
            )

            # Start new ping
            current_destination = ping_match.group(1)
            current_block = [line]

        elif current_destination is not None:

            current_block.append(line)

    # Process final ping
    process_block(
        current_destination,
        current_block
    )

    return {
        "tests": tests
    }

# ============================================================
# 8. Master parser
# ============================================================

def parse_evidence(text):
    """
    Parse a combined evidence text file.

    The parser does NOT diagnose the network fault.
    It only extracts structured facts.
    """

    evidence = {}

    # --------------------------------------------------------
    # Detect and parse ipconfig
    # --------------------------------------------------------

    if "IPv4 Address" in text and "Subnet Mask" in text:
        evidence["gateway"] = parse_ipconfig(text)

    # --------------------------------------------------------
    # Interface brief
    # --------------------------------------------------------

    if "show ip interface brief" in text:
        evidence["interfaces"] = parse_interface_brief(text)

    # --------------------------------------------------------
    # Routing table
    # --------------------------------------------------------

    if "show ip route" in text:
        evidence["routing"] = {
            "routing_table": parse_routing_table(text)
        }

    # --------------------------------------------------------
    # VLAN
    # --------------------------------------------------------

    if "show vlan brief" in text:
        evidence["vlans"] = parse_vlan_brief(text)

    # --------------------------------------------------------
    # MAC table
    # --------------------------------------------------------

    if "show mac address-table" in text:
        evidence["mac_table"] = parse_mac_address_table(text)

    # --------------------------------------------------------
    # ACL
    # --------------------------------------------------------

    if "show access-lists" in text:
        evidence["acl"] = {
            "rules": parse_access_lists(text)
        }

    # --------------------------------------------------------
    # Ping
    # --------------------------------------------------------

    if "ping " in text.lower():
        evidence["connectivity"] = parse_ping(text)

    return evidence

def parse_evidence_file(file_path):
    """
    Read a raw evidence text file and convert it into
    structured evidence.
    """

    with open(file_path, "r", encoding="utf-8") as file:
        text = file.read()

    return parse_evidence(text)
# ============================================================
# Simple manual test
# ============================================================

if __name__ == "__main__":

    from pathlib import Path

    BASE_DIR = Path(__file__).resolve().parent.parent

    evidence_file = BASE_DIR / "evidence" / "V1_03.txt"

    if not evidence_file.exists():
        print(f"Evidence file not found: {evidence_file}")
        raise SystemExit(1)

    parsed = parse_evidence_file(evidence_file)

    print("\n--- Parsed Evidence From V1_03.txt ---")

    for key, value in parsed.items():
        print(f"\n{key}:")
        print(value)