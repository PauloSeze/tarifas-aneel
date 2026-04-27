# Tarifas ANEEL

Consulta de tarifas homologadas da ANEEL com brutalização tributária.
Replica e expande o workflow n8n `Tarifas Energia` (`ZuZY3hgP4upKhD7D`).

**Produção:** [tarifas.midwestengenharia.com.br](https://tarifas.midwestengenharia.com.br)

## V1 — Energisa MT (EMT)

Grupos suportados:

- **B - Convencional** (B1 Residencial)
- **A4 - Azul** (Fora Ponta + Ponta)
- **A4 - Verde** (Fora Ponta + Ponta + Não se aplica)
- **A4 - Geração**
- **Fio B** (componente TUSD escalonado pela Lei 14.300/2022)

Tributos PIS/COFINS/ICMS são editáveis por consulta. Default vem da última fatura
EMT extraída (PIS 0,4659% / COFINS 2,1458% / ICMS 17%).

## Endpoints

```
GET  /                  Form HTML
POST /consultar         Resultado HTML
GET  /api/tarifas       JSON estruturado
GET  /healthz           Health check
```

### Exemplo de query

```bash
curl 'http://localhost:8000/api/tarifas?distribuidora=EMT&grupos=B-Convencional,FioB&pis=0.004659&cofins=0.021458&icms=0.17'
```

## Como rodar local

```bash
python -m venv .venv
.venv\Scripts\activate    # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Deploy

Coolify aponta para este Dockerfile.
Domínio `tarifas.midwestengenharia.com.br`.

## Estrutura

```
app/
├── main.py              FastAPI app
├── aneel.py             Cliente HTTP da API ANEEL Dados Abertos
├── grupos.py            GROUP_MAP (filtros por grupo tarifário)
├── tributos.py          Defaults + brutalização
├── calculos.py          Processamento de records (demanda, Fio B, etc.)
└── routers/
    ├── tarifas.py       JSON
    └── pagina.py        HTML (Jinja2)
```

## Roadmap

- V1: EMT, todos os grupos do n8n, tributos editáveis
- V2: outras distribuidoras Energisa (EMS, ETO, ERO)
- V3: histórico (consultar tarifas vigentes em ano específico)
- V4: comparativo entre distribuidoras
