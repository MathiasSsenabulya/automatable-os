#!/usr/bin/env python3
"""pruefe_regionen.py — jeden Regionsnamen gegen OpenStreetMap pruefen, bevor er Geld kostet.

DAS PROBLEM, gemessen am 23.08.2026 an Neuseeland:

  Landlauf ueber das ganze Land          330 Treffer
  ueber die generierte Regionsliste       97 Treffer

Der Unterschied lag NICHT am Rastern, sondern an den Namen. "Auckland" scheiterte als
`county` ganz und lieferte als `city` 17 Betriebe fuer ein Drittel des Landes, weil eine
automatische Stadtgrenze am Stadtrand aufhoert. Eine generierte Liste ist also nicht
einfach schlechter, sie ist UNGEPRUEFT -- und ungeprueft heisst hier: man merkt es erst an
der Rechnung.

Umgekehrt: regions/UK.json ist von Hand geprueft, und darueber sind 4.746 Schluesseldienste
zusammengekommen. Das ist die hoechste Zahl, die dieses System je erreicht hat. Eine
geprueft Liste schlaegt alles andere.

WARUM DAS HIER NICHTS KOSTET
  Der Actor loest ein Gebiet ueber OpenStreetMap-Verwaltungsgrenzen auf -- deshalb steht in
  run_campaign.py ein DECOMPOSE-Block fuer englische Countys, die gar keine OSM-Grenze mehr
  haben. Dieselbe Datenbank ist oeffentlich ueber Nominatim abfragbar. Wir koennen also
  vorher wissen, ob ein Name auf eine Flaeche zeigt und auf welcher Verwaltungsebene, statt
  es fuer 0,007 $ je Treffer herauszufinden.

  Nominatim erlaubt eine Anfrage je Sekunde und verlangt einen ehrlichen User-Agent. Bei
  rund 700 Regionen ueber alle 15 Laender sind das etwa zwoelf Minuten. Kostenlos.

WAS ES PRUEFT
  1. Findet Nominatim den Namen im richtigen Land ueberhaupt?
  2. Ist der Treffer eine FLAECHE (Relation/Polygon) oder nur ein Punkt? Ein Punkt bedeutet
     fuer den Actor: keine Grenze zum Rastern.
  3. Welches admin_level hat er? Daraus folgt, ob der Actor ihn als `state`, `county` oder
     `city` nehmen muss -- und genau dieses Feld traegt seo_scrape_adaptive je Region.

WAS ES NICHT KANN
  Garantieren, dass der Actor denselben Treffer waehlt. Er nutzt OSM, aber wie er einen
  mehrdeutigen Namen aufloest, steht nirgends. Ein hier gruener Name ist deshalb ein
  begruendeter Kandidat und kein Beweis -- der Beweis bleibt ein Testlauf. Umgekehrt ist ein
  hier roter Name aber ziemlich sicher auch dort einer, und DAS ist der Wert: die Fehler
  vorher finden.

  python3 pruefe_regionen.py NZ            # ein Land
  python3 pruefe_regionen.py --alle        # alle mit Regionsdatei
  python3 pruefe_regionen.py NZ --schreiben  # Ergebnis in die Datei zurueckschreiben
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
NOMINATIM = "https://nominatim.openstreetmap.org/search"
# Nominatim verlangt einen echten Kontakt im User-Agent. Ohne den wird gesperrt.
UA = "coldmail-addon/1.0 (region name validation; +https://github.com/luka-commits/automatable-os)"

# OSM admin_level -> was der Actor als Feld erwartet. Die Grenzen sind Konvention, nicht
# Gesetz: level 4 ist in den meisten Laendern die erste Ebene unter dem Staat.
def ebene_zu_feld(level):
    if level is None:
        return None
    lvl = int(level)
    if lvl <= 4:
        return 'state'
    if lvl <= 6:
        return 'county'
    return 'city'


def frage(name, land_cc):
    """Ein Nominatim-Treffer, oder None. Beschraenkt auf das Land, Flaechen bevorzugt."""
    p = urllib.parse.urlencode({
        'q': name, 'countrycodes': land_cc.lower(), 'format': 'jsonv2',
        'limit': 5, 'polygon_geojson': 0, 'addressdetails': 0, 'extratags': 1,
    })
    req = urllib.request.Request(f"{NOMINATIM}?{p}", headers={'User-Agent': UA})
    try:
        treffer = json.load(urllib.request.urlopen(req, timeout=30))
    except Exception as e:
        return {'fehler': f"{type(e).__name__}: {str(e)[:60]}"}
    # Grenzen zuerst: nur die haben eine Flaeche, die der Actor rastern kann.
    #
    # `ceremonial` gehoert ausdruecklich dazu, und das ist keine Kleinigkeit: englische
    # Countys wie Essex fuehrt OSM als ceremonial statt administrative, und ein Filter nur
    # auf administrative meldete sie als "kein Polygon". Essex hat im echten Lauf 316
    # Betriebe geliefert -- die Pruefung war also strenger als die Wirklichkeit und haette
    # acht funktionierende UK-Regionen verdaechtigt.
    ARTEN = ('administrative', 'ceremonial')
    flaechen = [t for t in treffer
                if t.get('category') == 'boundary' and t.get('type') in ARTEN]
    if not flaechen:
        if not treffer:
            return None
        t = treffer[0]
        return {'gefunden': True, 'flaeche': False, 'typ': f"{t.get('category')}/{t.get('type')}",
                'name': t.get('display_name', '')[:60]}
    t = flaechen[0]
    lvl = (t.get('extratags') or {}).get('admin_level')
    return {'gefunden': True, 'flaeche': True, 'level': lvl, 'feld': ebene_zu_feld(lvl),
            'name': t.get('display_name', '')[:60]}


def pruefe_land(code, schreiben=False):
    pfad = os.path.join(HERE, 'regions', f'{code}.json')
    if not os.path.exists(pfad):
        print(f"[{code}] keine Regionsdatei")
        return None
    d = json.load(open(pfad, encoding='utf-8'))
    cc = d.get('countryCode', code)
    regionen = d['regions']
    print(f"\n=== {d.get('country', code)}: {len(regionen)} Regionen, "
          f"~{len(regionen)} Sekunden ===", flush=True)

    gut = schief = fehlt = 0
    for r in regionen:
        erg = frage(r['name'], cc)
        time.sleep(1.05)                      # Nominatims Rate-Limit, ehrlich eingehalten
        if erg is None:
            r['osm'] = 'nicht gefunden'
            fehlt += 1
            print(f"  ✗ {r['name'][:34]:36} nicht in OSM", flush=True)
        elif erg.get('fehler'):
            print(f"  ? {r['name'][:34]:36} {erg['fehler']}", flush=True)
        elif not erg['flaeche']:
            r['osm'] = f"kein Polygon ({erg['typ']})"
            fehlt += 1
            print(f"  ✗ {r['name'][:34]:36} nur ein Punkt: {erg['typ']}", flush=True)
        elif erg['feld'] is None:
            # Eine Flaeche ohne admin_level -- typisch fuer englische ceremonial counties.
            # Sie ist rasterbar, nur laesst sich die Ebene daraus nicht ableiten. Also
            # gilt sie als in Ordnung und die bestehende Ebene bleibt stehen. Frueher fiel
            # sie in den Zweig unten und haette mit --schreiben `level: None` eingetragen,
            # was die geprueft UK-Liste stillschweigend zerstoert haette.
            r['osm'] = "Flaeche ohne admin_level (ceremonial)"
            gut += 1
        else:
            soll, ist = r.get('level'), erg['feld']
            r['osm'] = f"admin_level {erg['level']}"
            if soll == ist:
                gut += 1
            else:
                schief += 1
                r['osm_level'] = ist
                print(f"  ! {r['name'][:34]:36} steht als '{soll}', OSM sagt '{ist}' "
                      f"(level {erg['level']})", flush=True)

    print(f"\n  {gut} passen · {schief} falsche Ebene · {fehlt} ohne Flaeche")
    if schief:
        print(f"  -> mit --schreiben wird die Ebene je Region korrigiert")
    if fehlt:
        print(f"  -> die {fehlt} ohne Flaeche kann der Actor nicht rastern; sie brauchen "
              f"einen anderen Namen oder fallen raus")

    if schreiben:
        for r in regionen:
            neu = r.pop('osm_level', None)
            # Nur ueberschreiben, wenn OSM tatsaechlich eine Ebene NENNT. Ein None hier
            # heisst "nicht ableitbar", nicht "keine Ebene" -- und eine geprueft Liste
            # darf daran nicht kaputtgehen.
            if neu:
                r['level'] = neu
        d['_geprueft'] = f"OSM-Namenspruefung, {gut} von {len(regionen)} passen"
        json.dump(d, open(pfad, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(f"  geschrieben -> regions/{code}.json")
    return {'code': code, 'gut': gut, 'schief': schief, 'fehlt': fehlt, 'gesamt': len(regionen)}


def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('country', nargs='?')
    p.add_argument('--alle', action='store_true', help='jedes Land mit Regionsdatei')
    p.add_argument('--schreiben', action='store_true',
                   help='korrigierte Ebene in die Regionsdatei zurueckschreiben')
    a = p.parse_args()

    if a.alle:
        codes = sorted(f[:-5] for f in os.listdir(os.path.join(HERE, 'regions'))
                       if f.endswith('.json'))
    elif a.country:
        codes = [a.country.upper()]
    else:
        p.error("Land angeben oder --alle")

    ergebnisse = [x for x in (pruefe_land(c, a.schreiben) for c in codes) if x]
    if len(ergebnisse) > 1:
        print(f"\n{'Land':6} {'gut':>5} {'Ebene falsch':>13} {'ohne Flaeche':>13}")
        for e in sorted(ergebnisse, key=lambda x: -(x['schief'] + x['fehlt'])):
            print(f"{e['code']:6} {e['gut']:>5} {e['schief']:>13} {e['fehlt']:>13}")


if __name__ == '__main__':
    main()
