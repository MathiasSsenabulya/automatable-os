#!/usr/bin/env python3
"""build_regions.py — build regions/<C>.json, the region list --all-regions loops over.

WHY THIS EXISTS AT ALL
  seo_scrape_adaptive.py scrapes one region at a time and lets the actor grid that polygon
  itself. So a country is only as scrapeable as its region list is sensible. Germany at
  Bundesland level and the UK at county level were hand-checked and work. Nothing else had
  a list, and the old version of this script was not even shipped with the add-on -- the
  scraper pointed at a file that did not exist.

THE PART THAT MATTERS FOR BIG COUNTRIES
  The old version emitted regions in alphabetical order, which is fine for 16 Bundeslaender
  and useless for the United States. Alabama first, and the scrape is 40 runs deep before
  it reaches Los Angeles.

  Measured against GeoNames city population (23.08.2026):

      United States   954 counties -- 79 of them hold 60% of the urban population
      Australia       143 counties --  5 of them hold 60%
      United Kingdom  174 counties -- 32 of them hold 60%
      Canada          119 counties -- 11 of them hold 60%

  So the level alone is the wrong question. Australia's eight states are not too coarse,
  they are nearly empty: gridding New South Wales means gridding the outback to reach
  Sydney. The United States is the opposite -- 50 states too coarse, 3,000 counties too
  many, 79 about right.

  Every region therefore carries `pop` and `cum` (the running share of urban population up
  to and including it), sorted biggest first. `--coverage 0.6` then means "the regions that
  together hold 60% of the market", and the scrape spends its first dollars where the
  businesses are.

  `pop` is the population of GeoNames cities over 15,000 in that region, NOT its total
  population. For finding businesses that is the better measure anyway -- but it is a
  different number from the one on Wikipedia, and calling it "population" would be a lie.

WHEN A REGION HAS NO ADMIN2
  GeoNames leaves admin2 blank for some of the densest places on earth: New York City,
  Sydney, greater Brisbane. Those fall back to the name of their largest city with
  level='city', which is what the actor resolves best anyway.

WHAT THIS CANNOT DECIDE FOR YOU
  Whether the actor resolves a given name. GeoNames writes "City and Borough of
  Birmingham"; Google Maps wants "West Midlands". That is exactly why regions/UK.json is
  curated rather than generated. The scraper's level fallback (state -> county -> city)
  fails validation at $0, so a wrong name costs nothing but a retry -- run --dry-run and
  then a single region before committing to a whole country.

USAGE
  python3 build_regions.py US --level county
  python3 build_regions.py AU --level county --min-pop 30000
  python3 build_regions.py US --level state           # coarse, for a small test
  python3 build_regions.py --list                     # what maerkte.json says is worth doing

Source: GeoNames (CC BY 4.0), downloaded on first run and cached beside this script.
"""
import argparse
import collections
import io
import json
import os
import sys
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, '.geonames')
BASE = 'https://download.geonames.org/export/dump/'

# GeoNames writes English exonyms; Google Maps and the actor want the local name.
LOCAL = {
    'DE': {'Bavaria': 'Bayern', 'North Rhine-Westphalia': 'Nordrhein-Westfalen',
           'Lower Saxony': 'Niedersachsen', 'Hesse': 'Hessen', 'Saxony': 'Sachsen',
           'Thuringia': 'Thüringen', 'Saxony-Anhalt': 'Sachsen-Anhalt',
           'Baden-Wurttemberg': 'Baden-Württemberg', 'State of Berlin': 'Berlin',
           'Rhineland-Palatinate': 'Rheinland-Pfalz', 'Mecklenburg-Vorpommern':
           'Mecklenburg-Vorpommern'},
}

# ISO country code -> (actor countryCode, language, timezone for the SERP step)
LAENDER = {
    'UK': ('gb', 'en', 'Europe/London', 'United Kingdom'),
    'US': ('us', 'en', 'America/New_York', 'United States'),
    'IE': ('ie', 'en', 'Europe/Dublin', 'Ireland'),
    'AU': ('au', 'en', 'Australia/Sydney', 'Australia'),
    'NZ': ('nz', 'en', 'Pacific/Auckland', 'New Zealand'),
    'SG': ('sg', 'en', 'Asia/Singapore', 'Singapore'),
    'HK': ('hk', 'en', 'Asia/Hong_Kong', 'Hong Kong'),
    'FR': ('fr', 'fr', 'Europe/Paris', 'France'),
    'NL': ('nl', 'nl', 'Europe/Amsterdam', 'Netherlands'),
    'DE': ('de', 'de', 'Europe/Berlin', 'Germany'),
    'CA': ('ca', 'en', 'America/Toronto', 'Canada'),
    'ZA': ('za', 'en', 'Africa/Johannesburg', 'South Africa'),
    'SE': ('se', 'sv', 'Europe/Stockholm', 'Sweden'),
    'EE': ('ee', 'et', 'Europe/Tallinn', 'Estonia'),
    'NO': ('no', 'no', 'Europe/Oslo', 'Norway'),
    'FI': ('fi', 'fi', 'Europe/Helsinki', 'Finland'),
}

# GeoNames uses GB, the pipeline says UK; same for a couple of others.
GEO_CC = {'UK': 'GB'}

# Ein Stadtstaat wird nicht aufgeteilt: seine Bezirke ueberlappen mit der Stadt selbst,
# GeoNames fuehrt beide, und ein einziger Lauf deckt ohnehin das ganze Gebiet ab.
STADTSTAATEN = {'SG', 'HK'}

# Groesster Lauf, der nachweislich vollstaendig zurueckkam: Greater London, 1.359 Treffer
# fuer $9.51 (UK-Schluesseldienstlauf, 13.06.2026). Bei rund 87 Treffern je Million
# Stadtbevoelkerung entspricht das etwa 15 Millionen. Darueber wird geteilt -- nicht weil
# ein Deckel bekannt waere, sondern weil er unbekannt ist.
MAX_POP = 15_000_000


def hole(name, zipname=None):
    """Download a GeoNames table once, cache it beside this script."""
    ziel = os.path.join(CACHE, name)
    if os.path.exists(ziel):
        return ziel
    os.makedirs(CACHE, exist_ok=True)
    url = BASE + (zipname or name)
    print(f"  [geonames] {url}", file=sys.stderr)
    roh = urllib.request.urlopen(url, timeout=120).read()
    if zipname:
        with zipfile.ZipFile(io.BytesIO(roh)) as z:
            roh = z.read(name)
    open(ziel, 'wb').write(roh)
    return ziel


def admin_namen(stufe):
    """code -> name, for admin1CodesASCII.txt or admin2Codes.txt."""
    datei = 'admin1CodesASCII.txt' if stufe == 1 else 'admin2Codes.txt'
    aus = {}
    for zeile in open(hole(datei), encoding='utf-8'):
        teile = zeile.rstrip('\n').split('\t')
        if len(teile) >= 2:
            aus[teile[0]] = teile[1]
    return aus


def staedte(cc):
    """Every GeoNames city over 15,000 in this country: (admin1, admin2, name, pop).

    PPLX is excluded, and that exclusion is load-bearing: it means "section of a populated
    place", so GeoNames lists Hong Kong at 7.4m AND Kowloon at 2.2m AND New Territories at
    4.0m -- the same people counted three times. Summed unfiltered, Hong Kong came out at
    14.8m against a real 7.5m, and Johannesburg at 12.6m against 6m. The ranking mostly
    survived that, the numbers did not.
    """
    pfad = hole('cities15000.txt', 'cities15000.zip')
    aus = []
    for zeile in open(pfad, encoding='utf-8'):
        t = zeile.split('\t')
        if len(t) > 14 and t[8] == cc and t[7] != 'PPLX':
            aus.append((t[10], t[11], t[1], int(t[14] or 0)))
    return aus


def buendeln(orte, geo_cc, stufe):
    """Cities grouped by admin1 (stufe=1) or admin2 (stufe=2), with the biggest city kept."""
    topf = collections.defaultdict(lambda: {'pop': 0, 'groesster': ('', 0), 'a1': ''})
    for a1, a2, ort, pop in orte:
        schluessel = f"{geo_cc}.{a1}" + (f".{a2}" if stufe == 2 else "")
        e = topf[schluessel]
        e['pop'] += pop
        e['a1'] = f"{geo_cc}.{a1}"
        if pop > e['groesster'][1]:
            e['groesster'] = (ort, pop)
    return topf


def benennen(schluessel, eintrag, namen, land, ebene):
    """The name the actor gets, and the level to ask for it at."""
    name = namen.get(schluessel, '')
    # An empty admin code ('US.NY.', 'AU.02.') has no entry -- GeoNames leaves admin2 blank
    # for some of the densest places there are. Fall back to the biggest city, which is what
    # the actor resolves best anyway: 'New York City', 'Sydney'.
    if not name or schluessel.endswith('.'):
        return eintrag['groesster'][0], 'city'
    return LOCAL.get(land, {}).get(name, name), ebene


def bauen(land, stufe, min_pop, max_pop, ueberschreiben):
    if land not in LAENDER:
        sys.exit(f"[fatal] {land} unbekannt. Bekannt: {', '.join(sorted(LAENDER))}")
    cc, sprache, tz, voller_name = LAENDER[land]
    geo_cc = GEO_CC.get(land, land)
    orte = staedte(geo_cc)
    if not orte:
        sys.exit(f"[fatal] GeoNames kennt keine Staedte >15k fuer {geo_cc}")

    # Ein Stadtstaat hat keine sinnvolle Untergliederung: die Bezirke ueberlappen mit der
    # Stadt, und ein Lauf deckt ohnehin alles ab. Aufteilen hiesse dieselben Betriebe
    # mehrfach bezahlen.
    if land in STADTSTAATEN:
        regionen = [{'name': voller_name, 'level': 'city',
                     'pop': max(p for *_, p in orte)}]
        stufe_txt = 'city-state, single run'
    elif stufe == 0:
        # ADAPTIV (Standard): so grob wie moeglich, so fein wie noetig.
        #
        # Das ist die Antwort auf "ein ganzes Land durchscrapen". Ein Staat als eine Region
        # ist der bessere Zuschnitt, wo er durchgeht: weniger Laeufe, und die Kleinstaedte
        # zwischen den Ballungsraeumen fallen nicht durchs Raster. Western Australia hat
        # 2,8 Mio Einwohner, davon 2,4 Mio in Perth -- der Staat KOSTET fast nichts mehr als
        # die Stadt, weil Apify nach Treffern abrechnet (~$0.007, aus dem UK-Lauf) und nicht
        # nach Flaeche. Leeres Raster ist langsam, nicht teuer.
        #
        # Die Grenze ist nicht die Flaeche, sondern was ein Lauf noch vollstaendig
        # zurueckgibt. Groesster gemessener Lauf: Greater London, 1.359 Treffer fuer $9.51,
        # sauber. Darueber ist es unbekannt -- also wird ein Staat, dessen Stadtbevoelkerung
        # ueber --max-pop liegt, durch seine Countys ersetzt. Kalifornien faellt darunter,
        # Wyoming nicht.
        n1, n2 = admin_namen(1), admin_namen(2)
        t1, t2 = buendeln(orte, geo_cc, 1), buendeln(orte, geo_cc, 2)
        regionen, geteilt = [], []
        for s1, e1 in t1.items():
            if e1['pop'] <= max_pop:
                if e1['pop'] >= min_pop:
                    name, lvl = benennen(s1, e1, n1, land, 'state')
                    regionen.append({'name': name, 'level': lvl, 'pop': e1['pop']})
                continue
            geteilt.append((n1.get(s1, s1), e1['pop']))
            for s2, e2 in t2.items():
                if e2['a1'] == s1 and e2['pop'] >= min_pop:
                    name, lvl = benennen(s2, e2, n2, land, 'county')
                    regionen.append({'name': name, 'level': lvl, 'pop': e2['pop']})
        stufe_txt = f'adaptive: states, split into counties above {max_pop:,} urban residents'
        if geteilt:
            print(f"  geteilt (zu gross fuer einen Lauf): " +
                  ', '.join(f"{n} ({p//1000}k)" for n, p in sorted(geteilt, key=lambda x: -x[1])))
    else:
        ebene = 'state' if stufe == 1 else 'county'
        namen = admin_namen(stufe)
        regionen = []
        for schluessel, e in buendeln(orte, geo_cc, stufe).items():
            if e['pop'] < min_pop:
                continue
            name, lvl = benennen(schluessel, e, namen, land, ebene)
            regionen.append({'name': name, 'level': lvl, 'pop': e['pop']})
        stufe_txt = f'GeoNames admin{stufe}'

    regionen.sort(key=lambda r: -r['pop'])
    ebene = regionen[0]['level'] if regionen else 'county'
    gesamt = sum(r['pop'] for r in regionen) or 1
    laufend = 0
    for r in regionen:
        laufend += r['pop']
        r['cum'] = round(laufend / gesamt, 4)

    aus = {
        'country': voller_name, 'countryCode': cc, 'language': sprache, 'timezone': tz,
        'level': ebene,
        '_source': f'{stufe_txt}; GeoNames + cities15000, sorted by urban population',
        '_pop_note': 'pop = residents of GeoNames cities over 15,000 in that region, '
                     'not its total population. cum = running share of that, biggest first.',
        '_urban_pop': gesamt,
        'regions': regionen,
    }
    os.makedirs(os.path.join(HERE, 'regions'), exist_ok=True)
    pfad = os.path.join(HERE, 'regions', f'{land}.json')
    # Eine von Hand geprüfte Liste ist mehr wert als eine generierte, und regions/UK.json
    # ist genau deshalb kuratiert: GeoNames schreibt "City and Borough of Birmingham", der
    # Actor braucht "West Midlands". Ohne diese Sperre nimmt ein unbedachter Lauf die
    # Arbeit zurück, und der Scrape wird still schlechter statt lauter kaputt.
    if os.path.exists(pfad) and not ueberschreiben:
        alt = json.load(open(pfad, encoding='utf-8'))
        if 'curated' in (alt.get('_source') or '').lower():
            sys.exit(f"[stop] regions/{land}.json ist kuratiert:\n"
                     f"       {alt.get('_source')}\n"
                     f"       Ueberschreiben mit --force, aber pruefe vorher, ob der Actor "
                     f"die generierten Namen aufloest.")
    json.dump(aus, open(pfad, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    print(f"{land}: {len(regionen)} Regionen ({ebene}) -> regions/{land}.json")
    for anteil in (0.5, 0.6, 0.8):
        n = next((i for i, r in enumerate(regionen, 1) if r['cum'] >= anteil), len(regionen))
        print(f"    {int(anteil*100)}% des Marktes in {n} Regionen")
    print("    groesste:", ', '.join(f"{r['name']} ({r['pop']//1000}k)" for r in regionen[:5]))
    return pfad


def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('country', nargs='?', help='UK, US, AU, ... (see --list)')
    p.add_argument('--level', choices=['adaptive', 'state', 'county'], default='adaptive',
                   help='adaptive (default): states, and only the states too big for one '
                        'run are split into counties. state / county force one level '
                        'throughout -- state for a cheap coarse test, county to prioritise '
                        'dense markets first.')
    p.add_argument('--min-pop', type=int, default=15000,
                   help='drop regions below this urban population (default 15000)')
    p.add_argument('--max-pop', type=int, default=MAX_POP,
                   help=f'split a state above this urban population (default {MAX_POP:,}, '
                        f'derived from the biggest run measured complete)')
    p.add_argument('--force', action='store_true',
                   help='overwrite a curated regions file (UK is curated -- check first '
                        'that the actor resolves the generated names)')
    p.add_argument('--list', action='store_true', help='which countries maerkte.json rates')
    a = p.parse_args()

    if a.list:
        markt = os.path.join(HERE, 'maerkte.json')
        if os.path.exists(markt):
            d = json.load(open(markt, encoding='utf-8'))
            zeichen = {'green': '●', 'amber': '◐', 'red': '○'}
            for l in d['countries']:
                da = '✓' if os.path.exists(os.path.join(HERE, l.get('region_file') or '')) else ' '
                print(f"  {da} {zeichen.get(l['light'], '?')} {l['code']:3} "
                      f"{l['regime']:26} {str(l['regions']):>4} regions   {l['name']}")
            print("\n  ✓ = region file present · ● lawful for B2B, opt-out · ◐ conditional "
                  "· ○ not recommended")
            print("  The legal column is desk research, not legal advice -- read the rule "
                  "and catch fields in maerkte.json before sending anywhere.")
        else:
            print("  " + ', '.join(sorted(LAENDER)))
        return
    if not a.country:
        p.error("country fehlt (oder --list)")
    stufe = {'adaptive': 0, 'state': 1, 'county': 2}[a.level]
    bauen(a.country.upper(), stufe, a.min_pop, a.max_pop, a.force)


if __name__ == '__main__':
    main()
