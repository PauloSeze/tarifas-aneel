"""
Mapa de grupos tarifários para filtros da API ANEEL.

Replica fielmente o GROUP_MAP do workflow n8n `Tarifas Energia`.
"""

from typing import Literal, TypedDict


# Concessionárias Energisa atendidas (sigla = SigAgente do dataset ANEEL).
# UF é só pro display; a sigla é o que vai pro filtro da API.
DISTRIBUIDORAS: dict[str, dict[str, str]] = {
    "EMT": {"nome": "Energisa Mato Grosso", "uf": "MT"},
    "EMS": {"nome": "Energisa Mato Grosso do Sul", "uf": "MS"},
    "ETO": {"nome": "Energisa Tocantins", "uf": "TO"},
    "ERO": {"nome": "Energisa Rondônia", "uf": "RO"},
    "EAC": {"nome": "Energisa Acre", "uf": "AC"},
    "EPB": {"nome": "Energisa Paraíba", "uf": "PB"},
    "EBO": {"nome": "Energisa Borborema", "uf": "PB"},
    "ESE": {"nome": "Energisa Sergipe", "uf": "SE"},
    "ENF": {"nome": "Energisa Nova Friburgo", "uf": "RJ"},
    "EMR": {"nome": "Energisa Minas Rio", "uf": "MG"},
    "EMG": {"nome": "Energisa Minas Gerais", "uf": "MG"},
    "ESS": {"nome": "Energisa Sul-Sudeste", "uf": "SP/PR"},
}

GrupoNome = Literal[
    "B - Convencional",
    "A4 - Azul",
    "A4 - Verde",
    "A4 - Geração",
    "Fio B",
]

# Aliases aceitos via querystring (sem espaços/acentos)
GRUPO_ALIAS: dict[str, GrupoNome] = {
    "B-Convencional": "B - Convencional",
    "B": "B - Convencional",
    "A4-Azul": "A4 - Azul",
    "A4-Verde": "A4 - Verde",
    "A4-Geracao": "A4 - Geração",
    "A4-Geração": "A4 - Geração",
    "FioB": "Fio B",
    "Fio-B": "Fio B",
}


class ConfigGrupo(TypedDict):
    DscSubGrupo: str
    DscModalidadeTarifaria: str
    DscDetalhe: str
    postos: list[str]


GROUP_MAP: dict[GrupoNome, ConfigGrupo] = {
    "B - Convencional": {
        "DscSubGrupo": "B1",
        "DscModalidadeTarifaria": "Convencional",
        "DscDetalhe": "Não se aplica",
        "postos": ["Não se aplica"],
    },
    "A4 - Azul": {
        "DscSubGrupo": "A4",
        "DscModalidadeTarifaria": "Azul",
        "DscDetalhe": "Não se aplica",
        "postos": ["Fora ponta", "Ponta"],
    },
    "A4 - Verde": {
        "DscSubGrupo": "A4",
        "DscModalidadeTarifaria": "Verde",
        "DscDetalhe": "Não se aplica",
        "postos": ["Fora ponta", "Ponta", "Não se aplica"],
    },
    "A4 - Geração": {
        "DscSubGrupo": "A4",
        "DscModalidadeTarifaria": "Geração",
        "DscDetalhe": "Não se aplica",
        "postos": ["Não se aplica"],
    },
}


# Filtros do componente Fio B (dataset diferente do dataset de tarifas)
FIO_B_FILTERS: dict[str, str] = {
    "DscComponenteTarifario": "TUSD_FioB",
    "DscBaseTarifaria": "Tarifa de Aplicação",
    "DscSubGrupoTarifario": "B1",
    "DscModalidadeTarifaria": "Convencional",
    "DscClasseConsumidor": "Residencial",
    "DscSubClasseConsumidor": "Residencial",
    "DscDetalheConsumidor": "Não se aplica",
    "DscPostoTarifario": "Não se aplica",
}


def normalizar_grupo(valor: str) -> GrupoNome | None:
    """Aceita tanto o nome canônico quanto aliases sem espaço/acento."""
    if valor in GROUP_MAP or valor == "Fio B":
        return valor  # type: ignore[return-value]
    return GRUPO_ALIAS.get(valor)


def construir_filtros_tarifa(grupo: GrupoNome, distribuidora: str) -> list[dict[str, str]]:
    """
    Monta os filtros do dataset de TARIFAS para um grupo.
    Retorna uma lista (um por posto tarifário).
    """
    if grupo == "Fio B":
        return []

    conf = GROUP_MAP[grupo]
    base: dict[str, str] = {
        "SigAgente": distribuidora,
        "DscBaseTarifaria": "Tarifa de Aplicação",
        "DscSubGrupo": conf["DscSubGrupo"],
        "DscModalidadeTarifaria": conf["DscModalidadeTarifaria"],
        "DscDetalhe": conf["DscDetalhe"],
    }

    # B1 é Residencial; A4 é "Não se aplica"
    if grupo == "B - Convencional":
        base["DscClasse"] = "Residencial"
        base["DscSubClasse"] = "Residencial"
    else:
        base["DscClasse"] = "Não se aplica"
        base["DscSubClasse"] = "Não se aplica"

    return [{**base, "NomPostoTarifario": posto} for posto in conf["postos"]]


def construir_filtros_fio_b(distribuidora: str) -> dict[str, str]:
    """Filtros do dataset de COMPONENTES (Fio B)."""
    return {"SigNomeAgente": distribuidora, **FIO_B_FILTERS}
