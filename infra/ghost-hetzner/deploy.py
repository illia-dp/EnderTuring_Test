"""Small stdlib-only Hetzner provisioner; secrets stay out of files and argv."""

import argparse
import getpass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parent
API = "https://api.hetzner.cloud/v1"


def cloud_config(domain, auth_key):
    files = [
        {"path": f"/opt/ghost/{name}", "permissions": "0600", "content": (ROOT / name).read_text()}
        for name in ("compose.yaml", "Caddyfile", "bootstrap.sh")
    ]
    files.extend([
        {"path": "/opt/ghost/public.env", "permissions": "0600", "content": f"BLOG_DOMAIN={domain}\n"},
        {"path": "/run/tailscale-auth.key", "permissions": "0600", "content": auth_key},
    ])
    # JSON is valid YAML and avoids interpolation/quoting secrets in shell scripts.
    return "#cloud-config\n" + json.dumps({
        "ssh_pwauth": False,
        "disable_root": True,
        "package_update": True,
        "packages": ["ca-certificates", "curl", "python3", "openssl"],
        "write_files": files,
        "runcmd": [["bash", "/opt/ghost/bootstrap.sh"]],
    })


class Hetzner:
    def __init__(self, token):
        self.token = token

    def request(self, method, path, payload=None):
        request = urllib.request.Request(
            API + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            # Do not echo API responses: creation responses can contain credentials.
            raise RuntimeError(f"Hetzner {method} {path}: HTTP {error.code}") from None
        except (urllib.error.URLError, TimeoutError):
            raise RuntimeError("Hetzner request failed; inspect the Cloud Console before retrying (the request may have succeeded).") from None

    def wait_action(self, action):
        for _ in range(120):
            current = self.request("GET", f"/actions/{action['id']}")["action"]
            if current["status"] == "success":
                return
            if current["status"] == "error":
                raise RuntimeError("Hetzner provisioning action failed; inspect the Cloud Console.")
            time.sleep(5)
        raise RuntimeError("Hetzner action timed out; the server was not deleted.")


def secret(name, prompt):
    value = os.environ.pop(name, "")
    if not value:
        if not sys.stdin.isatty():
            raise ValueError(f"Provide {name} through the environment or run in an interactive terminal")
        value = getpass.getpass(prompt)
    if not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


def wait_for_bootstrap(name):
    print("Waiting for Tailscale and cloud-init (up to 20 minutes)…", flush=True)
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        result = subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            peers = json.loads(result.stdout).get("Peer", {}) or {}
            matches = [peer for peer in peers.values() if peer.get("HostName") == name and peer.get("Online")]
            if len(matches) > 1:
                raise RuntimeError("Multiple Tailscale devices match the server name; remove the stale device and connect manually.")
            if matches:
                address = matches[0]["TailscaleIPs"][0]
                subprocess.run([
                    "tailscale", "ssh", f"root@{address}",
                    "cloud-init status --wait >/dev/null && test -f /opt/ghost/ready",
                ], check=True, timeout=600)
                admin = matches[0]["DNSName"].rstrip(".")
                print(f"Ready. Admin: https://{admin}/ghost/\nSSH: tailscale ssh root@{address}")
                return
        time.sleep(5)
    raise RuntimeError("Tailscale did not become reachable; inspect the server console/cloud-init logs. Resources were retained.")


def main():
    parser = argparse.ArgumentParser(description="Deploy Ghost to a new Hetzner VPS with private Tailscale administration.")
    parser.add_argument("--domain", required=True, help="Public blog DNS name")
    parser.add_argument("--name", default="ghost-blog", help="Unique server/Tailscale hostname")
    parser.add_argument("--server-type", default="cx23")
    parser.add_argument("--location", default="nbg1")
    args = parser.parse_args()
    args.domain = args.domain.lower()
    if len(args.domain) > 253 or "." not in args.domain or not all(
        re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
        for label in args.domain.split(".")
    ):
        parser.error("--domain must be a DNS hostname, without scheme, path or port")
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", args.name):
        parser.error("--name must be a lowercase hostname (1–63 characters)")
    if not shutil.which("tailscale"):
        parser.error("Install the Tailscale CLI and connect to your tailnet first")
    status = subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=15)
    if status.returncode or json.loads(status.stdout).get("BackendState") != "Running":
        parser.error("Connect this computer to Tailscale first")
    peers = json.loads(status.stdout).get("Peer", {}) or {}
    if any(peer.get("HostName") == args.name for peer in peers.values()):
        parser.error("A Tailscale device already uses this name; choose another --name or remove the stale device")

    client = Hetzner(secret("HCLOUD_TOKEN", "Hetzner Cloud API token (read/write): "))
    query = urllib.parse.urlencode({"name": args.name})
    if client.request("GET", f"/servers?{query}")["servers"]:
        raise RuntimeError("Server name already exists; no changes made. Use the existing server or choose a new name.")
    firewall_name = args.name + "-web"
    if client.request("GET", "/firewalls?" + urllib.parse.urlencode({"name": firewall_name}))["firewalls"]:
        raise RuntimeError(f"Firewall {firewall_name} already exists; inspect/remove it in the Cloud Console before retrying.")
    auth_key = secret("TS_AUTHKEY", "Tailscale auth key (single-use, pre-approved): ")
    user_data = cloud_config(args.domain, auth_key)
    firewall = client.request("POST", "/firewalls", {
        "name": firewall_name,
        "rules": [
            {"direction": "in", "protocol": "tcp", "port": port, "source_ips": ["0.0.0.0/0", "::/0"]}
            for port in ("80", "443")
        ],
    })["firewall"]
    print(f"Firewall created: {firewall['id']}. Creating VPS…", flush=True)
    # Attach the firewall at creation, before the server can accept connections.
    created = client.request("POST", "/servers", {
        "name": args.name, "server_type": args.server_type, "location": args.location,
        "image": "ubuntu-24.04", "user_data": user_data,
        "firewalls": [{"firewall": firewall["id"]}],
        "public_net": {"enable_ipv4": True, "enable_ipv6": False},
    })
    server = created["server"]
    ip = server["public_net"]["ipv4"]["ip"]
    print(f"Server ID: {server['id']}\nSet DNS A: {args.domain} → {ip} (remove stale AAAA records).", flush=True)
    client.wait_action(created["action"])
    wait_for_bootstrap(args.name)
    print(f"Blog: https://{args.domain} (TLS becomes available after DNS propagation).")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(f"Deployment failed: {error}", file=sys.stderr)
        sys.exit(1)
    except (KeyboardInterrupt, EOFError):
        print("Deployment interrupted. Check the Cloud Console for resources already created.", file=sys.stderr)
        sys.exit(1)
