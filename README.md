<p align="center">
  <img src="images/logo.png" alt="Portale Consumi SII" width="160">
</p>

<h1 align="center">Portale Consumi SII</h1>

<p align="center">
  🇮🇹 <a href="#-italiano">Italiano</a> · 🇬🇧 <a href="#-english">English</a>
</p>

<p align="center">
  <a href="https://github.com/hacs/integration"><img src="https://img.shields.io/badge/HACS-Custom-orange.svg" alt="HACS Custom"></a>
  <img src="https://img.shields.io/badge/Home%20Assistant-custom%20integration-blue.svg" alt="Home Assistant">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT">
</p>

---

## 🇮🇹 Italiano

Integrazione personalizzata per **Home Assistant** che legge i consumi di **luce e gas** dal [Portale Consumi](https://www.consumienergia.it/portaleConsumi/) del SII (Sistema Informativo Integrato), anche per i periodi di precedenti fornitori.

### Funzionalità

- Rileva automaticamente i **POD** (luce) e i **PDR** (gas) con un contratto attivo.
- Sensori di **consumo per anno solare** (totale) e **per ciascun mese** (gennaio–dicembre), per luce (kWh) e gas (m³).
- Unisce le misure di contratti e gestori diversi sullo stesso punto, preferendo la lettura più recente (e una rettifica a parità di data).
- Importa tutta la storia mensile come **statistiche esterne** (`portale_consumi:luce_<pod>`, `portale_consumi:gas_<pdr>`), selezionabili nella **dashboard Energia**.
- Sensori di servizio: forniture elettriche/gas attive e ultimo aggiornamento.
- Intervallo di aggiornamento configurabile (da 24 a 720 ore, predefinito una settimana).
- Gestione della scadenza sessione con **reautenticazione** e **riconfigurazione** dal menu dell'integrazione.
- Interfaccia in italiano e inglese.

### Installazione con HACS

1. HACS → menu ⋮ → **Repository personalizzati**.
2. Aggiungi `https://github.com/Manu-Nat/portale-consumi-ha` con categoria **Integrazione**.
3. Cerca **Portale Consumi SII**, scarica e **riavvia Home Assistant**.

### Installazione manuale

Copia la cartella `custom_components/portale_consumi` nella cartella `custom_components` della tua configurazione e riavvia Home Assistant.

### Configurazione

1. **Impostazioni → Dispositivi e servizi → Aggiungi integrazione → Portale Consumi SII**.
2. Accedi al portale con il tuo browser (SPID/CIE) e copia l'intero valore dell'header **`Cookie`** di una richiesta già autenticata (strumenti per sviluppatori → Rete).
3. Incollalo nel campo richiesto e scegli l'intervallo di aggiornamento.

### Come ottenere il cookie di autenticazione

Esempio con Chrome/Edge (su Firefox e Safari i passaggi sono simili):

1. Apri [consumienergia.it/portaleConsumi](https://www.consumienergia.it/portaleConsumi/) e accedi con SPID o CIE, fino a vedere le tue forniture.
2. Premi **F12** (oppure tasto destro → **Ispeziona**) e apri la scheda **Rete** (*Network*).
3. Ricarica la pagina con **F5**. Nel campo filtro scrivi `Service.json`.
4. Clicca una richiesta dell'elenco, ad esempio `fornitureElettricheService.json`.
5. Nel pannello a destra, scheda **Intestazioni** (*Headers*), sezione **Intestazioni richiesta** (*Request Headers*), trova la riga **`Cookie`**.
6. Clicca col tasto destro sul valore → **Copia valore** (oppure selezionalo tutto e copialo): deve essere l'**intera** stringa, di solito lunga, con più coppie `nome=valore` separate da `;`.
7. Incollala in Home Assistant nel campo **Header Cookie completo**.

Consigli:
- Il cookie è come una password: **non condividerlo e non pubblicarlo** (né in issue, né in log, né in screenshot).
- La sessione scade dopo un certo tempo. Quando succede, Home Assistant mostra la notifica di reautenticazione: ripeti i passaggi sopra e incolla il nuovo cookie. Puoi anche sostituirlo prima dalla voce **Riconfigura** dell'integrazione.
- Se la validazione fallisce con "sessione rifiutata", il cookie è incompleto o scaduto: copialo di nuovo subito dopo aver ricaricato la pagina del portale.

> ⚠️ **Non inserire mai credenziali SPID o CIE.** L'integrazione usa soltanto il cookie di una sessione già autenticata, che resta salvato nella tua istanza di Home Assistant. Quando la sessione scade, Home Assistant avvia la procedura di reautenticazione e ti chiede un nuovo cookie.

### Rinnovo automatico della sessione

Home Assistant fa una richiesta leggera al portale **ogni 10 minuti** per tenere viva la sessione e salva i cookie che il portale rinnova, così non devi reincollarli. Se la sessione scade comunque (il portale risponde `503 API_INVALID_RESPONSE`) e il sito è raggiungibile, Home Assistant avvia la **riautenticazione** e ti chiede un nuovo cookie. Non vengono salvate credenziali SPID o CIE.

### Entità

| Entità | Descrizione |
| --- | --- |
| `PortaleConsumi - Consumo elettrico anno solare` | Totale kWh dell'anno corrente (attributo `consumi_mensili`) |
| `PortaleConsumi - Consumo elettrico <mese>` | kWh del singolo mese |
| `PortaleConsumi - Consumo gas anno solare` | Totale m³ dell'anno corrente |
| `PortaleConsumi - Consumo gas <mese>` | m³ del singolo mese |
| `PortaleConsumi - Forniture elettriche attive` | Numero di POD con contratto attivo |
| `PortaleConsumi - Forniture gas attive` | Numero di PDR con contratto attivo |
| `PortaleConsumi - Ultimo aggiornamento` | Data e ora dell'ultimo aggiornamento riuscito |

### Dashboard Energia

Per ogni POD e PDR viene creata una statistica con una riga per mese, posta alla mezzanotte del primo giorno. In **Impostazioni → Dashboard → Energia** scegli `Luce … (SII)` come consumo dalla rete e `Gas … (SII)` come consumo di gas.

- Nelle viste **mese** e **anno** i totali sono corretti; nella vista **giorno** il consumo del mese appare tutto il giorno 1.
- I dati del portale arrivano con settimane o mesi di ritardo.
- Il gas è pubblicato in **Smc** e mostrato come m³ (differenza di pochi punti percentuali).
- Se il portale smette di pubblicare i mesi più vecchi, la somma già registrata non torna indietro.

### Note

- I dati sono quelli pubblicati dal portale e possono avere ritardi di settimane/mesi: i mesi senza misura risultano non disponibili (`mesi_mancanti`).
- Il gas è espresso nell'unità del portale (Smc), mostrata come m³.
- Progetto non ufficiale e non affiliato al SII né ai gestori. Usalo a tuo rischio.

---

## 🇬🇧 English

Custom integration for **Home Assistant** that reads your **electricity and gas** consumption from the SII (Italian Integrated Information System) [Portale Consumi](https://www.consumienergia.it/portaleConsumi/), including periods served by previous suppliers.

### Features

- Automatically detects the **POD** (electricity) and **PDR** (gas) points with an active contract.
- **Calendar-year** (total) and **per-month** (January–December) consumption sensors for electricity (kWh) and gas (m³).
- Merges readings from different contracts/suppliers on the same point, preferring the most recent reading (and a correction when dates are equal).
- Imports the full monthly history as **external statistics** (`portale_consumi:luce_<pod>`, `portale_consumi:gas_<pdr>`), selectable in the **Energy dashboard**.
- Service sensors: active electricity/gas supplies and last update.
- Configurable update interval (24 to 720 hours, default one week).
- Session expiry handled through **reauthentication** and **reconfiguration** from the integration menu.
- Italian and English UI.

### Installation with HACS

1. HACS → ⋮ menu → **Custom repositories**.
2. Add `https://github.com/Manu-Nat/portale-consumi-ha` with category **Integration**.
3. Search for **Portale Consumi SII**, download it and **restart Home Assistant**.

### Manual installation

Copy the `custom_components/portale_consumi` folder into your configuration's `custom_components` folder and restart Home Assistant.

### Setup

1. **Settings → Devices & services → Add integration → Portale Consumi SII**.
2. Log in to the portal in your browser (SPID/CIE) and copy the full value of the **`Cookie`** header from an already authenticated request (developer tools → Network).
3. Paste it in the requested field and choose the update interval.

### How to get the authentication cookie

Example with Chrome/Edge (Firefox and Safari work similarly):

1. Open [consumienergia.it/portaleConsumi](https://www.consumienergia.it/portaleConsumi/) and log in with SPID or CIE until you see your supplies.
2. Press **F12** (or right-click → **Inspect**) and open the **Network** tab.
3. Reload the page with **F5**. In the filter box type `Service.json`.
4. Click one of the requests in the list, e.g. `fornitureElettricheService.json`.
5. In the right-hand panel, **Headers** tab, **Request Headers** section, find the **`Cookie`** line.
6. Right-click the value → **Copy value** (or select it all and copy it): it must be the **whole** string, usually long, made of several `name=value` pairs separated by `;`.
7. Paste it into Home Assistant in the **Full Cookie header** field.

Tips:
- The cookie works like a password: **do not share or publish it** (not in issues, logs or screenshots).
- The session expires after some time. When it does, Home Assistant shows a reauthentication notification: repeat the steps above and paste the new cookie. You can also replace it earlier via the integration's **Reconfigure** option.
- If validation fails with "session rejected", the cookie is incomplete or expired: copy it again right after reloading the portal page.

> ⚠️ **Never enter SPID or CIE credentials.** The integration only uses the cookie of an already authenticated session, which is stored inside your Home Assistant instance. When the session expires, Home Assistant starts the reauthentication flow and asks for a new cookie.

### Automatic session renewal

Home Assistant sends a lightweight request to the portal **every 10 minutes** to keep the session alive and saves the cookies the portal renews, so you don't have to paste them again. If the session expires anyway (the portal answers `503 API_INVALID_RESPONSE`) and the site is reachable, Home Assistant starts **reauthentication** and asks for a new cookie. No SPID or CIE credentials are stored.

### Entities

| Entity | Description |
| --- | --- |
| `PortaleConsumi - Consumo elettrico anno solare` | Current-year total in kWh (`consumi_mensili` attribute) |
| `PortaleConsumi - Consumo elettrico <month>` | kWh for a single month |
| `PortaleConsumi - Consumo gas anno solare` | Current-year total in m³ |
| `PortaleConsumi - Consumo gas <month>` | m³ for a single month |
| `PortaleConsumi - Forniture elettriche attive` | Number of PODs with an active contract |
| `PortaleConsumi - Forniture gas attive` | Number of PDRs with an active contract |
| `PortaleConsumi - Ultimo aggiornamento` | Date and time of the last successful update |

### Energy dashboard

For each POD and PDR a statistic is created with one row per month, placed at midnight on the first day. In **Settings → Dashboards → Energy** pick `Luce … (SII)` as grid consumption and `Gas … (SII)` as gas consumption.

- In the **month** and **year** views totals are correct; in the **day** view the whole month's consumption appears on day 1.
- Portal data arrives with a delay of weeks or months.
- Gas is published in **Smc** and shown as m³ (a difference of a few percent).
- If the portal stops publishing older months, the sum already recorded does not go backwards.

### Notes

- Data is whatever the portal publishes and can lag by weeks/months: months without a reading are reported as unavailable (`mesi_mancanti`).
- Gas uses the portal's unit (Smc), shown as m³.
- Unofficial project, not affiliated with SII or any energy supplier. Use at your own risk.

---

<p align="center">Licenza / License: <a href="LICENSE">MIT</a></p>

<p align="center">
  Rinnovo sessione e statistiche / Session renewal and statistics: <a href="https://github.com/EnrCol/ha-consumi-sii">EnrCol/ha-consumi-sii</a> (MIT)
</p>
