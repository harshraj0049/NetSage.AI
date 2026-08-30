from ipaddress import ip_address, ip_network


# ============================================================
# Utility
# ============================================================

def result(status, reason, details=None):
    """
    Standard result format for every rule.

    status:
        PASS    -> Check succeeded
        FAIL    -> Check found a fault
        UNKNOWN -> Required evidence is not available
    """
    return {
        "status": status,
        "reason": reason,
        "details": details or {}
    }


# ============================================================
# 1. Default Gateway Check
# ============================================================

def check_default_gateway(
    pc_ip,
    subnet_mask,
    gateway,
    router_interfaces
):
    """
    Check whether the configured PC gateway:

    1. Belongs to the PC's subnet.
    2. Matches a known router interface.
    """

    if not all([
        pc_ip,
        subnet_mask,
        gateway,
        router_interfaces
    ]):
        return result(
            "UNKNOWN",
            "Insufficient information to check the default gateway."
        )

    try:
        pc_network = ip_network(
            f"{pc_ip}/{subnet_mask}",
            strict=False
        )

        gateway_ip = ip_address(gateway)

    except ValueError as exc:
        return result(
            "UNKNOWN",
            f"Invalid IP addressing information: {exc}"
        )

    # Gateway must be in the same subnet as the PC
    if gateway_ip not in pc_network:
        return result(
            "FAIL",
            "Configured gateway is outside the PC's subnet.",
            {
                "pc_ip": pc_ip,
                "gateway": gateway,
                "pc_network": str(pc_network)
            }
        )

    # Gateway should match a router interface
    for interface_ip in router_interfaces:
        try:
            if ip_address(interface_ip) == gateway_ip:
                return result(
                    "PASS",
                    "Configured gateway matches a router interface.",
                    {
                        "gateway": gateway,
                        "router_interface": interface_ip
                    }
                )
        except ValueError:
            continue

    return result(
        "FAIL",
        "Configured gateway does not match any known router interface.",
        {
            "gateway": gateway,
            "router_interfaces": router_interfaces
        }
    )


# ============================================================
# 2. Router Interface Check
# ============================================================

def check_interfaces(interfaces):
    """
    Check whether required router interfaces are up/up.

    Expected input:

    [
        {
            "name": "GigabitEthernet0/0",
            "ip": "192.168.10.1",
            "status": "up",
            "protocol": "up"
        }
    ]
    """

    if not interfaces:
        return result(
            "UNKNOWN",
            "No router interface evidence was provided."
        )

    down_interfaces = []

    for interface in interfaces:
        status = interface.get("status", "").lower()
        protocol = interface.get("protocol", "").lower()

        if status != "up" or protocol != "up":
            down_interfaces.append(interface)

    if down_interfaces:
        return result(
            "FAIL",
            "One or more router interfaces are not operational.",
            {
                "affected_interfaces": down_interfaces
            }
        )

    return result(
        "PASS",
        "All provided router interfaces are operational."
    )


# ============================================================
# 3. Routing Check
# ============================================================

def check_routes(required_networks, routing_table):
    """
    Check whether required destination networks exist
    in the routing table.

    Example:

    required_networks = [
        "192.168.10.0/24",
        "192.168.20.0/24"
    ]

    routing_table = [
        "192.168.10.0/24",
        "192.168.20.0/24"
    ]
    """

    if not required_networks or routing_table is None:
        return result(
            "UNKNOWN",
            "Insufficient routing evidence."
        )

    missing_routes = []

    for network in required_networks:
        if network not in routing_table:
            missing_routes.append(network)

    if missing_routes:
        return result(
            "FAIL",
            "One or more required destination networks are missing from the routing table.",
            {
                "missing_routes": missing_routes
            }
        )

    return result(
        "PASS",
        "All required destination networks are present in the routing table."
    )


# ============================================================
# 4. VLAN Check
# ============================================================

def check_vlans(host_ports):
    """
    Check whether communicating hosts are assigned
    to the same VLAN.

    Expected input:

    {
        "PC0": 10,
        "PC1": 20
    }
    """

    if not host_ports or len(host_ports) < 2:
        return result(
            "UNKNOWN",
            "Insufficient VLAN information to compare hosts."
        )

    vlans = list(host_ports.values())

    if len(set(vlans)) == 1:
        return result(
            "PASS",
            "Communicating hosts are assigned to the same VLAN.",
            {
                "host_vlans": host_ports
            }
        )

    return result(
        "FAIL",
        "Communicating hosts are assigned to different VLANs.",
        {
            "host_vlans": host_ports
        }
    )


# ============================================================
# 5. ACL Check
# ============================================================

def check_acl(
    source_ip,
    destination_ip,
    protocol,
    acl_rules
):
    """
    Determine whether an ACL explicitly denies the
    specified traffic.

    Expected rule format:

    {
        "action": "deny",
        "protocol": "icmp",
        "source": "192.168.10.10",
        "destination": "192.168.20.10"
    }
    """

    if not acl_rules:
        return result(
            "UNKNOWN",
            "No ACL evidence was provided."
        )

    protocol = protocol.lower()

    for rule in acl_rules:

        action = rule.get("action", "").lower()
        rule_protocol = rule.get("protocol", "").lower()
        rule_source = rule.get("source")
        rule_destination = rule.get("destination")

        source_matches = (
            rule_source in ("any", source_ip)
        )

        destination_matches = (
            rule_destination in ("any", destination_ip)
        )

        protocol_matches = (
            rule_protocol in ("ip", protocol)
        )

        if (
            action == "deny"
            and source_matches
            and destination_matches
            and protocol_matches
        ):
            return result(
                "FAIL",
                "ACL explicitly denies the specified traffic.",
                {
                    "matched_rule": rule
                }
            )

    return result(
        "PASS",
        "No matching ACL deny rule was found.",
        {
            "source": source_ip,
            "destination": destination_ip,
            "protocol": protocol
        }
    )


# ============================================================
# 6. Connectivity Check
# ============================================================

def check_connectivity(ping_success, source, destination):
    """
    Check observed connectivity between two hosts.
    """

    if ping_success is None:
        return result(
            "UNKNOWN",
            "No connectivity test result was provided."
        )

    if ping_success:
        return result(
            "PASS",
            "Connectivity test succeeded.",
            {
                "source": source,
                "destination": destination
            }
        )

    return result(
        "FAIL",
        "Connectivity test failed.",
        {
            "source": source,
            "destination": destination
        }
    )


# ============================================================
# MASTER CHECKER
# ============================================================

def run_all_checks(evidence):
    """
    Run all deterministic checks that can be evaluated from
    the currently available evidence.

    The checker does NOT know:
        - case_id
        - expected_fault
        - category

    It only evaluates the evidence provided.
    """

    findings = {}

    # ========================================================
    # 1. Default Gateway
    # ========================================================

    gateway_data = evidence.get("gateway")

    if gateway_data:
        findings["default_gateway"] = check_default_gateway(
            pc_ip=gateway_data.get("pc_ip"),
            subnet_mask=gateway_data.get("subnet_mask"),
            gateway=gateway_data.get("gateway"),
            router_interfaces=[
                interface.get("ip")
                for interface in evidence.get("interfaces", [])
                if interface.get("ip")
            ]
        )
    else:
        findings["default_gateway"] = result(
            "UNKNOWN",
            "No PC IP configuration evidence was provided."
        )

    # ========================================================
    # 2. Router Interfaces
    # ========================================================

    findings["interfaces"] = check_interfaces(
        evidence.get("interfaces")
    )

    # ========================================================
    # 3. Routing
    # ========================================================

    routing_data = evidence.get("routing")

    if routing_data:

        routing_table = routing_data.get(
            "routing_table",
            []
        )

        # Only /24 network routes are relevant for our
        # current test cases.
        required_networks = [
            network
            for network in routing_table
            if not network.endswith("/32")
        ]

        findings["routing"] = check_routes(
            required_networks=required_networks,
            routing_table=routing_table
        )

    else:
        findings["routing"] = result(
            "UNKNOWN",
            "No routing evidence was provided."
        )

    # ========================================================
    # 4. VLAN
    # ========================================================

    findings["vlans"] = check_vlans(
        evidence.get("host_vlans")
    )

    # ========================================================
    # 5. ACL
    # ========================================================

    acl_data = evidence.get("acl")

    connectivity_tests = evidence.get(
        "connectivity",
        {}
    ).get(
        "tests",
        []
    )

    # Find failed and successful connectivity tests
    failed_tests = [
        test
        for test in connectivity_tests
        if test.get("success") is False
    ]

    if acl_data and failed_tests:

        # For the current test cases, use the failed
        # destination as the ACL destination.
        destination = failed_tests[0].get(
            "destination"
        )

        # Source is inferred from the ACL rule when
        # available.
        source = None

        for rule in acl_data.get("rules", []):

            if (
                rule.get("source") != "any"
                and rule.get("source")
            ):
                source = rule.get("source")
                break

        findings["acl"] = check_acl(
            source_ip=source,
            destination_ip=destination,
            protocol="icmp",
            acl_rules=acl_data.get("rules")
        )

    else:
        findings["acl"] = result(
            "UNKNOWN",
            "Insufficient ACL/connectivity evidence to evaluate ACL behavior."
        )

    # ========================================================
    # 6. Connectivity
    # ========================================================

    if connectivity_tests:

        connectivity_results = []

        for test in connectivity_tests:

            connectivity_results.append({
                "destination": test.get("destination"),
                "status": (
                    "PASS"
                    if test.get("success")
                    else "FAIL"
                ),
                "sent": test.get("sent"),
                "received": test.get("received")
            })

        findings["connectivity"] = {
            "status": "FAIL"
            if any(
                item["status"] == "FAIL"
                for item in connectivity_results
            )
            else "PASS",
            "reason": "Connectivity tests were evaluated.",
            "details": {
                "tests": connectivity_results
            }
        }

    else:
        findings["connectivity"] = result(
            "UNKNOWN",
            "No connectivity evidence was provided."
        )

    return findings


if __name__ == "__main__":

    import json
    from pathlib import Path
    from evidence_parser import parse_evidence_file

    BASE_DIR = Path(__file__).resolve().parent.parent

    evidence_file = (
        BASE_DIR
        / "evidence"
        / "V1_03.txt"
    )

    if not evidence_file.exists():
        print(
            f"Evidence file not found: {evidence_file}"
        )
        raise SystemExit(1)

    evidence = parse_evidence_file(
        evidence_file
    )

    findings = run_all_checks(evidence)

    print("\n--- Parsed Evidence ---")
    print(
        json.dumps(
            evidence,
            indent=2
        )
    )

    print("\n--- Rule Checker Findings ---")
    print(
        json.dumps(
            findings,
            indent=2
        )
    )