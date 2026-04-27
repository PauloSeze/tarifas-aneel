# Deploy

Configuração para rodar `tarifas-aneel` em VPS Ubuntu com Docker + Caddy.

## Stack

- **Caddy 2**: reverse proxy + SSL automático (Let's Encrypt)
- **tarifas-aneel**: container FastAPI

## Localização no servidor

```
/srv/midwest/
├── docker-compose.yml
├── Caddyfile
└── tarifas-aneel/        # clone do repo, fonte do build
```

## Adicionar nova app

1. Adicionar bloco no `Caddyfile`:
   ```
   nome.midwestengenharia.com.br {
       reverse_proxy nome-app:porta
   }
   ```
2. Adicionar serviço no `docker-compose.yml` (network `web`)
3. `docker compose up -d` + `docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile`

## Atualizar tarifas-aneel

```
cd /srv/midwest/tarifas-aneel
git pull
cd /srv/midwest
docker compose build tarifas-aneel
docker compose up -d tarifas-aneel
```

## Logs

```
docker compose logs -f tarifas-aneel
docker compose logs -f caddy
```
