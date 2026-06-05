# Dexcom Developer API setup (E8 Phase 0)

One-time steps to validate the official Dexcom API v3 `/events` endpoint as the insulin
source (replacing manual Clarity CSV export). This is the **different** Dexcom API from
the Share API `pydexcom` uses for glucose - it is OAuth-based and needs an app.

## 1. Register an app
1. Create an account at https://developer.dexcom.com and sign in.
2. **My Apps -> Add App.** Note the **Client ID** and **Client Secret**.
3. Set the **Redirect URI** to `http://localhost:8080/` (if Dexcom rejects http, use
   `https://localhost:8080/`). The probe never runs a server there - you just copy the
   `code` out of the redirected URL.

## 2. Sandbox first, then real data
- **Sandbox** works immediately, no approval - simulated data, good for confirming the
  OAuth flow end to end. Base URL: `https://sandbox-api.dexcom.com`.
- **Real data:** My Apps -> your app -> **Apply for Upgrade -> Individual** (Limited
  Access, up to 5 users - covers personal use). Base URL once approved:
  - EU / outside-US: `https://api.dexcom.eu`  *(confirm this is the host your account
    uses - it mirrors the `clarity.dexcom.eu` pattern; US production is
    `https://api.dexcom.com`)*

Only scope is `offline_access`; Dexcom grants access to all your data with it (no
per-endpoint scopes).

## 3. Create the creds file
Create `dexcom_api_creds.json` at the project root (gitignored - never committed):
```json
{
  "client_id":     "<your client id>",
  "client_secret": "<your client secret>",
  "redirect_uri":  "http://localhost:8080/",
  "base_url":      "https://sandbox-api.dexcom.com"
}
```
Switch `base_url` to the production host once Individual access is approved.

## 4. Run the probe
```
py -X utf8 scripts/dexcom_api_probe.py 2026-05-10 2026-05-16
```
- It prints an authorize URL (also opens your browser). Log in, authorize, then paste
  the redirected `http://localhost:8080/?code=...` URL back into the prompt.
- Tokens cache at `~/.dexcom_api/tokens.json` (refreshed automatically after).
- Output: a sample raw record (real field names), the event-type counts, and the
  insulin events (basal = `longActing`, bolus = `fastActing`).

## 5. Go / no-go
Compare the probe's insulin events against a Clarity day we already have - e.g.
`data/Clarity_..._2026-05-15_*.csv` rows where column 3 is `Insulin` and column 4 is
`Lang` (basal) or `Hurtig` (bolus):
- **Timestamps + units match, and history reaches back to ~2025-04** -> GO. Proceed to
  build `dexcom_api_fetch.py` + `dexcom_api_loader.py`.
- **Sparse / short history** -> NO-GO. Fall back to semi-manual Clarity export (the
  `clarity_coverage.py` gap engine already lists exactly which days to export by hand).
