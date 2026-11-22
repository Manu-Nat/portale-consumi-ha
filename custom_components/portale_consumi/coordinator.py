"""Aggiornamento periodico e aggregazione delle misure per anno solare."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

import aiohttp

from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .api import (
    PortaleConsumiApi,
    PortaleConsumiAuthError,
    PortaleConsumiError,
    PortaleConsumiSessionSuspect,
)
from .const import (
    CONF_COOKIE_HEADER,
    CONF_SCAN_INTERVAL_HOURS,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DOMAIN,
    KEY_CONSUMI_ELETTRICI,
    KEY_CONSUMI_GAS,
    KEY_FORNITURE_ELETTRICHE,
    KEY_FORNITURE_GAS,
    KEY_LAST_UPDATE,
    KEEPALIVE_MINUTES,
)
from .statistics import async_import_series

_LOGGER = logging.getLogger(__name__)

KEY_CALENDAR_YEAR = "calendar_year"
KEY_CALENDAR_ELECTRIC = "calendar_electric"
KEY_CALENDAR_GAS = "calendar_gas"

_ELECTRIC_DELTA_KEYS = tuple(f"delta_misure_f{i}" for i in range(1, 7))


def _parse_date(value: Any) -> date | None:
    """Converte una data YYYYMMDD del portale."""
    if not isinstance(value, str) or len(value) != 8 or not value.isdigit():
        return None
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        return None


def _point_codes_with_active_supply(
    payload: Any,
    point_key: str,
    code_key: str,
    today: date,
) -> list[str]:
    """Restituisce i POD/PDR che hanno almeno un contratto attivo oggi."""
    if not isinstance(payload, dict) or not isinstance(payload.get(point_key), list):
        raise PortaleConsumiError(
            f"La risposta forniture non contiene l'elenco {point_key} previsto."
        )

    codes: set[str] = set()

    for point in payload[point_key]:
        if not isinstance(point, dict):
            continue

        code = point.get(code_key)
        supplies = point.get("forniture")

        if not isinstance(code, str) or not code.strip() or not isinstance(supplies, list):
            continue

        for supply in supplies:
            if not isinstance(supply, dict):
                continue

            start = _parse_date(supply.get("data_inizio_fornitura"))
            end_value = supply.get("data_fine_fornitura")
            end = _parse_date(end_value)

            # Una data di fine vuota identifica il contratto corrente nel
            # campione fornito. Una data futura è ancora attiva oggi.
            end_is_open = end_value in (None, "")
            starts_by_today = start is None or start <= today
            ends_after_today = end_is_open or (end is not None and end >= today)

            if starts_by_today and ends_after_today:
                codes.add(code.strip())
                break

    return sorted(codes)


def _iter_monthly_records(payload: Any):
    """Legge misure_mensili; usa misure_altre_frequenze solo come ripiego."""
    if isinstance(payload, list):
        for item in payload:
            yield from _iter_monthly_records(item)
        return

    if not isinstance(payload, dict):
        return

    monthly = payload.get("misure_mensili")
    other_frequency = payload.get("misure_altre_frequenze")

    if isinstance(monthly, list):
        for record in monthly:
            if isinstance(record, dict):
                yield record
    elif isinstance(other_frequency, list):
        for record in other_frequency:
            if isinstance(record, dict):
                yield record

    # Continua nei contenitori esterni, evitando di rileggere gli stessi
    # array mensili come se fossero un secondo insieme di misure.
    for key, value in payload.items():
        if key not in ("misure_mensili", "misure_altre_frequenze"):
            yield from _iter_monthly_records(value)


def _number(value: Any) -> float | None:
    """Converte un numero della risposta, mantenendo null come dato mancante."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _record_consumption(record: dict, commodity: str) -> float | None:
    """Estrae il delta di consumo elettrico o gas."""
    if commodity == "gas":
        return _number(record.get("delta_misure"))

    fascia_values = [_number(record.get(key)) for key in _ELECTRIC_DELTA_KEYS]
    if any(value is not None for value in fascia_values):
        return sum(value for value in fascia_values if value is not None)

    # Il portale può fornire la misura elettrica monoraria al posto delle fasce.
    return _number(record.get("delta_misure_monoraria"))


def _calendar_for_year(
    usage_by_point: dict[str, Any],
    commodity: str,
    year: int,
) -> dict[str, Any]:
    """Unisce i contratti dello stesso punto e prepara gennaio-dicembre."""
    # Per ogni competenza conserva la lettura più recente; a parità di data
    # preferisce una rettifica rispetto a una lettura periodica.
    selected: dict[str, tuple[tuple[str, int], float]] = {}

    for payload in usage_by_point.values():
        for record in _iter_monthly_records(payload):
            competence = str(record.get("competenza_consumi", ""))
            if len(competence) != 6 or not competence.isdigit():
                continue
            if competence[:4] != str(year):
                continue

            value = _record_consumption(record, commodity)
            if value is None:
                continue

            reading_date = str(record.get("data_lettura") or "")
            is_correction = int("rettifica" in str(record.get("tipo_misura", "")).lower())
            rank = (reading_date, is_correction)

            previous = selected.get(competence)
            if previous is None or rank > previous[0]:
                selected[competence] = (rank, value)

    months: dict[str, float | None] = {}
    for month in range(1, 13):
        competence = f"{year}{month:02d}"
        entry = selected.get(competence)
        months[f"{month:02d}"] = entry[1] if entry else None

    available = [value for value in months.values() if value is not None]

    return {
        "year": year,
        "months": months,
        "total": sum(available) if available else None,
        "months_available": len(available),
        "months_missing": [
            month for month, value in months.items() if value is None
        ],
    }


def _monthly_series(payload: Any, commodity: str) -> dict[str, float]:
    """Serie mensile ``YYYYMM`` → consumo di un singolo POD/PDR.

    Unisce contratti e gestori dello stesso punto: per ogni competenza tiene
    la lettura più recente, a parità di data preferisce una rettifica.
    """
    selected: dict[str, tuple[tuple[str, int], float]] = {}
    for record in _iter_monthly_records(payload):
        competence = str(record.get("competenza_consumi", ""))
        if len(competence) != 6 or not competence.isdigit():
            continue
        if not 1 <= int(competence[4:]) <= 12:
            continue
        value = _record_consumption(record, commodity)
        if value is None:
            continue
        reading_date = str(record.get("data_lettura") or "")
        is_correction = int("rettifica" in str(record.get("tipo_misura", "")).lower())
        rank = (reading_date, is_correction)
        previous = selected.get(competence)
        if previous is None or rank > previous[0]:
            selected[competence] = (rank, value)
    return {key: round(value, 3) for key, (_, value) in sorted(selected.items())}


class PortaleConsumiCoordinator(DataUpdateCoordinator):
    """Recupera i punti attivi e le misure annuali, incluse quelle di gestori cessati."""

    def __init__(self, hass, entry, session: aiohttp.ClientSession) -> None:
        interval_hours = entry.options.get(
            CONF_SCAN_INTERVAL_HOURS,
            DEFAULT_SCAN_INTERVAL_HOURS,
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=interval_hours),
        )
        self.interval_hours = interval_hours
        self.entry = entry
        self.api = PortaleConsumiApi(
            session,
            entry.data[CONF_COOKIE_HEADER],
        )

    async def _async_update_data(self) -> dict:
        try:
            electric_supplies = await self.api.get_forniture_elettriche()
            gas_supplies = await self.api.get_forniture_gas()

            today = dt_util.now().date()
            year = today.year

            electric_codes = _point_codes_with_active_supply(
                electric_supplies, "pod", "codice_pod", today
            )
            gas_codes = _point_codes_with_active_supply(
                gas_supplies, "pdr", "codice_pdr", today
            )

            # Una chiamata per POD/PDR. Il servizio restituisce le misure
            # associate al punto, comprese quelle dei precedenti gestori.
            electric_usage = {}
            for code in electric_codes:
                electric_usage[code] = await self.api.get_consumi_elettrici(code)

            gas_usage = {}
            for code in gas_codes:
                gas_usage[code] = await self.api.get_consumi_gas(code)

            # Statistiche mensili per la dashboard Energia, una per POD/PDR.
            for code, payload in electric_usage.items():
                await async_import_series(
                    self.hass, True, code, _monthly_series(payload, "electric")
                )
            for code, payload in gas_usage.items():
                await async_import_series(
                    self.hass, False, code, _monthly_series(payload, "gas")
                )

            return {
                KEY_FORNITURE_ELETTRICHE: electric_supplies,
                KEY_FORNITURE_GAS: gas_supplies,
                KEY_CONSUMI_ELETTRICI: electric_usage,
                KEY_CONSUMI_GAS: gas_usage,
                KEY_CALENDAR_YEAR: year,
                KEY_CALENDAR_ELECTRIC: _calendar_for_year(
                    electric_usage, "electric", year
                ),
                KEY_CALENDAR_GAS: _calendar_for_year(
                    gas_usage, "gas", year
                ),
                "active_electric_points": len(electric_codes),
                "active_gas_points": len(gas_codes),
                KEY_LAST_UPDATE: dt_util.utcnow(),
            }

        except PortaleConsumiAuthError as err:
            raise ConfigEntryAuthFailed(
                "Sessione del Portale Consumi scaduta o non valida."
            ) from err
        except PortaleConsumiSessionSuspect as err:
            # Il portale risponde così alle sessioni scadute; se la home
            # pubblica è raggiungibile il problema è la sessione.
            if await self.api.portal_is_up():
                raise ConfigEntryAuthFailed(
                    "Sessione del Portale Consumi scaduta: serve un nuovo accesso."
                ) from err
            raise UpdateFailed(str(err)) from err
        except (PortaleConsumiError, aiohttp.ClientError) as err:
            raise UpdateFailed(str(err)) from err
        finally:
            self._persist_renewed_cookie()

    @callback
    def async_start_keepalive(self) -> None:
        """Una richiesta leggera ogni 10 minuti tiene viva la sessione del
        portale fra un aggiornamento e l'altro."""
        self.entry.async_on_unload(
            async_track_time_interval(
                self.hass, self._async_keepalive, timedelta(minutes=KEEPALIVE_MINUTES)
            )
        )

    async def _async_keepalive(self, _now: datetime) -> None:
        try:
            await self.api.get_forniture_elettriche()
        except (PortaleConsumiAuthError, PortaleConsumiSessionSuspect):
            if isinstance(self.last_exception, ConfigEntryAuthFailed):
                return  # reautenticazione già avviata dal coordinator
            if await self.api.portal_is_up():
                _LOGGER.info(
                    "Sessione del Portale Consumi scaduta: avvio la riautenticazione"
                )
                self.entry.async_start_reauth(self.hass)
        except PortaleConsumiError as err:
            _LOGGER.debug("Mantenimento sessione non riuscito: %s", err)
        finally:
            self._persist_renewed_cookie()

    def _persist_renewed_cookie(self) -> None:
        """Salva l'header se il portale ha rinnovato la sessione (senza ricaricare)."""
        header = self.api.cookie_header
        if header != self.entry.data.get(CONF_COOKIE_HEADER):
            self.hass.config_entries.async_update_entry(
                self.entry,
                data={**self.entry.data, CONF_COOKIE_HEADER: header},
            )