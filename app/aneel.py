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

RESOURCE_TARIFAS = "fcf2906c-7c32-4b9b-a637-054e7a5234f4"
RESOURCE_COMPONENTES = "a4060165-3a0c-404f-926c-83901088b67c"

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


async def buscar_fio_b(filters: dict[str, str]) -> list[dict[str, Any]]:
    async with _client() as client:
        return await _consultar(client, RESOURCE_COMPONENTES, filters)


async def buscar_tudo(
    tarifa_filters: list[dict[str, str]],
    fio_b_filters: dict[str, str] | None,
) -> tuple[list[list[dict[str, Any]]], list[dict[str, Any]]]:
    """Executa todas as consultas em paralelo dentro do mesmo client."""
    async with _client() as client:
        tarifas_task = asyncio.gather(
            *[_consultar(client, RESOURCE_TARIFAS, f) for f in tarifa_filters]
        )
        fio_b_task = (
            _consultar(client, RESOURCE_COMPONENTES, fio_b_filters)
            if fio_b_filters
            else asyncio.sleep(0, result=[])
        )
        tarifas_records, fio_b_records = await asyncio.gather(tarifas_task, fio_b_task)

    return tarifas_records, fio_b_records  # type: ignore[return-value]


def limpar_cache() -> None:
    """Útil para testes ou para forçar refresh."""
    _cache.clear()
