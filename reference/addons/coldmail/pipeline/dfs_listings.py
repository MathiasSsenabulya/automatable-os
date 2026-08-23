#!/usr/bin/env python3
"""dfs_listings.py — die Leistungsliste und die Attribute aus DataForSEO nachziehen.

DER ANLASS IST EIN FEHLER, KEIN WUNSCH. `gbp-services` behauptet "your reviews keep saying
X and Y, but your profile mentions neither" und prueft dafuer nur die KATEGORIEN -- die
Leistungs-Sektion des Profils liefert Apify gar nicht. An sechs Bedford-Betrieben gemessen
waren 2 der 6 Behauptungen falsch: die Leistung stand sehr wohl drin. Der Befund feuert bei
63% aller Leads, also traegt rund jede fuenfte Mail eine Aussage, die der Empfaenger mit
einem Blick auf sein eigenes Profil widerlegt.

WARUM DIE BILLIGE DATENBANK REICHT: business_listings bedient aus DataForSEOs Crawl-Bestand.

  ⚠️ KORREKTUR 23.08.2026: hier stand "im Median 28 Tage alt". Nachgemessen an 246
  neuseelaendischen Schluesseldiensten sind es **110 Tage im Median**, der aelteste
  Datensatz 1.074 Tage. Nur 23 von 246 waren juenger als ein Monat. Woher die 28 kamen,
  ist nicht mehr nachvollziehbar -- moeglicherweise aus einer UK-Stichprobe, moeglicherweise
  geschaetzt. Am Schluss unten aendert das nichts (traege Felder bleiben traege), aber es
  ist der Unterschied zwischen "fast frisch" und "ein Vierteljahr alt", und bei
  Bewertungszahlen ist das der Unterschied zwischen einem Argument und einem Fehler.
Gemessen ueber 540 Leads: bei den TRAEGEN Feldern stimmt das mit unserem frischen Apify-
Scrape fast perfekt ueberein -- Oeffnungszeiten 0,0% Abweichung, beansprucht 0,4%,
Kategorien 2,0%. Nur Bewertungen (16,5%) und Fotos (16,1%) laufen auseinander, und die
holen wir ohnehin aus Apify. Eine Leistungsliste traegt niemand woechentlich nach.
$0.00037 je Betrieb gegen $0.0054 ueber my_business_info/live -- 14x billiger fuer Felder,
bei denen Frische nichts aendert.

Geschrieben wird nach `raw_dataforseo` (existierte, war bei allen 3.593 leer).

  dfs_listings.py --niche locksmith [--apply] [--limit-calls N]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import deeper_pull as dp
from dedupe_leads import _supabase

MAX_TREFFER = 1000        # was ein Aufruf hoechstens zurueckgibt
MIN_RADIUS = 3            # darunter lohnt kein weiteres Teilen


def api(payload: list) -> dict:
    req = urllib.request.Request(
        "https://api.dataforseo.com/v3/business_data/business_listings/search/live",
        data=json.dumps(payload).encode(),
        headers={"Authorization": "Basic " + dp._auth(), "Content-Type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=180))
    except urllib.error.HTTPError as e:
        print(f"    HTTP {e.code}: {(e.read() or b'').decode()[:160]}", flush=True)
    except Exception as e:
        print(f"    {type(e).__name__}: {str(e)[:110]}", flush=True)
    return {}


def kreis(niche: str, lat: float, lng: float, radius: float, treffer: dict, budget: list):
    """Ein Umkreis. Ist er voll, wird er geviertelt -- sonst fehlen uns genau die
    dichten Gegenden, in denen die meisten Leads sitzen."""
    if budget[0] <= 0:
        return
    budget[0] -= 1
    r = api([{"categories": [niche], "location_coordinate": f"{lat},{lng},{radius:.0f}",
              "limit": MAX_TREFFER}])
    res = ((r.get("tasks") or [{}])[0].get("result") or [{}])[0]
    items = res.get("items") or []
    gesamt = res.get("total_count") or 0
    for it in items:
        if it.get("place_id"):
            treffer[it["place_id"]] = it
    voll = len(items) >= MAX_TREFFER and gesamt > len(items)
    print(f"    {lat:.2f},{lng:.2f} r={radius:.0f}km -> {len(items)} von {gesamt}"
          f"{'  VOLL, teile' if voll else ''}", flush=True)
    if voll and radius > MIN_RADIUS:
        h = radius / 2
        d = h / 111.0                       # grob: 1 Grad ~ 111 km
        for dlat, dlng in ((d, d), (d, -d), (-d, d), (-d, -d)):
            kreis(niche, lat + dlat, lng + dlng / max(math.cos(math.radians(lat)), 0.1),
                  h, treffer, budget)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--niche", default="locksmith")
    ap.add_argument("--apply", action="store_true", help="wirklich schreiben")
    ap.add_argument("--limit-calls", type=int, default=60, help="Deckel gegen Ausreisser")
    a = ap.parse_args()

    url, key = _supabase()
    hdr = {"apikey": key, "Authorization": f"Bearer {key}"}
    leads, off = [], 0
    while True:
        q = (f"{url}/rest/v1/industry_operators?select=place_id,name,region,lat,lng"
             f"&niche=eq.{urllib.parse.quote(a.niche)}&pipeline_status=neq.disqualified"
             f"&lat=not.is.null&order=place_id&limit=1000&offset={off}")
        seite = json.load(urllib.request.urlopen(
            urllib.request.Request(q, headers=hdr), timeout=90))
        leads += seite
        off += 1000
        if len(seite) < 1000:
            break
    print(f"{len(leads)} Leads mit Koordinaten\n")

    # Je Region ein Kreis um den Schwerpunkt, gross genug fuer den entferntesten Lead.
    nach_region = {}
    for x in leads:
        nach_region.setdefault(x["region"], []).append(x)
    treffer, budget = {}, [a.limit_calls]
    for reg in sorted(nach_region, key=lambda r: -len(nach_region[r])):
        g = nach_region[reg]
        lat = sum(x["lat"] for x in g) / len(g)
        lng = sum(x["lng"] for x in g) / len(g)
        weit = max(math.hypot((x["lat"] - lat) * 111,
                              (x["lng"] - lng) * 111 * math.cos(math.radians(lat)))
                   for x in g)
        print(f"  {reg} ({len(g)} Leads)", flush=True)
        kreis(a.niche, lat, lng, max(weit + 5, 10), treffer, budget)
        if budget[0] <= 0:
            print("  [Aufruf-Deckel erreicht]", flush=True)
            break

    unsere = {x["place_id"] for x in leads}
    passend = {p: it for p, it in treffer.items() if p in unsere}
    mit_dienst = sum(1 for it in passend.values() if it.get("services"))
    print(f"\n{len(treffer)} Betriebe geholt, davon {len(passend)} unsere "
          f"({len(passend)/len(leads)*100:.0f}%), {mit_dienst} mit Leistungsliste")

    if not a.apply:
        print("[dry-run] mit --apply schreiben")
        return 0
    n = 0
    for pid, it in passend.items():
        nutz = {"services": [s.get("title") for s in (it.get("services") or [])
                             if s.get("title")],
                "attributes": it.get("attributes") or {},
                "place_topics": it.get("place_topics") or {},
                "stand": it.get("last_updated_time")}
        q = (f"{url}/rest/v1/industry_operators?place_id=eq."
             f"{urllib.parse.quote(pid, safe='')}")
        req = urllib.request.Request(q, data=json.dumps({"raw_dataforseo": nutz}).encode(),
                                     method="PATCH",
                                     headers={**hdr, "Content-Type": "application/json",
                                              "Prefer": "return=minimal"})
        try:
            urllib.request.urlopen(req, timeout=30).read()
            n += 1
        except urllib.error.HTTPError as e:
            print(f"  {pid}: {e.code} {(e.read() or b'').decode()[:120]}")
    print(f"geschrieben: {n} Zeilen nach raw_dataforseo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
