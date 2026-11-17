#!/usr/bin/env python3
"""Copy Google Search Console numbers into Supabase for the admin page.

Run by .github/workflows/search-stats.yml once a day. Needs two GitHub secrets:
  GSC_SERVICE_ACCOUNT  - the JSON key of the read-only Google "robot" account
  GSC_SYNC_TOKEN       - the token created by search-console-setup.sql
                         (Supabase: select value from private.settings where key = 'gsc_sync_token')
If either is missing the script explains and exits without failing the job.
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.environ.get("GSC_SITE", "sc-domain:ziyaanelite.co.ke")
DAYS = int(os.environ.get("GSC_DAYS", "60"))


def config():
    txt = open(os.path.join(ROOT, "config.js"), encoding="utf-8").read()
    get = lambda k: (re.search(k + r"\s*:\s*['\"]([^'\"]*)['\"]", txt) or [None, ""])[1]
    return get("supabaseUrl").rstrip("/"), get("supabaseAnonKey")


def main():
    key_json = os.environ.get("GSC_SERVICE_ACCOUNT", "").strip()
    token = os.environ.get("GSC_SYNC_TOKEN", "").strip()
    if not key_json or not token:
        print("Search Console sync is not set up yet (secrets GSC_SERVICE_ACCOUNT / GSC_SYNC_TOKEN missing) - skipping.")
        return 0

    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession

    creds = service_account.Credentials.from_service_account_info(
        json.loads(key_json), scopes=["https://www.googleapis.com/auth/webmasters.readonly"])
    http = AuthorizedSession(creds)
    api = "https://searchconsole.googleapis.com/webmasters/v3/sites/%s/searchAnalytics/query" % urllib.parse.quote(SITE, safe="")

    end = dt.date.today()
    start = end - dt.timedelta(days=DAYS)

    def query(dims):
        rows, start_row = [], 0
        while True:
            r = http.post(api, json={"startDate": start.isoformat(), "endDate": end.isoformat(), "dimensions": dims,
                                     "rowLimit": 25000, "startRow": start_row, "dataState": "all"}, timeout=60)
            if r.status_code != 200:
                raise SystemExit("Google Search Console error %s: %s" % (r.status_code, r.text[:400]))
            got = r.json().get("rows", [])
            rows += got
            if len(got) < 25000:
                return rows
            start_row += 25000

    daily = [{"day": r["keys"][0], "clicks": int(r["clicks"]), "impressions": int(r["impressions"]),
              "position": round(r["position"], 2)} for r in query(["date"])]

    host = re.compile(r"^https?://[^/]+")
    terms = []
    for kind in ("query", "page", "country", "device"):
        for r in query(["date", kind]):
            name = r["keys"][1]
            if kind == "page":
                name = host.sub("", name) or "/"
            elif kind == "device":
                name = name.lower()
            terms.append({"day": r["keys"][0], "kind": kind, "name": name[:300], "clicks": int(r["clicks"]),
                          "impressions": int(r["impressions"]), "position": round(r["position"], 2)})

    print("Google returned %d days and %d breakdown rows (%s to %s)." % (len(daily), len(terms), start, end))
    if not daily:
        print("No search data yet - Google usually needs 2-3 days after verification.")
        return 0

    url, anon = config()
    body = json.dumps({"p_token": token, "p_daily": daily, "p_terms": terms}).encode()
    req = urllib.request.Request(url + "/rest/v1/rpc/gsc_ingest", data=body, method="POST", headers={
        "apikey": anon, "Authorization": "Bearer " + anon, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            print("Saved to Supabase:", resp.read().decode()[:300])
    except urllib.error.HTTPError as e:
        raise SystemExit("Supabase error %s: %s" % (e.code, e.read().decode()[:400]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
