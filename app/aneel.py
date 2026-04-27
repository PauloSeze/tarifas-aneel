"""
Cliente HTTP para a API de Dados Abertos da ANEEL.

Datasets utilizados:
- Tarifas (TUSD + TE):  fcf2906c-7c32-4b9b-a637-054e7a5234f4
- Componentes (Fio B):  a4060165-3a0c-404f-926c-83901088b67c

Referência: https://dadosabertos.aneel.gov.br/
"""

import asyncio
import hashlib
import json
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://dadosabertos.aneel.gov.br/api/3/action/datastore_search"
PACKAGE_SHOW_URL = "https://dadosabertos.aneel.gov.br/api/3/action/package_show"

# Tarifas (TUSD + TE) — 1 CSV agregando todos os anos.
RESOURCE_TARIFAS = "fcf2906c-7c32-4b9b-a637-054e7a5234f4"

# Componentes tarifários (Fio B, etc.) — 1 CSV POR ANO.
# IDs descobertos dinamicamente via package_show; mapa abaixo é fallback offline.
PACKAGE_COMPONENTES = "componentes-tarifarias"
RESOURCE_COMPONENTES_FALLBACK: dict[int, str] = {
    2024: "70ac08d1-53fc-4ceb-9c22-3a3a2c70e9fa",
    2025: "a4060165-3a0c-404f-926c-83901088b67c",
    2026: "e8717aa8-2521-453f-bf16-fbb9a16eea39",
}

DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
DEFAULT_LIMIT = 30
RETRY_ATTEMPTS = 3
RETRY_BACKOFF_BASE = 1.5  # segundos
CACHE_TTL_SECONDS = 3600  # 1h
USER_AGENT = "tarifas-aneel/0.1 (+https://tarifas.midwestengenharia.com.br)"


class AneelError(Exception):
    """Erro na comunicação com a API ANEEL."""


# Cache in-memory simples — chave determinística pelo (resource_id + filters)
_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def _cache_key(resource_id: str, filters: dict[str, str], limit: int, sort: str) -> str:
    payload = json.dumps(
        {"r": resource_id, "f": filters, "l": limit, "s": sort},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _cache_get(key: str) -> list[dict[str, Any]] | None:
    entry = _cache.get(key)
    if entry is None:
        return None
    expira, dados = entry
    if time.time() > expira:
        _cache.pop(key, None)
        return None
    return dados


def _cache_set(key: str, dados: list[dict[str, Any]]) -> None:
    _cache[key] = (time.time() + CACHE_TTL_SECONDS, dados)


async def _consultar(
    client: httpx.AsyncClient,
    resource_id: str,
    filters: dict[str, str],
    *,
    limit: int = DEFAULT_LIMIT,
    sort: str = "DatInicioVigencia desc",
) -> list[dict[str, Any]]:
    key = _cache_key(resource_id, filters, limit, sort)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    params = {
        "resource_id": resource_id,
        "filters": json.dumps(filters),
        "sort": sort,
        "limit": limit,
    }

    last_exc: Exception | None = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            resp = await client.get(BASE_URL, params=params, timeout=DEFAULT_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            registros = data.get("result", {}).get("records", [])
            _cache_set(key, registros)
            return registros
        except (httpx.HTTPError, ValueError) as exc:
            last_exc = exc
            if attempt < RETRY_ATTEMPTS:
                espera = RETRY_BACKOFF_BASE**attempt
                logger.warning(
                    "ANEEL tentativa %d/%d falhou (%s); retry em %.1fs",
                    attempt,
                    RETRY_ATTEMPTS,
                    type(exc).__name__,
                    espera,
                )
                await asyncio.sleep(espera)
            else:
                logger.error("ANEEL falhou após %d tentativas: %s", RETRY_ATTEMPTS, exc)

    raise AneelError(f"ANEEL indisponível após {RETRY_ATTEMPTS} tentativas: {last_exc}")


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(headers={"User-Agent": USER_AGENT})


# Mapa ano → resource_id descoberto via package_show. TTL 24h.
_resource_componentes_cache: dict[int, tuple[float, str]] = {}
_RESOURCE_DISCOVERY_TTL = 86400


async def descobrir_resource_componentes(ano: int) -> str:
    """
    Descobre o resource_id do ano informado consultando o package
    `componentes-tarifarias`. Faz fallback pro mapa hardcoded se a ANEEL
    estiver fora do ar.
    """
    import time

    cached = _resource_componentes_cache.get(ano)
    if cached and time.time() < cached[0]:
        return cached[1]

    try:
        async with _client() as client:
            resp = await client.get(
                PACKAGE_SHOW_URL,
                params={"id": PACKAGE_COMPONENTES},
                timeout=DEFAULT_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            alvo = f"componentes-tarifarias-{ano}.csv"
            for res in data.get("result", {}).get("resources", []):
                if (res.get("name") or "").lower() == alvo:
                    rid = res["id"]
                    _resource_componentes_cache[ano] = (
                        time.time() + _RESOURCE_DISCOVERY_TTL,
                        rid,
                    )
                    return rid
            logger.warning("ano %s nao encontrado no package %s", ano, PACKAGE_COMPONENTES)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("falha em package_show: %s — usando fallback", exc)

    fallback = RESOURCE_COMPONENTES_FALLBACK.get(ano)
    if not fallback:
        raise AneelError(
            f"Nao foi possivel descobrir resource de componentes para {ano}; "
            f"adicione fallback em RESOURCE_COMPONENTES_FALLBACK."
        )
    return fallback


async def buscar_tarifas(
    filters_list: list[dict[str, str]],
) -> list[list[dict[str, Any]]]:
    """
    Faz uma chamada por conjunto de filtros (um por posto tarifário).
    Retorna a lista de registros de cada chamada (mesma ordem dos filtros).
    """
    if not filters_list:
        return []

    async with _client() as client:
        return [await _consultar(client, RESOURCE_TARIFAS, f) for f in filters_list]


async def buscar_fio_b(
    filters: dict[str, str], ano: int | None = None
) -> list[dict[str, Any]]:
    """
    Tenta o ano solicitado primeiro; se vazio, recua ano a ano até achar dados
    (até 3 anos). Resolve o caso 'ano corrente ainda não publicado' e o caso
    'resource do ano antigo limpou registros'.
    """
    from datetime import datetime

    inicio = ano or datetime.now().year
    async with _client() as client:
        for tentativa_ano in (inicio, inicio - 1, inicio - 2):
            resource_id = await descobrir_resource_componentes(tentativa_ano)
            registros = await _consultar(client, resource_id, filters)
            if registros:
                return registros
    return []


async def buscar_tudo(
    tarifa_filters: list[dict[str, str]],
    fio_b_filters: dict[str, str] | None,
    ano: int | None = None,
) -> tuple[list[list[dict[str, Any]]], list[dict[str, Any]]]:
    """Executa todas as consultas em paralelo dentro do mesmo client."""
    from datetime import datetime

    inicio = ano or datetime.now().year

    async with _client() as client:
        tarifas_task = asyncio.gather(
            *[_consultar(client, RESOURCE_TARIFAS, f) for f in tarifa_filters]
        )
        if fio_b_filters:
            fio_b_task = _buscar_fio_b_com_fallback(client, fio_b_filters, inicio)
        else:
            fio_b_task = asyncio.sleep(0, result=[])

        tarifas_records, fio_b_records = await asyncio.gather(tarifas_task, fio_b_task)

    return tarifas_records, fio_b_records  # type: ignore[return-value]


async def _buscar_fio_b_com_fallback(
    client: httpx.AsyncClient, filters: dict[str, str], ano_inicio: int
) -> list[dict[str, Any]]:
    """Tenta o ano e dois anos anteriores até achar registros."""
    for tentativa in (ano_inicio, ano_inicio - 1, ano_inicio - 2):
        resource_id = await descobrir_resource_componentes(tentativa)
        registros = await _consultar(client, resource_id, filters)
        if registros:
            return registros
    return []


def limpar_cache() -> None:
    """Útil para testes ou para forçar refresh."""
    _cache.clear()
