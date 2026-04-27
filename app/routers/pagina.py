"""
GET /  →  form HTML
POST /consultar  →  resultado HTML
"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app import aneel
from app.calculos import formatar_br, montar_resultado
from app.grupos import (
    DISTRIBUIDORAS,
    construir_filtros_fio_b,
    construir_filtros_tarifa,
    normalizar_grupo,
)
from app.tributos import COFINS_DEFAULT, ICMS_DEFAULT, PIS_DEFAULT, Tributos

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.filters["br"] = formatar_br

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "form.html",
        {
            "request": request,
            "distribuidoras": DISTRIBUIDORAS,
            "pis_default": PIS_DEFAULT,
            "cofins_default": COFINS_DEFAULT,
            "icms_default": ICMS_DEFAULT,
        },
    )


@router.post("/consultar", response_class=HTMLResponse)
async def consultar(
    request: Request,
    distribuidora: Annotated[str, Form()] = "EMT",
    grupos: Annotated[list[str], Form()] = ["B-Convencional"],
    pis_pct: Annotated[float, Form()] = PIS_DEFAULT * 100,
    cofins_pct: Annotated[float, Form()] = COFINS_DEFAULT * 100,
    icms_pct: Annotated[float, Form()] = ICMS_DEFAULT * 100,
) -> HTMLResponse:
    grupos_normalizados = []
    for raw in grupos:
        g = normalizar_grupo(raw)
        if g and g not in grupos_normalizados:
            grupos_normalizados.append(g)

    if not grupos_normalizados:
        raise HTTPException(400, "Selecione ao menos um grupo")

    tarifa_filters: list[dict[str, str]] = []
    fio_b_filters = None
    for g in grupos_normalizados:
        if g == "Fio B":
            fio_b_filters = construir_filtros_fio_b(distribuidora)
        else:
            tarifa_filters.extend(construir_filtros_tarifa(g, distribuidora))

    try:
        tarifa_records, fio_b_records = await aneel.buscar_tudo(tarifa_filters, fio_b_filters)
    except aneel.AneelError as exc:
        raise HTTPException(502, f"ANEEL indisponível: {exc}") from exc
    # ano não vem do form V1 — usa ano corrente automaticamente

    tributos = Tributos(pis=pis_pct / 100, cofins=cofins_pct / 100, icms=icms_pct / 100)
    resultado = montar_resultado(
        distribuidora=distribuidora,
        tarifa_records=tarifa_records,
        fio_b_records=fio_b_records,
        tributos=tributos,
        ano_solicitado=None,
    )

    pediu_fio_b = "Fio B" in grupos_normalizados
    fio_b_indisponivel = pediu_fio_b and resultado.fio_b_base_kwh is None

    return templates.TemplateResponse(
        "resultado.html",
        {
            "request": request,
            "resultado": resultado,
            "tributos": tributos,
            "distribuidora": distribuidora,
            "pediu_fio_b": pediu_fio_b,
            "fio_b_indisponivel": fio_b_indisponivel,
        },
    )
