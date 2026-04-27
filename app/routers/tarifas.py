"""
GET /api/tarifas — JSON estruturado.

Permite outras integrações (n8n, frontends, scripts) consumirem
as tarifas calculadas com tributos aplicados.
"""

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app import aneel
from app.calculos import montar_resultado
from app.grupos import (
    GrupoNome,
    construir_filtros_fio_b,
    construir_filtros_tarifa,
    normalizar_grupo,
)
from app.tributos import COFINS_DEFAULT, ICMS_DEFAULT, PIS_DEFAULT, Tributos

router = APIRouter(prefix="/api", tags=["tarifas"])

GRUPOS_DEFAULT = "B-Convencional,A4-Azul,A4-Verde,A4-Geracao,FioB"


@router.get("/tarifas")
async def consultar_tarifas(
    distribuidora: Annotated[str, Query(description="Sigla ANEEL (ex: EMT)")] = "EMT",
    grupos: Annotated[
        str,
        Query(description="Lista separada por vírgula. Ex: B-Convencional,FioB"),
    ] = GRUPOS_DEFAULT,
    ano: Annotated[int | None, Query(description="Ano da resolução (default: vigente)")] = None,
    pis: Annotated[float, Query(ge=0, le=1)] = PIS_DEFAULT,
    cofins: Annotated[float, Query(ge=0, le=1)] = COFINS_DEFAULT,
    icms: Annotated[float, Query(ge=0, le=1)] = ICMS_DEFAULT,
):
    grupos_lista: list[GrupoNome] = []
    for raw in grupos.split(","):
        raw = raw.strip()
        if not raw:
            continue
        grupo = normalizar_grupo(raw)
        if grupo is None:
            raise HTTPException(400, f"Grupo desconhecido: {raw!r}")
        if grupo not in grupos_lista:
            grupos_lista.append(grupo)

    if not grupos_lista:
        raise HTTPException(400, "Nenhum grupo informado")

    tarifa_filters: list[dict[str, str]] = []
    fio_b_filters = None
    for g in grupos_lista:
        if g == "Fio B":
            fio_b_filters = construir_filtros_fio_b(distribuidora)
        else:
            tarifa_filters.extend(construir_filtros_tarifa(g, distribuidora))

    try:
        tarifa_records, fio_b_records = await aneel.buscar_tudo(tarifa_filters, fio_b_filters)
    except aneel.AneelError as exc:
        raise HTTPException(502, f"ANEEL indisponível: {exc}") from exc

    tributos = Tributos(pis=pis, cofins=cofins, icms=icms)
    resultado = montar_resultado(
        distribuidora=distribuidora,
        tarifa_records=tarifa_records,
        fio_b_records=fio_b_records,
        tributos=tributos,
        ano_solicitado=ano,
    )

    return {
        "distribuidora": resultado.distribuidora,
        "ano_vigencia": resultado.ano_vigencia,
        "resolucao": resultado.resolucao_tarifas,
        "consultado_em": resultado.consultado_em,
        "tributos": {
            "pis": tributos.pis,
            "cofins": tributos.cofins,
            "icms": tributos.icms,
        },
        "grupos": {
            nome: [asdict(linha) for linha in linhas]
            for nome, linhas in resultado.grupos.items()
        },
        "fio_b": {
            "base_kwh_sem_tributos": resultado.fio_b_base_kwh,
            "resolucao": resultado.fio_b_resolucao,
            "anos": [asdict(a) for a in resultado.fio_b_anos],
        }
        if resultado.fio_b_base_kwh is not None
        else None,
    }
