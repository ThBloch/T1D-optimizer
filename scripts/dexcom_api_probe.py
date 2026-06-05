"""Phase 0 probe for the Dexcom Developer API v3 /events endpoint (E8).

Throwaway validation tool: confirms the official Dexcom API returns Thomas's
manually-logged insulin (basal = longActing, bolus = fastActing) BEFORE we build
the full integration. Compare its output against a known Clarity CSV day.

NOT part of the production path. Once validated, dexcom_api_fetch.py supersedes it.

Setup: see docs/dexcom-api-setup.md. Requires dexcom_api_creds.json (gitignored) at
the project root with: client_id, client_secret, redirect_uri, base_url.

Run:
    py -X utf8 scripts/dexcom_api_probe.py 2026-05-10 2026-05-16
"""
import sys, json, webbrowser
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CREDS_FILE   = PROJECT_ROOT / 'dexcom_api_creds.json'
TOKEN_CACHE  = Path.home() / '.dexcom_api' / 'tokens.json'


def _load_creds():
    if not CREDS_FILE.exists():
        sys.exit(f'Missing {CREDS_FILE}. See docs/dexcom-api-setup.md.')
    return json.loads(CREDS_FILE.read_text(encoding='utf-8'))


def _save_tokens(tok):
    TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_CACHE.write_text(json.dumps(tok, indent=2), encoding='utf-8')


def _load_tokens():
    if TOKEN_CACHE.exists():
        return json.loads(TOKEN_CACHE.read_text(encoding='utf-8'))
    return None


def _authorize(creds):
    """One-time auth-code flow. Paste-the-code - no local redirect server."""
    params = {
        'client_id':     creds['client_id'],
        'redirect_uri':  creds['redirect_uri'],
        'response_type': 'code',
        'scope':         'offline_access',   # the only scope Dexcom supports
        'state':         'probe',
    }
    url = f"{creds['base_url']}/v3/oauth2/login?{urlencode(params)}"
    print('1. Open this URL, log in, and authorize:')
    print(f'   {url}')
    try:
        webbrowser.open(url)
    except Exception:
        pass
    print(f"2. The browser redirects to {creds['redirect_uri']}?code=...  "
          f"(the page itself will not load - that is fine).")
    pasted = input('3. Paste the full redirected URL (or just the code): ').strip()
    code = pasted
    if 'code=' in pasted:
        code = parse_qs(urlparse(pasted).query).get('code', [pasted])[0]
    return _token_request(creds, {
        'code':         code,
        'grant_type':   'authorization_code',
        'redirect_uri': creds['redirect_uri'],
    })


def _refresh(creds, tok):
    return _token_request(creds, {
        'refresh_token': tok['refresh_token'],
        'grant_type':    'refresh_token',
    })


def _token_request(creds, extra):
    data = {'client_id': creds['client_id'], 'client_secret': creds['client_secret']}
    data.update(extra)
    resp = requests.post(f"{creds['base_url']}/v3/oauth2/token", data=data)
    resp.raise_for_status()
    tok = resp.json()
    _save_tokens(tok)
    return tok


def _get_events(creds, token, start, end):
    # v3 dates are ISO without timezone, e.g. 2026-05-10T00:00:00
    params = {'startDate': f'{start}T00:00:00', 'endDate': f'{end}T23:59:59'}
    resp = requests.get(
        f"{creds['base_url']}/v3/users/self/events?{urlencode(params)}",
        headers={'Authorization': f"Bearer {token}"},
    )
    resp.raise_for_status()
    return resp.json()


def main():
    if len(sys.argv) != 3:
        sys.exit('Usage: dexcom_api_probe.py <start YYYY-MM-DD> <end YYYY-MM-DD>')
    start, end = sys.argv[1], sys.argv[2]
    creds = _load_creds()
    tok = _load_tokens() or _authorize(creds)

    try:
        data = _get_events(creds, tok['access_token'], start, end)
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 401:
            tok = _refresh(creds, tok)
            data = _get_events(creds, tok['access_token'], start, end)
        else:
            raise

    records = data.get('records') or data.get('events') or []
    print(f'\n{len(records)} event record(s) for {start}..{end}')

    if records:
        print('\nSample raw record (confirm the real field names):')
        print(json.dumps(records[0], indent=2))

    types = {}
    for r in records:
        et = r.get('eventType')
        types[et] = types.get(et, 0) + 1
    print(f'\nEvent types seen: {types}')

    print('\nInsulin events (expect basal=longActing, bolus=fastActing):')
    insulin = [r for r in records if r.get('eventType') == 'insulin']
    for r in sorted(insulin, key=lambda r: r.get('systemTime') or ''):
        print(f"  {r.get('displayTime')}  {str(r.get('eventSubType')):<11} "
              f"{r.get('value')} {r.get('unit')}")
    if not insulin:
        print('  (none - check eventType naming in the sample record above)')


if __name__ == '__main__':
    main()
