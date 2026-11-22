from datetime import timedelta

DOMAIN = "portale_consumi"
NAME = "Portale Consumi SII"

BASE_URL = "https://www.consumienergia.it/portaleConsumi/legacyapi/rs/it/"

API_FORNITURE_ELETTRICHE = "fornitureElettricheService.json"
API_FORNITURE_GAS = "fornitureGasService.json"
API_CONSUMI_ELETTRICI = "consumiElettricoService.json"
API_CONSUMI_GAS = "consumiGasService.json"

# Individuati nelle conversazioni, ma non chiamati finché parametri e risposte
# non sono descritti in modo sufficiente.
API_PROCESSI_ELETTRICI = "processiElettricoService.json"
API_PROCESSI_GAS = "processiGasService.json"

CONF_COOKIE_HEADER = "cookie_header"
CONF_SCAN_INTERVAL_HOURS = "scan_interval_hours"

DEFAULT_SCAN_INTERVAL_HOURS = 168  # una settimana
MIN_SCAN_INTERVAL_HOURS = 24
MAX_SCAN_INTERVAL_HOURS = 720

# Richiesta leggera per tenere viva la sessione fra un aggiornamento e l'altro.
KEEPALIVE_MINUTES = 10

DEFAULT_SCAN_INTERVAL = timedelta(hours=DEFAULT_SCAN_INTERVAL_HOURS)

KEY_FORNITURE_ELETTRICHE = "forniture_elettriche"
KEY_FORNITURE_GAS = "forniture_gas"
KEY_CONSUMI_ELETTRICI = "consumi_elettrici"
KEY_CONSUMI_GAS = "consumi_gas"
KEY_LAST_UPDATE = "last_update"

POD_KEYS = ("codice_pod", "codice_pod_pdr", "pod", "code")
PDR_KEYS = ("codice_pdr", "codice_pod_pdr", "pdr", "code")
