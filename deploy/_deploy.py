"""
Deploy do tarifas-aneel no VPS via paramiko.

Etapas:
1. Cria /srv/midwest com Caddyfile + docker-compose.yml
2. Clona/atualiza repo PauloSeze/tarifas-aneel em /srv/midwest/tarifas-aneel
3. docker compose build + up
4. Reporta status
"""

import os
import shlex
import sys
from pathlib import Path

import paramiko

HOST = "177.7.36.193"
KEY_PATH = str(Path.home() / ".ssh" / "midwest_vps")
DEPLOY_DIR = Path(__file__).resolve().parent

CADDYFILE = (DEPLOY_DIR / "Caddyfile").read_text(encoding="utf-8")

COMPOSE_YAML = """\
name: midwest

services:
  caddy:
    image: caddy:2-alpine
    container_name: caddy
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    networks:
      - web

  tarifas-aneel:
    build:
      context: ./tarifas-aneel
      dockerfile: Dockerfile
    container_name: tarifas-aneel
    restart: unless-stopped
    networks:
      - web
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8000/healthz"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s

networks:
  web:
    name: web
    driver: bridge

volumes:
  caddy_data:
  caddy_config:
"""

REMOTE_SCRIPT = r"""
set -eu
mkdir -p /srv/midwest
cd /srv/midwest

# clona ou atualiza repo
if [ -d tarifas-aneel/.git ]; then
  cd tarifas-aneel && git fetch --all --quiet && git reset --hard origin/main >/dev/null && cd ..
else
  rm -rf tarifas-aneel
  git clone --depth 1 https://github.com/PauloSeze/tarifas-aneel.git tarifas-aneel >/dev/null 2>&1
fi

# build + up
docker compose pull caddy 2>/dev/null || true
docker compose build tarifas-aneel
docker compose up -d --remove-orphans

echo
echo "==CONTAINERS=="
docker compose ps
echo
echo "==CADDY LOGS==(ultimas 30 linhas)"
docker compose logs --tail=30 caddy 2>&1 | tail -30
"""


def run(client: paramiko.SSHClient, cmd: str) -> tuple[int, str, str]:
    _, stdout, stderr = client.exec_command(cmd, timeout=300)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    rc = stdout.channel.recv_exit_status()
    return rc, out, err


def write_file(sftp: paramiko.SFTPClient, path: str, content: str) -> None:
    with sftp.open(path, "w") as f:
        f.write(content)
    sftp.chmod(path, 0o644)


def main() -> None:
    pkey = paramiko.Ed25519Key.from_private_key_file(KEY_PATH)
    last_err: Exception | None = None
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    for attempt in range(1, 8):
        try:
            print(f"-- tentativa {attempt}: conectando {HOST}")
            c.connect(HOST, username="root", pkey=pkey, timeout=15,
                      look_for_keys=False, allow_agent=False, banner_timeout=30,
                      auth_timeout=15)
            break
        except (paramiko.SSHException, OSError, TimeoutError) as exc:
            last_err = exc
            print(f"   falhou ({type(exc).__name__}: {exc}), retry...")
            import time as _t
            _t.sleep(5)
    else:
        sys.exit(f"sem conexao apos retries: {last_err}")

    print("-- garantindo /srv/midwest")
    rc, out, err = run(c, "mkdir -p /srv/midwest && echo ok")
    if rc != 0:
        sys.exit(f"mkdir falhou: {err}")

    print("-- enviando Caddyfile e docker-compose.yml")
    sftp = c.open_sftp()
    write_file(sftp, "/srv/midwest/Caddyfile", CADDYFILE)
    write_file(sftp, "/srv/midwest/docker-compose.yml", COMPOSE_YAML)
    sftp.close()

    print("-- executando deploy")
    rc, out, err = run(c, REMOTE_SCRIPT)
    sys.stdout.buffer.write(out.encode("utf-8"))
    if err.strip():
        sys.stdout.buffer.write(b"\n--- stderr ---\n")
        sys.stdout.buffer.write(err.encode("utf-8"))
    print(f"\n[exit {rc}]")
    c.close()


if __name__ == "__main__":
    main()
