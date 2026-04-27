"""Pega logs dos containers via paramiko."""
import sys
from pathlib import Path

import paramiko

HOST = "177.7.36.193"
KEY_PATH = str(Path.home() / ".ssh" / "midwest_vps")

CMD = """
cd /srv/midwest
echo "==CADDY==" && docker compose logs --tail=60 caddy 2>&1 | tail -60
echo
echo "==TARIFAS==" && docker compose logs --tail=20 tarifas-aneel 2>&1 | tail -20
echo
echo "==STATUS==" && docker compose ps
"""

def main() -> None:
    pkey = paramiko.Ed25519Key.from_private_key_file(KEY_PATH)
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    for _ in range(8):
        try:
            c.connect(HOST, username="root", pkey=pkey, timeout=15,
                      look_for_keys=False, allow_agent=False, banner_timeout=30,
                      auth_timeout=15)
            break
        except (paramiko.SSHException, OSError, TimeoutError) as exc:
            print(f"retry: {exc}", file=sys.stderr)
            import time; time.sleep(4)
    else:
        sys.exit("sem conexao")
    _, out, err = c.exec_command(CMD, timeout=60)
    sys.stdout.buffer.write(out.read())
    e = err.read()
    if e.strip():
        sys.stdout.buffer.write(b"\n--stderr--\n")
        sys.stdout.buffer.write(e)
    c.close()

if __name__ == "__main__":
    main()
