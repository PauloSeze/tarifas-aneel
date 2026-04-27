"""
Tributos default e brutalização tributária.

Default = última fatura EMT processada (abril/2026).
Os valores podem ser sobrescritos por consulta via querystring/form.
"""

from dataclasses import dataclass


# Defaults extraídos da fatura Energisa MT mais recente (abr/2026).
# Manter alinhado com .claude/tools/config/tributacao.json do midwest workspace.
PIS_DEFAULT = 0.004659
COFINS_DEFAULT = 0.021458
ICMS_DEFAULT = 0.17


@dataclass(frozen=True)
class Tributos:
    pis: float
    cofins: float
    icms: float

    @property
    def divisor_completo(self) -> float:
        """Divisor com PIS + COFINS + ICMS."""
        return (1 - (self.pis + self.cofins)) * (1 - self.icms)

    @property
    def divisor_sem_icms(self) -> float:
        """Divisor sem ICMS — usado em demanda 'Não Consumida'."""
        return 1 - (self.pis + self.cofins)

    def aplicar(self, valor_sem_tributos: float) -> float:
        """Brutaliza valor da ANEEL para tarifa cobrada do consumidor."""
        return valor_sem_tributos / self.divisor_completo

    def aplicar_sem_icms(self, valor_sem_tributos: float) -> float:
        """Brutaliza com PIS+COFINS, sem ICMS."""
        return valor_sem_tributos / self.divisor_sem_icms


def tributos_default() -> Tributos:
    return Tributos(pis=PIS_DEFAULT, cofins=COFINS_DEFAULT, icms=ICMS_DEFAULT)
