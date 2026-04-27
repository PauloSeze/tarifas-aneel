"""
Provisionamento inicial do VPS via paramiko.

USO ÚNICO — após primeira execução, autenticação é por chave SSH e este script
nem é necessário (usa-se ssh direto). NÃO COMMITAR.

Etapas:
1. Login com senha root
2. Instalar pubkey do Claude em /root/.ssh/authorized_keys
3. Atualizar sistema
4. Instalar Docker + curl + ufw + git
5. Configurar UFW (22, 80, 443)
6. Endurecer SSH (PasswordAuthentication=no)
7. Restart sshd
"""

import os
import sys
from pathlib import Path

import paramiko

HOST = "177.7.36.193"
USER = "root"
PASS = os.environ.get("VPS_PASS")

PUBKEY = (Path.home() / ".ssh" / "midwest_vps.pub").read_text().strip()

SETUP = f"""
set -euxo pipefail
mkdir -p /root/.ssh
chmod 700 /root/.ssh
grep -qxF '{PUBKEY}' /root/.ssh/authorized_keys 2>/dev/null \\
  || echo '{PUBKEY}' >> /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq curl ca-certificates ufw git

# Docker oficial
if ! command -v docker >/dev/null; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $VERSION_CODENAME stable" > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
systemctl enable --now docker

# UFW
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# Diretorio padrao
mkdir -p /srv/midwest

# SSH hardening (mantem permite root via key, bloqueia senha)
sed -i 's/^#\\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#\\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
sed -i 's/^#\\?PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config
systemctl restart ssh || systemctl restart sshd

echo "=== versions ==="
docker --version
docker compose version
ufw status verbose | head -15
echo "=== done ==="
"""


def main():
    if not PASS:
        sys.exit("env VPS_PASS nao definida")
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"-- conectando {USER}@{HOST}")
    c.connect(HOST, username=USER, password=PASS, timeout=30, look_for_keys=False, allow_agent=False)
    print("-- conectado, enviando setup")
    stdin, stdout, stderr = c.exec_command(SETUP, get_pty=True)
    for raw in iter(stdout.readline, ""):
        if raw:
            print(raw.rstrip())
    rc = stdout.channel.recv_exit_status()
    err = stderr.read().decode("utf-8", "replace")
    if err.strip():
        print("--- stderr ---")
        print(err)
    print(f"-- exit code: {rc}")
    c.close()


if __name__ == "__main__":
    main()
