"""
Processamento de records ANEEL → linhas calculadas com tributos aplicados.

Replica fielmente a lógica do `Code in JavaScript4` do workflow n8n.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.tributos import Tributos

# Lei 14.300/2022 — escalonamento do Fio B para clientes GD II
FIOB_RAMP: dict[int, float] = {
    2023: 0.15,
    2024: 0.30,
    2025: 0.45,
    2026: 0.60,
    2027: 0.75,
    2028: 0.90,
}
FIOB_RAMP_POS_2028 = 0.90


def parse_br(valor: Any) -> float:
    """Converte string brasileira (1.234,56) para float."""
    if valor is None:
        return 0.0
    s = str(valor).strip()
    if not s:
        return 0.0
    return float(s.replace(".", "").replace(",", "."))


def is_te_zero_ou_vazio(te: Any) -> bool:
    if te is None:
        return True
    s = str(te).strip()
    return s in ("", ",00", "0", "0,00", "0.00")


def truncar(num: float, casas: int = 5) -> float:
    """Trunca (não arredonda) — n8n usa Math.floor."""
    fator = 10**casas
    return int(num * fator) / fator


def formatar_br(num: float) -> str:
    return f"{truncar(num, 5):.5f}".replace(".", ",")


def extrair_ano_resolucao(reh: str | None) -> int | None:
    if not reh:
        return None
    import re

    match = re.search(r"\b(20\d{2})\b", reh)
    return int(match.group(1)) if match else None


@dataclass
class LinhaTarifa:
    subgrupo: str
    modalidade: str
    posto: str
    posto_original: str
    unidade: str
    tipo: str  # "Consumo" | "Demanda"
    tusd: float
    te: float
    valor_kwh: float
    valor_sem_icms: float


@dataclass
class FioBAno:
    ano: int
    percentual: float
    valor_kwh: float
    atual: bool


@dataclass
class ResultadoConsulta:
    """Resultado completo da consulta — pronto para JSON ou template."""

    distribuidora: str
    grupos: dict[str, list[LinhaTarifa]] = field(default_factory=dict)
    fio_b_base_kwh: float | None = None
    fio_b_resolucao: str | None = None
    fio_b_anos: list[FioBAno] = field(default_factory=list)
    resolucao_tarifas: str | None = None
    ano_vigencia: int | None = None
    tributos: Tributos | None = None
    consultado_em: str = ""


def processar_tarifa(record: dict[str, Any], tributos: Tributos) -> LinhaTarifa:
    """Aplica regras do n8n ao record bruto da ANEEL."""
    subgrupo = record.get("DscSubGrupo", "") or ""
    modalidade = record.get("DscModalidadeTarifaria", "") or ""
    posto_original = record.get("NomPostoTarifario", "") or ""
    unidade = record.get("DscUnidadeTerciaria", "") or ""
    te_raw = record.get("VlrTE")
    tusd_raw = record.get("VlrTUSD")

    # Detecta linha de demanda — ou unidade kW, ou TE vazio
    eh_demanda = (unidade.lower() == "kw") or is_te_zero_ou_vazio(te_raw)

    # Reescreve o nome do posto para "Demanda X" quando aplicável
    if eh_demanda:
        if modalidade == "Geração":
            posto = "Demanda de Geração"
        elif posto_original == "Fora ponta":
            posto = "Demanda Fora Ponta"
        elif posto_original == "Ponta":
            posto = "Demanda Ponta"
        elif posto_original == "Não se aplica":
            posto = "Demanda"
        else:
            posto = f"Demanda {posto_original}"
    else:
        posto = posto_original

    tusd = parse_br(tusd_raw)
    te = 0.0 if is_te_zero_ou_vazio(te_raw) else parse_br(te_raw)
    total = tusd + te

    unidade_final = unidade
    if unidade == "MWh":
        tusd /= 1000
        te /= 1000
        total /= 1000
        unidade_final = "kWh"

    return LinhaTarifa(
        subgrupo=subgrupo,
        modalidade=modalidade,
        posto=posto,
        posto_original=posto_original,
        unidade=unidade_final,
        tipo="Demanda" if eh_demanda else "Consumo",
        tusd=tributos.aplicar(tusd),
        te=tributos.aplicar(te),
        valor_kwh=tributos.aplicar(total),
        valor_sem_icms=tributos.aplicar_sem_icms(total),
    )


def processar_fio_b(
    records: list[dict[str, Any]],
    tributos: Tributos,
    ano_atual: int | None = None,
) -> tuple[float | None, str | None, list[FioBAno]]:
    """
    Pega o primeiro registro (mais recente) e gera os 6 cards de escalonamento.
    Retorna (base_kwh_sem_tributos, resolucao, lista_anos).
    """
    if not records:
        return None, None, []

    primeiro = records[0]
    base_mwh = parse_br(primeiro.get("VlrComponenteTarifario"))
    base_kwh = base_mwh / 1000
    resolucao = primeiro.get("DscResolucaoHomologatoria")

    ano_atual = ano_atual or datetime.now().year
    anos_card = sorted(FIOB_RAMP.keys())
    cards: list[FioBAno] = []
    for ano in anos_card:
        cards.append(
            FioBAno(
                ano=ano,
                percentual=FIOB_RAMP[ano],
                valor_kwh=base_kwh * FIOB_RAMP[ano],
                atual=ano == ano_atual,
            )
        )
    return base_kwh, resolucao, cards


def montar_resultado(
    distribuidora: str,
    tarifa_records: list[list[dict[str, Any]]],
    fio_b_records: list[dict[str, Any]],
    tributos: Tributos,
    ano_solicitado: int | None = None,
) -> ResultadoConsulta:
    """Combina todos os records nas estruturas finais."""

    grupos: dict[str, list[LinhaTarifa]] = {}
    resolucao_geral: str | None = None
    ano_vigencia: int | None = None

    for batch in tarifa_records:
        if not batch:
            continue

        if ano_solicitado is not None:
            # Filtra todos os registros cuja vigência começa no ano solicitado
            registros = [
                r
                for r in batch
                if (r.get("DatInicioVigencia") or "").startswith(str(ano_solicitado))
            ]
            if not registros:
                registros = [batch[0]]
        else:
            # Default: pega registros da vigência mais recente
            # (mantém múltiplos se compartilharem a mesma DatInicioVigencia)
            vigencia_topo = batch[0].get("DatInicioVigencia") or ""
            registros = [r for r in batch if (r.get("DatInicioVigencia") or "") == vigencia_topo]

        for r in registros:
            linha = processar_tarifa(r, tributos)
            chave = f"{linha.subgrupo} - {linha.modalidade}"
            grupos.setdefault(chave, []).append(linha)

            if not resolucao_geral:
                resolucao_geral = r.get("DscREH")
            if ano_vigencia is None:
                vig = r.get("DatInicioVigencia") or ""
                if vig and len(vig) >= 4 and vig[:4].isdigit():
                    ano_vigencia = int(vig[:4])

    base_fio_b, reh_fio_b, cards = processar_fio_b(
        fio_b_records, tributos, ano_atual=ano_vigencia or ano_solicitado
    )

    if not resolucao_geral and reh_fio_b:
        resolucao_geral = reh_fio_b
    if ano_vigencia is None:
        ano_vigencia = extrair_ano_resolucao(resolucao_geral)

    return ResultadoConsulta(
        distribuidora=distribuidora,
        grupos=grupos,
        fio_b_base_kwh=base_fio_b,
        fio_b_resolucao=reh_fio_b,
        fio_b_anos=cards,
        resolucao_tarifas=resolucao_geral,
        ano_vigencia=ano_vigencia,
        tributos=tributos,
        consultado_em=datetime.now().strftime("%d/%m/%Y %H:%M"),
    )
