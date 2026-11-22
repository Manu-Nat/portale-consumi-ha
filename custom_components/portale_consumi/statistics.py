"""Statistiche esterne mensili, utilizzabili nella dashboard Energia.

Ogni misura mensile del portale diventa una riga oraria posta alla
mezzanotte locale del primo giorno del mese. Nella vista mensile e annuale
della dashboard Energia il totale è corretto; nella vista giornaliera il
consumo appare tutto il giorno 1.

Adattato da EnrCol/ha-consumi-sii (MIT).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    statistics_during_period,
)
from homeassistant.const import UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
_EPOCH = datetime(2000, 1, 1, tzinfo=dt_util.UTC)
_STAT_ID_UNSAFE = re.compile(r"[^a-z0-9_]")


def statistic_id(commodity: str, code: str) -> str:
    """ID di statistica esterna valido per il recorder (``dominio:oggetto``)."""
    return f"{DOMAIN}:{commodity}_{_STAT_ID_UNSAFE.sub('_', code.lower())}"


def mask_code(code: str) -> str:
    """Codice abbreviato per i nomi visibili (ultime 4 cifre)."""
    code = code.strip()
    return f"…{code[-4:]}" if len(code) > 4 else code


def cumulative_months(months: dict[str, float]) -> list[tuple[int, int, float, float]]:
    """(anno, mese, consumo, somma progressiva) dalla prima competenza.

    ``months`` ha chiave ``YYYYMM``. I mesi mancanti tra due misure valgono 0,
    così la somma resta monotona.
    """
    if not months:
        return []
    keys = sorted(months)
    year, month = int(keys[0][:4]), int(keys[0][4:])
    last_year, last_month = int(keys[-1][:4]), int(keys[-1][4:])
    rows: list[tuple[int, int, float, float]] = []
    total = 0.0
    while (year, month) <= (last_year, last_month):
        value = months.get(f"{year}{month:02d}", 0.0)
        total = round(total + value, 3)
        rows.append((year, month, value, total))
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return rows


def _month_start(year: int, month: int) -> datetime:
    return dt_util.as_utc(
        datetime(year, month, 1, tzinfo=dt_util.get_default_time_zone())
    )


async def _sum_before(hass: HomeAssistant, stat_id: str, before: datetime) -> float:
    """Somma già registrata prima della prima competenza importata.

    Se il portale smette di pubblicare i mesi più vecchi, la serie riparte
    da qui invece che da zero e la somma non torna indietro.
    """
    rows = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        _EPOCH,
        before,
        {stat_id},
        "hour",
        None,
        {"sum"},
    )
    series = rows.get(stat_id) or []
    if not series:
        return 0.0
    return float(series[-1].get("sum") or 0.0)


async def async_import_series(
    hass: HomeAssistant, electric: bool, code: str, months: dict[str, float]
) -> None:
    """Scrive (o riscrive) tutta la serie mensile di un POD o PDR."""
    rows = cumulative_months(months)
    if not rows:
        return

    commodity = "luce" if electric else "gas"
    stat_id = statistic_id(commodity, code)
    try:
        first_start = _month_start(rows[0][0], rows[0][1])
        offset = await _sum_before(hass, stat_id, first_start)

        metadata = StatisticMetaData(
            mean_type=StatisticMeanType.NONE,
            has_sum=True,
            name=f"{'Luce' if electric else 'Gas'} {mask_code(code)} (SII)",
            source=DOMAIN,
            statistic_id=stat_id,
            unit_class="energy" if electric else "volume",
            unit_of_measurement=(
                UnitOfEnergy.KILO_WATT_HOUR if electric else UnitOfVolume.CUBIC_METERS
            ),
        )
        statistics = [
            StatisticData(
                start=_month_start(year, month),
                state=value,
                sum=round(offset + total, 3),
            )
            for year, month, value, total in rows
        ]
        async_add_external_statistics(hass, metadata, statistics)
    except Exception:  # noqa: BLE001 - il recorder non deve bloccare i sensori
        _LOGGER.warning("Impossibile importare le statistiche di %s", stat_id, exc_info=True)
        return
    _LOGGER.debug("Importate %d righe mensili in %s", len(statistics), stat_id)
