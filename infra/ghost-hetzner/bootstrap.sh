#!/usr/bin/env bash
set -euo pipefail
umask 077
cd /opt/ghost
chmod 700 /opt/ghost

# Tailscale SSH handles connections on the tailnet without an OpenSSH listener.
systemctl disable --now ssh.socket ssh.service || true
systemctl mask ssh.socket ssh.service

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/noble.noarmor.gpg -o /etc/apt/keyrings/tailscale.gpg
chmod 644 /etc/apt/keyrings/*.asc /etc/apt/keyrings/tailscale.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu noble stable" > /etc/apt/sources.list.d/docker.list
echo 'deb [signed-by=/etc/apt/keyrings/tailscale.gpg] https://pkgs.tailscale.com/stable/ubuntu noble main' > /etc/apt/sources.list.d/tailscale.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin tailscale
systemctl enable --now docker tailscaled

if ! tailscale status --json | python3 -c 'import json,sys; sys.exit(json.load(sys.stdin).get("BackendState") != "Running")'; then
    tailscale up --auth-key=file:/run/tailscale-auth.key --ssh --hostname="$(hostname)" --timeout=120s
fi
rm -f /run/tailscale-auth.key
# cloud-init caches user-data containing the now-consumed, single-use auth key.
rm -f /var/lib/cloud/instance/user-data.txt /var/lib/cloud/instance/user-data.txt.i \
    /var/lib/cloud/instance/cloud-config.txt

ADMIN_DOMAIN=$(tailscale status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')
test -n "$ADMIN_DOMAIN"
if [ ! -f .env ]; then
    DB_PASSWORD=$(openssl rand -hex 32)
    DB_ROOT_PASSWORD=$(openssl rand -hex 32)
    trap 'rm -f .env.tmp' EXIT
    {
        cat /opt/ghost/public.env
        printf 'ADMIN_DOMAIN=%s\n' "$ADMIN_DOMAIN"
        printf 'DB_PASSWORD=%s\n' "$DB_PASSWORD"
        printf 'DB_ROOT_PASSWORD=%s\n' "$DB_ROOT_PASSWORD"
    } > .env.tmp
    mv .env.tmp .env
    trap - EXIT
fi
chmod 600 .env
docker compose up -d --wait --wait-timeout 300
timeout 120 tailscale serve --bg --https=443 http://127.0.0.1:2368
touch /opt/ghost/ready
printf 'Ghost ready. Private admin: https://%s/ghost/\n' "$ADMIN_DOMAIN"
