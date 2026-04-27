"""Testa lógica de processamento sem chamar a ANEEL."""

from app.calculos import (
    formatar_br,
    is_te_zero_ou_vazio,
    montar_resultado,
    parse_br,
    processar_tarifa,
    truncar,
)
from app.tributos import tributos_default


def test_parse_br():
    assert parse_br("1.234,56") == 1234.56
    assert parse_br("0,32540") == 0.3254
    assert parse_br("") == 0.0
    assert parse_br(None) == 0.0


def test_te_zero_detecta_demanda():
    assert is_te_zero_ou_vazio("")
    assert is_te_zero_ou_vazio(",00")
    assert is_te_zero_ou_vazio("0,00")
    assert is_te_zero_ou_vazio(None)
    assert not is_te_zero_ou_vazio("0,15")


def test_truncar_nao_arredonda():
    # 0.123456 truncado a 5 casas = 0.12345 (não 0.12346)
    assert truncar(0.123456, 5) == 0.12345


def test_formatar_br_usa_virgula():
    assert formatar_br(0.852130) == "0,85213"


def test_brutalizacao_b1_residencial():
    """Aplica PIS+COFINS+ICMS sobre tarifa ANEEL pura."""
    record = {
        "DscSubGrupo": "B1",
        "DscModalidadeTarifaria": "Convencional",
        "NomPostoTarifario": "Não se aplica",
        "DscUnidadeTerciaria": "MWh",
        "VlrTUSD": "340,00",  # 340 R$/MWh = 0,34 R$/kWh
        "VlrTE": "320,00",  # 320 R$/MWh = 0,32 R$/kWh
    }
    linha = processar_tarifa(record, tributos_default())
    # 0,66 sem tributos / ((1 - 0,004659 - 0,021458) * (1 - 0,17)) ≈ 0,8167
    assert linha.tipo == "Consumo"
    assert linha.unidade == "kWh"
    assert abs(linha.valor_kwh - 0.66 / ((1 - 0.004659 - 0.021458) * (1 - 0.17))) < 1e-6


def test_demanda_renomeia_posto_a4_azul():
    """Quando TE vazio em A4 - Azul, vira 'Demanda Fora Ponta'/'Demanda Ponta'."""
    record_fora = {
        "DscSubGrupo": "A4",
        "DscModalidadeTarifaria": "Azul",
        "NomPostoTarifario": "Fora ponta",
        "DscUnidadeTerciaria": "kW",
        "VlrTUSD": "30,00",
        "VlrTE": "",
    }
    linha = processar_tarifa(record_fora, tributos_default())
    assert linha.tipo == "Demanda"
    assert linha.posto == "Demanda Fora Ponta"


def test_demanda_geracao_renomeia():
    record = {
        "DscSubGrupo": "A4",
        "DscModalidadeTarifaria": "Geração",
        "NomPostoTarifario": "Não se aplica",
        "DscUnidadeTerciaria": "kW",
        "VlrTUSD": "12,00",
        "VlrTE": ",00",
    }
    linha = processar_tarifa(record, tributos_default())
    assert linha.posto == "Demanda de Geração"


def test_montar_resultado_pega_apenas_vigencia_mais_recente():
    """Sem ano_solicitado, deve descartar registros de vigências antigas."""
    batch_b1 = [
        {
            "DscSubGrupo": "B1",
            "DscModalidadeTarifaria": "Convencional",
            "NomPostoTarifario": "Não se aplica",
            "DscUnidadeTerciaria": "MWh",
            "VlrTUSD": "340,00",
            "VlrTE": "320,00",
            "DatInicioVigencia": "2026-04-22",
            "DscREH": "RESOLUÇÃO HOMOLOGATÓRIA Nº 3.581/2026",
        },
        {
            "DscSubGrupo": "B1",
            "DscModalidadeTarifaria": "Convencional",
            "NomPostoTarifario": "Não se aplica",
            "DscUnidadeTerciaria": "MWh",
            "VlrTUSD": "320,00",  # vigência antiga
            "VlrTE": "300,00",
            "DatInicioVigencia": "2025-04-01",
            "DscREH": "RESOLUÇÃO HOMOLOGATÓRIA Nº 3.440/2025",
        },
    ]

    resultado = montar_resultado(
        distribuidora="EMT",
        tarifa_records=[batch_b1],
        fio_b_records=[],
        tributos=tributos_default(),
        ano_solicitado=None,
    )

    chave = "B1 - Convencional"
    assert chave in resultado.grupos
    assert len(resultado.grupos[chave]) == 1, "Deve descartar a vigência antiga"
    assert resultado.ano_vigencia == 2026
    assert "3.581" in (resultado.resolucao_tarifas or "")


def test_montar_resultado_filtro_por_ano_pega_vigencia_correta():
    batch_b1 = [
        {
            "DscSubGrupo": "B1",
            "DscModalidadeTarifaria": "Convencional",
            "NomPostoTarifario": "Não se aplica",
            "DscUnidadeTerciaria": "MWh",
            "VlrTUSD": "340,00",
            "VlrTE": "320,00",
            "DatInicioVigencia": "2026-04-22",
            "DscREH": "RH 3.581/2026",
        },
        {
            "DscSubGrupo": "B1",
            "DscModalidadeTarifaria": "Convencional",
            "NomPostoTarifario": "Não se aplica",
            "DscUnidadeTerciaria": "MWh",
            "VlrTUSD": "320,00",
            "VlrTE": "300,00",
            "DatInicioVigencia": "2025-04-01",
            "DscREH": "RH 3.440/2025",
        },
    ]

    resultado = montar_resultado(
        distribuidora="EMT",
        tarifa_records=[batch_b1],
        fio_b_records=[],
        tributos=tributos_default(),
        ano_solicitado=2025,
    )

    chave = "B1 - Convencional"
    assert chave in resultado.grupos
    linhas = resultado.grupos[chave]
    assert len(linhas) == 1
    # TUSD 0,32 R$/kWh com tributos:
    esperado = 0.62 / ((1 - 0.004659 - 0.021458) * (1 - 0.17))
    assert abs(linhas[0].valor_kwh - esperado) < 1e-6


def test_fio_b_gera_seis_cards_com_escalonamento():
    fio_b_records = [
        {
            "VlrComponenteTarifario": "320,00",  # R$/MWh
            "DscResolucaoHomologatoria": "RH 3.581/2026",
            "DatInicioVigencia": "2026-04-22",
        }
    ]
    resultado = montar_resultado(
        distribuidora="EMT",
        tarifa_records=[],
        fio_b_records=fio_b_records,
        tributos=tributos_default(),
        ano_solicitado=2026,
    )
    assert resultado.fio_b_base_kwh is not None
    assert abs(resultado.fio_b_base_kwh - 0.32) < 1e-6
    assert len(resultado.fio_b_anos) == 6
    atuais = [c for c in resultado.fio_b_anos if c.atual]
    assert len(atuais) == 1
    assert atuais[0].ano == 2026
    assert atuais[0].percentual == 0.60
    assert abs(atuais[0].valor_kwh - 0.32 * 0.60) < 1e-6
