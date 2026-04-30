# Copyright (c) 2026 Arista Networks, Inc.
# Use of this source code is governed by the Apache License 2.0
# that can be found in the COPYING file.

from cloudvision.cvlib import ActionFailed

def string_to_list(string_to_convert):
    """ Returns the input string as a list object """
    numbers = []
    segments = [segment.strip() for segment in string_to_convert.split(",")]
    for segment in segments:
        if "-" in segment:
            for i in range(int(segment.split("-")[0]), int(segment.split("-")[1]) + 1):
                numbers.append(i)
        else:
            numbers.append(int(segment))
    return numbers


switch = ctx.getDevice()
vlan_ids = ctx.action.args['VLAN IDs']

ctx.info(f"Supplied VLANs: {vlan_ids}")
vlan_ids = string_to_list(vlan_ids)

cmds = [
        "enable",
        "show ip virtual-router"
    ]
cmdResponses = []

cmdResponses: list[dict] = ctx.runDeviceCmds(cmds)

if cmdResponses[1]["response"]["virtualMac"] == "00:00:00:00:00:00":
    raise ActionFailed ("No virtual MAC address configured")

else:
    virtual_mac_address = cmdResponses[1]["response"]["virtualMac"]
    for vlan_id in vlan_ids:
        ctx.info(f"Getting interface info for Vlan{vlan_id}")
        try:
            show_ip_interface_output = ctx.runDeviceCmds([f"show ip interface vlan {vlan_id}"])
        except:
            ctx.error(f"Skipping Vlan{vlan_id} as Interface Vlan{vlan_id} is not present on the device")
            continue

        try:
            interface_info = show_ip_interface_output[0]["response"]["interfaces"][f"Vlan{vlan_id}"]
        except KeyError:
            ctx.error(f"Couldn't retrieve IP interface details for Vlan{vlan_id}")
            continue

        try:
            svi_virtual_ip_address = interface_info["interfaceAddress"]["virtualIp"]["address"]
        except KeyError:
            ctx.error(f"Vlan{vlan_id} does not have a Virtual IP address assigned to it")

        if svi_virtual_ip_address == "0.0.0.0":
            continue
        vrf_name = interface_info["vrf"]
        if vrf_name == "default":
            garp_command = f"bash timeout 5 sudo ethxmit " \
                f"--ip-src={svi_virtual_ip_address} --ip-dst={svi_virtual_ip_address} -S {virtual_mac_address} --arp=reply vlan{vlan_id}"

        else:
            garp_command = f"bash timeout 5 sudo ip netns exec ns-{vrf_name} ethxmit " \
                f"--ip-src={svi_virtual_ip_address} --ip-dst={svi_virtual_ip_address} -S {virtual_mac_address} --arp=reply vlan{vlan_id}"

        ctx.info(f"Sending out GARP on Vlan{vlan_id}")
        garp_output = ctx.runDeviceCmds([garp_command])

    ctx.info("Executed GARP on all SVIs")
