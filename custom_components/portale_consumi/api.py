"""Client HTTP per i servizi osservati del Portale Consumi."""

from __future__ import annotations

import json
import logging
import ssl
from http.cookies import Morsel
from pathlib import Path
from typing import Any

import aiohttp

from .const import (
    API_CONSUMI_ELETTRICI,
    API_CONSUMI_GAS,
    API_FORNITURE_ELETTRICHE,
    API_FORNITURE_GAS,
    BASE_URL,
)

_LOGGER = logging.getLogger(__name__)


class PortaleConsumiError(Exception):
    """Errore generico del client Portale Consumi."""


class PortaleConsumiAuthError(PortaleConsumiError):
    """La sessione non è accettata dal portale."""


class PortaleConsumiSessionSuspect(PortaleConsumiError):
    """HTTP 503 ``API_INVALID_RESPONSE``.

    Il portale risponde così a una sessione non valida o scaduta (non usa
    401/403), ma potrebbe anche essere un disservizio. Chi la riceve decide
    se trattarla come sessione scaduta.
    """


def _error_code(payload: Any) -> str | None:
    try:
        return payload["response"]["errors"]["error"]["code"]
    except (KeyError, TypeError):
        return None


def unwrap_result(payload: Any) -> Any:
    """Estrae response.result, decodificandolo se è una stringa JSON."""
    if not isinstance(payload, dict):
        raise PortaleConsumiError("La risposta del servizio non è un oggetto JSON.")

    response = payload.get("response")
    if not isinstance(response, dict) or "result" not in response:
        raise PortaleConsumiError("La risposta non contiene response.result.")

    result = response["result"]
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError as err:
            raise PortaleConsumiError(
                "response.result è una stringa ma non contiene JSON valido."
            ) from err

    if result is None:
        raise PortaleConsumiError("response.result è vuoto.")

    return result


def parse_cookie_header(header: str) -> dict[str, str]:
    """``a=1; b=2`` → ``{"a": "1", "b": "2"}``, ordine conservato.

    Accetta anche la riga intera copiata dagli strumenti sviluppatore
    (``Cookie: a=1; b=2``).
    """
    header = header.strip()
    if header.lower().startswith("cookie:"):
        header = header[7:]
    cookies: dict[str, str] = {}
    for part in header.split(";"):
        name, sep, value = part.strip().partition("=")
        if sep and name.strip():
            cookies[name.strip()] = value.strip()
    return cookies


def format_cookie_header(cookies: dict[str, str]) -> str:
    return "; ".join(f"{name}={value}" for name, value in cookies.items())


def _is_deletion(morsel: Morsel) -> bool:
    if not morsel.value:
        return True
    max_age = morsel.get("max-age")
    if max_age not in (None, ""):
        try:
            return int(max_age) <= 0
        except ValueError:
            return False
    return False


def merge_set_cookies(cookies: dict[str, str], received: Any) -> bool:
    """Applica i Set-Cookie ricevuti; ``True`` se qualcosa è cambiato."""
    changed = False
    for name, morsel in received.items():
        if _is_deletion(morsel):
            if name in cookies:
                del cookies[name]
                changed = True
        elif cookies.get(name) != morsel.value:
            cookies[name] = morsel.value
            changed = True
    return changed


def _build_ssl_context() -> ssl.SSLContext:
    """Contesto SSL standard + eventuale certificato intermedio del portale."""
    ctx = ssl.create_default_context()
    ca_file = Path(__file__).parent / "ca_intermedio.pem"
    if ca_file.exists():
        ctx.load_verify_locations(cafile=str(ca_file))
    return ctx


async def async_build_ssl_context(hass) -> ssl.SSLContext:
    # Il caricamento dei certificati è bloccante: va fatto in un executor.
    return await hass.async_add_executor_job(_build_ssl_context)


class PortaleConsumiApi:
    """Interroga gli endpoint confermati usando una sessione fornita dall’utente."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        cookie_header: str,
    ) -> None:
        self._session = session
        self._cookies = parse_cookie_header(cookie_header)
        if not self._cookies:
            raise PortaleConsumiAuthError("L'header Cookie è vuoto o non valido.")

    @property
    def cookie_header(self) -> str:
        """Header aggiornato con gli eventuali rinnovi del portale."""
        return format_cookie_header(self._cookies)

    async def _get(self, endpoint: str, params: dict[str, str] | None = None) -> Any:
        url = BASE_URL + endpoint
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Cookie": self.cookie_header,
        }

        try:
            async with self._session.get(
                url,
                params=params,
                headers=headers,
                allow_redirects=False,
            ) as response:
                if response.status in (401, 403) or 300 <= response.status < 400:
                    raise PortaleConsumiAuthError(
                        "Il portale ha rifiutato la sessione o rimanda all'accesso."
                    )
                if response.status == 503:
                    try:
                        body = await response.json(content_type=None)
                    except (aiohttp.ContentTypeError, json.JSONDecodeError, ValueError):
                        body = None
                    if _error_code(body) == "API_INVALID_RESPONSE":
                        raise PortaleConsumiSessionSuspect(
                            "Il portale non ha restituito dati (API_INVALID_RESPONSE): "
                            "sessione scaduta o servizio non disponibile."
                        )
                if response.status != 200:
                    raise PortaleConsumiError(
                        f"{endpoint} ha restituito HTTP {response.status}."
                    )
                content_type = response.headers.get("Content-Type", "").lower()
                if "text/html" in content_type:
                    raise PortaleConsumiAuthError(
                        "Il portale ha restituito la pagina di accesso invece dei dati. "
                        "La sessione potrebbe essere scaduta."
                    )
                if merge_set_cookies(self._cookies, response.cookies):
                    _LOGGER.debug("Il portale ha rinnovato uno o più cookie di sessione")
                try:
                    payload = await response.json(content_type=None)
                except (aiohttp.ContentTypeError, json.JSONDecodeError) as err:
                    raise PortaleConsumiError(
                        "La risposta del portale non è JSON valido."
                    ) from err

        except PortaleConsumiError:
            raise
        except (aiohttp.ClientError, TimeoutError) as err:
            raise PortaleConsumiError(f"Errore di rete: {err}") from err

        return unwrap_result(payload)

    async def portal_is_up(self) -> bool:
        """La home pubblica del portale risponde? Distingue un disservizio
        da una sessione scaduta."""
        try:
            async with self._session.get(
                BASE_URL.split("legacyapi")[0], allow_redirects=False
            ) as response:
                return response.status == 200
        except (aiohttp.ClientError, TimeoutError):
            return False

    async def get_forniture_elettriche(self) -> Any:
        # Parametri osservati nella richiesta del portale: sono stringhe
        # letterali, così le invia il frontend.
        return await self._get(
            API_FORNITURE_ELETTRICHE,
            {"cf_delega": "null", "denominazione_delegato": "undefined"},
        )

    async def get_forniture_gas(self) -> Any:
        return await self._get(
            API_FORNITURE_GAS,
            {"cf_delega": "null", "denominazione_delegato": "undefined"},
        )

    async def get_consumi_elettrici(self, pod: str) -> Any:
        return await self._get(API_CONSUMI_ELETTRICI, {"code": pod})

    async def get_consumi_gas(self, pdr: str) -> Any:
        return await self._get(API_CONSUMI_GAS, {"code": pdr})
