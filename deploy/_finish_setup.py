"""Finaliza o que o _provision.py deixou pelo caminho. Idempotente."""

import os
import sys

import paramiko

HOST = "177.7.36.193"
PASS = os.environ["VPS_PASS"]

# UTF-8 friendly: nada de seta unicode aqui
SETUP = r"""
set -eu
mkdir -p /srv/midwest
chmod 755 /srv/midwest

# UFW (idempotente)
ufw allow 22/tcp >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
echo y | ufw enable >/dev/null 2>&1 || true
ufw status verbose

# SSH hardening: usa drop-in (forma mais limpa que sed)
cat > /etc/ssh/sshd_config.d/99-midwest.conf <<'EOF'
PasswordAuthentication no
PermitRootLogin prohibit-password
PubkeyAuthentication yes
EOF
chmod 644 /etc/ssh/sshd_config.d/99-midwest.conf

# Validar config antes de aplicar
sshd -t && systemctl reload ssh

echo
echo "==SSH AUTH STATE=="
sshd -T 2>/dev/null | grep -E '^(passwordauthentication|permitrootlogin|pubkeyauthentication)'

echo
echo "==DIRS=="
ls -la /srv/midwest

echo
echo "==DOCKER=="
docker --version
docker compose version
"""


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PASS, timeout=20, look_for_keys=False, allow_agent=False)
    _, stdout, stderr = c.exec_command(SETUP)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    rc = stdout.channel.recv_exit_status()
    sys.stdout.buffer.write(out.encode("utf-8"))
    if err.strip():
        sys.stdout.buffer.write(b"\n--- stderr ---\n")
        sys.stdout.buffer.write(err.encode("utf-8"))
    print(f"\n[exit {rc}]")
    c.close()


if __name__ == "__main__":
    main()
