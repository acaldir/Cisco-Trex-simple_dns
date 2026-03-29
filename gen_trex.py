#!/usr/bin/env python3

import ipaddress
import re

DUMMY_IP            = "255.255.255.255"
DUMMY_GW            = "255.255.255.1"
CFG_OUTPUT          = "/etc/trex_cfg.yaml"
ICMP_PATH           = "/v3.08/emu/simple_icmp.py"
IPV4_PATH           = "/v3.08/emu/simple_ipv4.py"
IGMP_PATH           = "/v3.08/emu/simple_igmp.py"
DOT1X_PATH          = "/v3.08/emu/simple_dot1x.py"
DNS_PATH            = "/v3.08/emu/simple_dns.py"
DHCPSRVR_RELAY_PATH = "/v3.08/emu/dhcpsrv_relay.py"


def mac_for_port(idx):
    return f"{idx * 0x10:02x}:00:00:70:00:03"

def ip_plus_one(ip_str):
    return str(ipaddress.IPv4Address(ip_str) + 1)

def validate_ip(prompt):
    while True:
        value = input(prompt).strip()
        try:
            ipaddress.IPv4Address(value)
            return value
        except ipaddress.AddressValueError:
            print("  Hata: Gecerli bir IPv4 adresi girin (ornek: 192.168.1.1)")

# -----------------------------------------------------------------------
#  1) /etc/trex_cfg.yaml
# -----------------------------------------------------------------------
def generate_trex_cfg(port_info, total_ports, need_dummy):
    ifaces = [f"eth{i}" for i in range(len(port_info))]
    if need_dummy:
        ifaces.append("dummy")

    iface_str = ", ".join(f'"{x}"' for x in ifaces)

    lines = []
    lines.append(f"- port_limit    : {total_ports}")
    lines.append(f"  version       : 2")
    lines.append(f"  low_end       : true")
    lines.append(f"  interfaces    : [{iface_str}]")
    lines.append(f"  port_info     :")

    for p in port_info:
        lines.append(f"      - ip           : {p['ip']}")
        lines.append(f"        default_gw   : {p['gw']}")

    if need_dummy:
        lines.append(f"      - ip           : {DUMMY_IP}  # Dummy interface (even port requirement)")
        lines.append(f"        default_gw   : {DUMMY_GW}")

    yaml_content = "\n".join(lines) + "\n"

    try:
        with open(CFG_OUTPUT, "w") as f:
            f.write(yaml_content)
        print(f"  [OK] Config yazildi: {CFG_OUTPUT}")
    except PermissionError:
        print(f"  [UYARI] {CFG_OUTPUT} yazma izni yok. Ekrana yaziliyor:")

    print("\n" + yaml_content)

# -----------------------------------------------------------------------
#  Ortak blok üretici: mac / ipv4 / dg  if/elif/else bloğu
#  loop_var: "i" → simple_icmp, simple_dns
#            "j" → simple_ipv4, simple_igmp, simple_dot1x
# -----------------------------------------------------------------------
def build_port_block(port_info, loop_var="i"):
    n = len(port_info)

    if n == 1:
        mac  = mac_for_port(0)
        ipv4 = ip_plus_one(port_info[0]['ip'])
        dg   = port_info[0]['gw']
        return "\n".join([
            f"            mac  = Mac('{mac}')",
            f"            ipv4 = Ipv4('{ipv4}')",
            f"            dg   = Ipv4('{dg}')",
        ])

    lines = []
    for idx, p in enumerate(port_info):
        mac  = mac_for_port(idx)
        ipv4 = ip_plus_one(p['ip'])
        dg   = p['gw']

        if idx == 0:           keyword = "if"
        elif idx == n - 1:     keyword = "else"
        else:                  keyword = "elif"

        if keyword == "else":
            lines.append(f"            else:")
        else:
            lines.append(f"            {keyword} {loop_var} == {idx}:")

        lines.append(f"                mac  = Mac('{mac}')")
        lines.append(f"                ipv4 = Ipv4('{ipv4}')")
        lines.append(f"                dg   = Ipv4('{dg}')")

    return "\n".join(lines)


def _patch_emu_ns_block(content, new_block, filename):
    """
    ns = EMUNamespaceObj(...) satırından sonra,
    '# create a different client each time' yorumuna kadar
    olan bloğu new_block ile değiştirir.
    """
    pattern = re.compile(
        r"(ns = EMUNamespaceObj\(ns_key = ns_key, def_c_plugs = self\.def_c_plugs\)\n)"
        r".*?"
        r"(\n\s+# create a different client each time)",
        re.DOTALL
    )
    replacement = r"\g<1>\n" + new_block + r"\n\g<2>"
    new_content, count = re.subn(pattern, replacement, content)
    if count == 0:
        print(f"  [HATA] {filename} icinde degistirilecek blok bulunamadi.")
        return None
    return new_content

# -----------------------------------------------------------------------
#  2) write_simple_icmp  (loop var: i)
# -----------------------------------------------------------------------
def write_simple_icmp(port_info, path=ICMP_PATH):
    new_block = build_port_block(port_info, loop_var="i")
    try:
        with open(path, "r") as f:
            content = f.read()
    except FileNotFoundError:
        print(f"  [HATA] {path} bulunamadi.")
        return

    new_content = _patch_emu_ns_block(content, new_block, "simple_icmp.py")
    if new_content is None:
        return

    try:
        with open(path, "w") as f:
            f.write(new_content)
        print(f"  [OK] simple_icmp.py guncellendi: {path}")
    except PermissionError:
        print(f"  [UYARI] {path} yazma izni yok.")
        return

    print("\n  Uretilen port blogu (icmp):")
    print("  " + "-" * 44)
    for line in new_block.splitlines():
        print("  " + line)
    print("  " + "-" * 44)

# -----------------------------------------------------------------------
#  3) write_simple_ipv4  (loop var: j)
# -----------------------------------------------------------------------
def write_simple_ipv4(port_info, path=IPV4_PATH):
    new_block = build_port_block(port_info, loop_var="j")
    try:
        with open(path, "r") as f:
            content = f.read()
    except FileNotFoundError:
        print(f"  [HATA] {path} bulunamadi.")
        return

    new_content = _patch_emu_ns_block(content, new_block, "simple_ipv4.py")
    if new_content is None:
        return

    try:
        with open(path, "w") as f:
            f.write(new_content)
        print(f"  [OK] simple_ipv4.py guncellendi: {path}")
    except PermissionError:
        print(f"  [UYARI] {path} yazma izni yok.")
        return

    print("\n  Uretilen port blogu (ipv4):")
    print("  " + "-" * 44)
    for line in new_block.splitlines():
        print("  " + line)
    print("  " + "-" * 44)

# -----------------------------------------------------------------------
#  4) write_simple_igmp  (loop var: j + self.mac patch)
# -----------------------------------------------------------------------
def write_simple_igmp(port_info, path=IGMP_PATH):
    new_block = build_port_block(port_info, loop_var="j")
    try:
        with open(path, "r") as f:
            content = f.read()
    except FileNotFoundError:
        print(f"  [HATA] {path} bulunamadi.")
        return

    # Patch 1: __init__ icindeki self.mac
    eth0_mac = mac_for_port(0)
    content = re.sub(
        r"self\.mac\s*=\s*Mac\('[^']*'\)",
        f"self.mac = Mac('{eth0_mac}')",
        content
    )

    # Patch 2: ns blogu
    new_content = _patch_emu_ns_block(content, new_block, "simple_igmp.py")
    if new_content is None:
        return

    try:
        with open(path, "w") as f:
            f.write(new_content)
        print(f"  [OK] simple_igmp.py guncellendi: {path}")
    except PermissionError:
        print(f"  [UYARI] {path} yazma izni yok.")
        return

    print("\n  Uretilen port blogu (igmp):")
    print("  " + "-" * 44)
    for line in new_block.splitlines():
        print("  " + line)
    print("  " + "-" * 44)

# -----------------------------------------------------------------------
#  5) write_simple_dot1x  (loop var: j)
# -----------------------------------------------------------------------
def write_simple_dot1x(port_info, path=DOT1X_PATH):
    new_block = build_port_block(port_info, loop_var="j")
    try:
        with open(path, "r") as f:
            content = f.read()
    except FileNotFoundError:
        print(f"  [HATA] {path} bulunamadi.")
        return

    new_content = _patch_emu_ns_block(content, new_block, "simple_dot1x.py")
    if new_content is None:
        return

    try:
        with open(path, "w") as f:
            f.write(new_content)
        print(f"  [OK] simple_dot1x.py guncellendi: {path}")
    except PermissionError:
        print(f"  [UYARI] {path} yazma izni yok.")
        return

    print("\n  Uretilen port blogu (dot1x):")
    print("  " + "-" * 44)
    for line in new_block.splitlines():
        print("  " + line)
    print("  " + "-" * 44)

# -----------------------------------------------------------------------
#  6) write_simple_dns  (loop var: i)
#
#  simple_dns.py'de iki ayrı patch:
#
#  Patch 1 – get_init_json icindeki dns_server_ip
#    "dns_server_ip": "<eski>"  →  eth0_ip + 1
#
#  Patch 2 – create_profile icindeki mac/ipv4/ipv6/dns_ip/dg blogu
#    ns = EMUNamespaceObj(...) sonrasından
#    # create a different client each time yorumuna kadar
#
#    port=1 → sabit satırlar
#    port>1 → if/elif/else (mac/ipv4/dg)
#             + ipv6 ve dns_ip ortak satırları bloğun sonuna eklenir
# -----------------------------------------------------------------------
def write_simple_dns(port_info, path=DNS_PATH):
    n = len(port_info)

    try:
        with open(path, "r") as f:
            content = f.read()
    except FileNotFoundError:
        print(f"  [HATA] {path} bulunamadi.")
        return

    # ------------------------------------------------------------------
    # Patch 1: get_init_json icindeki dns_server_ip → eth0_ip + 1
    # ------------------------------------------------------------------
    eth0_dns_ip = ip_plus_one(port_info[0]['ip'])
    # Tek tırnak stili: 'x.x.x.x'
    content = re.sub(
        r"(\"dns_server_ip\"\s*:\s*)'[^']*'",
        f"\\1'{eth0_dns_ip}'",
        content
    )
    # Çift tırnak stili: "x.x.x.x"
    content = re.sub(
        r'("dns_server_ip"\s*:\s*)"[^"]*"',
        f'\\1"{eth0_dns_ip}"',
        content
    )

    # ------------------------------------------------------------------
    # Patch 2: create_profile icindeki mac/ipv4/ipv6/dns_ip/dg blogu
    # ------------------------------------------------------------------
    if n == 1:
        mac_val  = mac_for_port(0)
        ipv4_val = ip_plus_one(port_info[0]['ip'])
        dg_val   = port_info[0]['gw']
        ipv6_val = "2001:DB8:1::3"
        new_block = "\n".join([
            f"            mac  = Mac('{mac_val}')",
            f"            ipv4 = Ipv4('{ipv4_val}')",
            f"            ipv6 = Ipv6(\"{ipv6_val}\")",
            f"            dns_ip = ipv6.S() if dns_ipv6 else ipv4.S()",
            f"            dg   = Ipv4('{dg_val}')",
        ])
    else:
        if_lines = []
        for idx, p in enumerate(port_info):
            mac_val  = mac_for_port(idx)
            ipv4_val = ip_plus_one(p['ip'])
            dg_val   = p['gw']
            ipv6_val = f"{2001 + idx}:DB8:1::3"   # 2001, 2002, 2003 ...

            if idx == 0:           keyword = "if"
            elif idx == n - 1:     keyword = "else"
            else:                  keyword = "elif"

            if keyword == "else":
                if_lines.append(f"            else:")
            else:
                if_lines.append(f"            {keyword} i == {idx}:")

            if_lines.append(f"                mac  = Mac('{mac_val}')")
            if_lines.append(f"                ipv4 = Ipv4('{ipv4_val}')")
            if_lines.append(f"                ipv6 = Ipv6(\"{ipv6_val}\")")
            if_lines.append(f"                dg   = Ipv4('{dg_val}')")

        # dns_ip bloğun dışında ortak satır (ipv6 artık if bloğu içinde)
        if_lines.append(f"            dns_ip = ipv6.S() if dns_ipv6 else ipv4.S()")
        new_block = "\n".join(if_lines)

    new_content = _patch_emu_ns_block(content, new_block, "simple_dns.py")
    if new_content is None:
        return

    try:
        with open(path, "w") as f:
            f.write(new_content)
        print(f"  [OK] simple_dns.py guncellendi: {path}")
    except PermissionError:
        print(f"  [UYARI] {path} yazma izni yok.")
        return

    print("\n  Uretilen port blogu (dns):")
    print("  " + "-" * 44)
    for line in new_block.splitlines():
        print("  " + line)
    print(f"  dns_server_ip (eth0+1): {eth0_dns_ip}")
    print("  " + "-" * 44)

# -----------------------------------------------------------------------
#  dhcpsrv_relay yardımcıları
# -----------------------------------------------------------------------
def pool_for_port(idx):
    third_octet = 2 + idx
    return {
        "min": f"1.1.{third_octet}.3",
        "max": f"1.1.{third_octet}.255",
        "prefix": 24,
    }


def _build_dhcpsrv_config_method(port_info):
    pool_lines = []
    for idx in range(len(port_info)):
        pool = pool_for_port(idx)
        pool_lines.append(
            f'                {{"min": "{pool["min"]}", '
            f'"max": "{pool["max"]}", '
            f'"prefix": {pool["prefix"]}}}'
        )
    pools_str = ",\n".join(pool_lines)

    return (
        "    def get_dhcpsrv_config(self):\n"
        "        return {\n"
        '            "default_lease": 120,\n'
        '            "pools": [\n'
        f"{pools_str},\n"
        "            ],\n"
        '            "options": {\n'
        '                "offer": [\n'
        '                    {"type": 6, "data": [8, 8, 8, 8]},\n'
        '                    {"type": 15, "data": [99, 105, 115, 99, 111, 46, 99, 111, 109]}\n'
        "                ],\n"
        '                "ack": [\n'
        '                    {"type": 6, "data": [8, 8, 8, 8]},\n'
        '                    {"type": 15, "data": [99, 105, 115, 99, 111, 46, 99, 111, 109]}\n'
        "                ]\n"
        "            }\n"
        "        }"
    )


def _build_get_profile_method(port_info):
    n = len(port_info)
    port_choices = "/".join(str(i) for i in range(n))
    port_help    = f"Server port ({port_choices})"

    lines = []
    lines.append("    def get_profile(self, tuneables):")
    lines.append("")
    lines.append("        parser = argparse.ArgumentParser(")
    lines.append("            description='DHCPv4 Server + Clients (Selectable Port)',")
    lines.append("            formatter_class=argparse.ArgumentDefaultsHelpFormatter")
    lines.append("        )")
    lines.append("")
    lines.append("        parser.add_argument('--clients', type=int, default=3)")
    lines.append(f"        parser.add_argument('--port', type=int, default=0, help='{port_help}')")
    lines.append("")

    for idx, p in enumerate(port_info):
        mac    = mac_for_port(idx)
        srv_ip = ip_plus_one(p['ip'])
        srv_dg = p['gw']
        lines.append(f"        parser.add_argument('--mac_{idx}', type = str, default = '{mac}', help='Starting MAC address eth{idx}')")
        lines.append(f"        parser.add_argument('--srv_ip_{idx}', type = str, default = '{srv_ip}', help='Server IPv4 eth{idx}')")
        lines.append(f"        parser.add_argument('--srv_dg_ip_{idx}', type = str, default = '{srv_dg}', help='Server Default Gateway eth{idx}')")
        lines.append("")

    lines.append("        args = parser.parse_args(tuneables)")
    lines.append("")

    for idx in range(n):
        if idx == 0:           keyword = "if"
        elif idx == n - 1:     keyword = "else"
        else:                  keyword = "elif"

        if keyword == "else":
            lines.append("        else:")
        else:
            lines.append(f"        {keyword} args.port == {idx}:")

        lines.append(f"            mac = args.mac_{idx}")
        lines.append(f"            ip  = args.srv_ip_{idx}")
        lines.append(f"            dg  = args.srv_dg_ip_{idx}")
        lines.append("")

    if n == 1:
        lines.append("        else:")
        lines.append("            raise Exception('Invalid port. Use 0')")
        lines.append("")

    lines.append("        return self.create_profile(args.clients, mac, ip, dg, args.port)")

    return "\n".join(lines)

# -----------------------------------------------------------------------
#  7) write_dhcpsrv_relay
# -----------------------------------------------------------------------
def write_dhcpsrv_relay(port_info, path=DHCPSRVR_RELAY_PATH):
    try:
        with open(path, "r") as f:
            fc = f.read()
    except FileNotFoundError:
        print(f"  [HATA] {path} bulunamadi.")
        return

    n = len(port_info)

    # Patch 1: get_dhcpsrv_config
    new_dhcpsrv = _build_dhcpsrv_config_method(port_info)
    p1 = re.compile(
        r"    def get_dhcpsrv_config\(self\):.*?(?=\n    def )",
        re.DOTALL
    )
    fc, c1 = p1.subn(new_dhcpsrv + "\n", fc)
    if c1 == 0:
        print("  [UYARI] get_dhcpsrv_config metodu bulunamadi, pools guncellenmedi.")

    # Patch 2: get_profile
    new_get_profile = _build_get_profile_method(port_info)
    p2 = re.compile(
        r"    def get_profile\(self, tuneables\):.*?(?=\n\ndef register\(\))",
        re.DOTALL
    )
    fc, c2 = p2.subn(new_get_profile + "\n", fc)
    if c2 == 0:
        print("  [HATA] get_profile metodu bulunamadi.")
        return

    try:
        with open(path, "w") as f:
            f.write(fc)
        print(f"  [OK] dhcpsrv_relay.py guncellendi: {path}")
    except PermissionError:
        print(f"  [UYARI] {path} yazma izni yok.")
        return

    print(f"\n  {n} port icin guncellendi:")
    for idx, p in enumerate(port_info):
        pool = pool_for_port(idx)
        print(f"  eth{idx}: mac={mac_for_port(idx)}  "
              f"srv_ip={ip_plus_one(p['ip'])}  dg={p['gw']}  "
              f"pool={pool['min']}-{pool['max']}")

# -----------------------------------------------------------------------
#  MAIN
# -----------------------------------------------------------------------
def main():
    print("-------------------------------------")
    print("  TRex Config Generator")
    print("-------------------------------------\n")

    while True:
        try:
            port_limit = int(input("Port limit girin [1-8]: ").strip())
            if 1 <= port_limit <= 8:
                break
            print("  Hata: 1 ile 8 arasinda bir sayi girin.")
        except ValueError:
            print("  Hata: Gecerli bir sayi girin.")

    need_dummy  = port_limit % 2 != 0
    total_ports = port_limit + 1 if need_dummy else port_limit

    if need_dummy:
        print(f"\n  [INFO] Tek sayi girildi --> dummy interface eklenecek.")
        print(f"  [INFO] Toplam interface: {total_ports} (even)\n")

    port_info = []
    for i in range(port_limit):
        iface = f"eth{i}"
        print(f"--- {iface} ---")
        ip = validate_ip(f"  {iface} IP adresi  : ")
        gw = validate_ip(f"  {iface} Default GW : ")
        port_info.append({"iface": iface, "ip": ip, "gw": gw})
        print()

    print("-------------------------------------\n")

    generate_trex_cfg(port_info, total_ports, need_dummy)
    write_simple_icmp(port_info)
    write_simple_ipv4(port_info)
    write_simple_igmp(port_info)
    write_simple_dot1x(port_info)
    write_simple_dns(port_info)
    write_dhcpsrv_relay(port_info)

    print("\n-------------------------------------")
    print("  Calistirmak icin:")
    print("  ./t-rex-64 -i -c 1 --software --emu")
    print("  emu_load_profile -f emu/dhcpsrv_relay.py -t --port 1 --srv_ip_1 5.1.1.100 --srv_dg_ip_1 5.1.1.1 --clients 3")
    print("-------------------------------------\n")


if __name__ == "__main__":
    main()