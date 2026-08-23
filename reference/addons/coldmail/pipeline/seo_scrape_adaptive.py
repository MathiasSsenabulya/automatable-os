#!/usr/bin/env python3
"""seo_scrape_adaptive.py — full-coverage Google-Maps scrape at REGION level.

ONE input model: keyword + country/region in, all leads out. We scrape at the region
(state / county) level and let the compass actor's own grid do the work — no city list,
no per-city loop.

WHY REGION-LEVEL (verified live 2026-06-13):
  Google Maps caps a SINGLE map-screen at ~120 places, but ONLY when no location is set.
  Give the actor a location and it AUTO-GRIDS that polygon (cell by cell, deduped) and
  returns the whole market. A region polygon (Bundesland / county) covers the metro AND
  its surrounding towns/villages (Umland) in one run. Verified complete: Birmingham via
  county="West Midlands" returned 131/131 of a dedicated city scrape — region-grid misses
  nothing. Cheaper than looping cities, no cities list to maintain, covers villages too.
  Trade-off: ~10-33% of results come back city-less (loose attribution) -> recovered
  downstream by seo-enrich's city-recovery (city from the website/name).

  The admin level differs by country: DE Bundesland = `state`, UK region = `county`.
  --state auto-detects (tries state, then county; an invalid level fails validation at $0).

USAGE
  # a whole country in ONE run -- the actor splits it into subregions itself:
  seo_scrape_adaptive.py --keyword locksmith --country NZ --country-wide
  # a whole country by looping its region list, resumable region by region:
  seo_scrape_adaptive.py --keyword locksmith --country UK --all-regions
  # every emergency trade in maerkte.json, one country, one command:
  seo_scrape_adaptive.py --niches emergency --country AU --country-wide --cold-email
  # one region:
  seo_scrape_adaptive.py --keyword locksmith --country UK --state "West Midlands"
  # always --dry-run first for the plan.

  Adding a country = python3 build_regions.py <C>   (--list rates them legally too)
  Adding an industry = --keyword, or add it to maerkte.json and use --niches.
  Filter after with filter_niche.py.

WHICH MODE
  --country-wide is one call and does not depend on region names resolving, which is where
  a generated region list goes wrong (measured on NZ: 'Auckland' fails as a county, and as
  a city it returns a fraction of the metro because the actor's automatic city polygons
  exclude the agglomeration). It is all-or-nothing though: a failed run loses the lot.
  --all-regions saves after every region and resumes, which is what you want when a run is
  worth 40 dollars. Use it with a CURATED region list (UK is one); with a generated list,
  prefer --country-wide.

OUTPUT (output/<...>-<kw>/):
  raw.json       union of all regions, deduped by placeId  (-> filter_niche.py -> enrich)
  coverage.json  per-region counts + per-city rollup + city-less count
  meta.json      serp_locations + tz  (drop-in for the enrich step)
"""
import json, argparse, os, re, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ACTOR = "compass~crawler-google-places"
CC = {'UK': 'gb', 'US': 'us', 'DE': 'de', 'AU': 'au', 'CA': 'ca', 'IE': 'ie', 'NL': 'nl'}


def env(key, *alts):
    for line in open(os.path.expanduser('~/.config/credentials.env')):
        if '=' in line and not line.strip().startswith('#'):
            k, v = line.split('=', 1)
            if k.strip() in (key, *alts):
                return v.strip().strip('"')
    return None


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


def run_apify(body):
    tok = env('APIFY_TOKEN', 'APIFY_API_TOKEN')
    if not tok:
        sys.exit("[fatal] no APIFY_TOKEN / APIFY_API_TOKEN in ~/.config/credentials.env")
    r = urllib.request.Request(
        f'https://api.apify.com/v2/acts/{ACTOR}/runs?token={tok}',
        data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    run = json.load(urllib.request.urlopen(r, timeout=30))['data']
    rid, ds = run['id'], run['defaultDatasetId']
    cost = 0.0
    while True:
        time.sleep(15)
        d = json.load(urllib.request.urlopen(
            f'https://api.apify.com/v2/actor-runs/{rid}?token={tok}', timeout=30))['data']
        if d['status'] in ('SUCCEEDED', 'FAILED', 'TIMED-OUT', 'ABORTED'):
            cost = d.get('usageTotalUsd', 0) or 0
            break
    items = json.load(urllib.request.urlopen(
        f'https://api.apify.com/v2/datasets/{ds}/items?token={tok}&clean=true&format=json', timeout=300))
    return items, cost, d['status']


def scrape_region(kw, region, level_hint, cc, lang, keep_no_website, per_region, addons=None):
    """One region run with admin-level auto-fallback (state -> county). An invalid level
    fails validation at $0, so the fallback is free. Returns (items, cost, status, level)."""
    # 'city' is the last fallback for metropolitan boroughs that have no state/county admin
    # boundary in OSM (e.g. Merseyside's Liverpool/Wirral — abolished county council, level-8 only).
    levels = [level_hint] if level_hint else ['state', 'county', 'city']
    a = addons or {}
    items, cost, status = [], 0, 'FAILED'
    for level in levels:
        # 'country' is not an actor field: a whole country goes in through locationQuery,
        # which the actor splits into subregions itself (its own input schema says so, and
        # --country-wide is where that gets used).
        feld = 'locationQuery' if level == 'country' else level
        b = {'searchStringsArray': [kw], feld: region, 'countryCode': cc, 'language': lang,
             # Add-ons default OFF (cheap discovery run). Turn on per skills/scrape-gmaps/
             # references/actor-config.md — a cold-email scrape needs --details at minimum,
             # otherwise services/reviewsTags/peopleAlsoSearch come back empty and every mail
             # ends up saying the same thing (measured: 99% share the "no GBP description" gap).
             'scrapeContacts': bool(a.get('contacts')),
             'scrapePlaceDetailPage': bool(a.get('details')),
             'skipClosedPlaces': True,
             'includeWebResults': False, 'maxReviews': 0, 'maxImages': 0}
        if a.get('leads'):
            # owner name / title / LinkedIn -> the {{first_name}} the subject line wants
            b['maximumLeadsEnrichmentRecords'] = int(a['leads'])
            if a.get('verify_leads'):
                b['verifyLeadsEnrichmentEmails'] = True
        if not keep_no_website:
            b['website'] = 'withWebsite'          # default: email-channel only (no site = no email)
        if per_region and per_region > 0:
            b['maxCrawledPlacesPerSearch'] = per_region
        items, cost, status = run_apify(b)
        if status == 'SUCCEEDED':
            return items, cost, status, level
    return items, cost, status, None


def union_add(union, items):
    """Merge items into the placeId-keyed union; return count of net-new."""
    before = len(union)
    for it in items:
        pid = it.get('placeId') or it.get('placeUrl') or json.dumps(it, sort_keys=True)[:80]
        union.setdefault(pid, it)
    return len(union) - before


def finalize(run_dir, union, region_rows, kw, rgeo, country):
    """Write raw.json (union), coverage.json (per-region + per-city + city-less), meta.json."""
    from collections import Counter
    raw_path = os.path.join(run_dir, 'raw.json')
    json.dump(list(union.values()), open(raw_path, 'w'), ensure_ascii=False)
    towns = Counter((it.get('city') or '∅').strip() or '∅' for it in union.values())
    nocity = towns.get('∅', 0)
    cov = {'mode': 'region', 'keyword': kw, 'country': country,
           'total_unique': len(union), 'total_city_less': nocity,
           'total_cost': round(sum(r['cost'] for r in region_rows), 2),
           'regions': region_rows, 'by_city': dict(towns.most_common())}
    json.dump(cov, open(os.path.join(run_dir, 'coverage.json'), 'w'), ensure_ascii=False, indent=1)
    cn = rgeo.get('country', country)
    meta = {'keyword': kw, 'country': country, 'country_name': cn, 'timezone': rgeo.get('timezone', ''),
            'serp_locations': {c: f"{c},,{cn}" for c in towns if c != '∅'}}
    json.dump(meta, open(os.path.join(run_dir, 'meta.json'), 'w'), ensure_ascii=False, indent=1)
    return raw_path, nocity


def nischen_aufloesen(auswahl):
    """--niches all | emergency | slug,slug -> [(slug, search term), ...] from maerkte.json.

    The point of scraping a country is rarely one trade. maerkte.json already lists 20 with
    their Maps search terms and which of them are emergency work, so the list lives there
    rather than being retyped on the command line every time.
    """
    pfad = os.path.join(HERE, 'maerkte.json')
    if not os.path.exists(pfad):
        sys.exit("[fatal] maerkte.json fehlt -- ohne sie kennt --niches keine Branchen.")
    alle = json.load(open(pfad, encoding='utf-8'))['niches']
    if auswahl == 'all':
        gewaehlt = alle
    elif auswahl == 'emergency':
        gewaehlt = [n for n in alle if n.get('emergency')]
    else:
        wunsch = [s.strip() for s in auswahl.split(',') if s.strip()]
        bekannt = {n['slug']: n for n in alle}
        fehlt = [s for s in wunsch if s not in bekannt]
        if fehlt:
            sys.exit(f"[fatal] unbekannte Nische(n): {', '.join(fehlt)}\n"
                     f"        bekannt: {', '.join(sorted(bekannt))}")
        gewaehlt = [bekannt[s] for s in wunsch]
    return [(n['slug'], n['terms'][0]) for n in gewaehlt]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--keyword', help='the Maps search term / niche, e.g. "locksmith"')
    ap.add_argument('--niches', default='',
                    help='instead of --keyword: all | emergency | slug,slug -- the trades '
                         'from maerkte.json, scraped one after another into their own runs.')
    ap.add_argument('--country', required=True, help='matches regions/<C>.json, e.g. UK or DE')
    ap.add_argument('--country-wide', action='store_true',
                    help='ONE run for the whole country instead of looping regions. The actor '
                         'splits the country into subregions itself. Cheaper in wall-clock and '
                         'in calls, and it does not depend on the region names resolving -- but '
                         'a single failed run loses everything, where --all-regions resumes.')
    ap.add_argument('--all-regions', action='store_true', help='WHOLE COUNTRY: loop every region in regions/<C>.json, union all. Resumable (skips done regions; --force to redo).')
    ap.add_argument('--state', default='', help='ONE region (e.g. "Bayern", "West Midlands"). Auto-detects state vs county.')
    ap.add_argument('--region-level', default='', choices=['', 'state', 'county', 'city'], help='force the admin level for --state (default auto: state then county then city).')
    ap.add_argument('--per-region', type=int, default=0, help='maxCrawledPlacesPerSearch cap; 0 = scrape ALL (default)')
    ap.add_argument('--keep-no-website', action='store_true', help='KEEP no-website places (drops the withWebsite filter): the enrich website-finder recovers ~30%%, the rest become a phone/cold-call list. ~25%% more scrape cost.')
    ap.add_argument('--details', action='store_true', help='Add-on: scrapePlaceDetailPage. Services, GBP description, booking link, reviewsTags, peopleAlsoSearch. REQUIRED for a cold-email scrape (see references/actor-config.md).')
    ap.add_argument('--contacts', action='store_true', help='Add-on: scrapeContacts. Emails + socials from the business website, in the same run. Recommended for new niches (own recovery measured at 5%% on the leftovers).')
    ap.add_argument('--leads', type=int, default=0, metavar='N', help='Add-on: maximumLeadsEnrichmentRecords=N. Owner name, title, LinkedIn -> first_name for the subject line. 1 is usually enough.')
    ap.add_argument('--verify-leads', action='store_true', help='Add-on: verify enriched lead emails (only decisive results are billed). Skip while MillionVerifier credits last.')
    ap.add_argument('--cold-email', action='store_true', help='Preset for an outreach scrape: --details --contacts --leads 1.')
    ap.add_argument('--force', action='store_true', help='re-scrape regions already in coverage.json (default: skip = never re-pay)')
    ap.add_argument('--dry-run', action='store_true', help='show the plan, no Apify call')
    a = ap.parse_args()

    if not (a.all_regions or a.state or a.country_wide):
        sys.exit("[fatal] choose --country-wide (one run for the country), --all-regions "
                 "(loop the region list) or --state \"<region>\" (one region).")
    if bool(a.keyword) == bool(a.niches):
        sys.exit("[fatal] choose --keyword \"<term>\" or --niches all|emergency|<slug,slug>.")

    if a.cold_email:
        a.details, a.contacts = True, True
        a.leads = a.leads or 1
    addons = {'details': a.details, 'contacts': a.contacts,
              'leads': a.leads, 'verify_leads': a.verify_leads}
    on = [k for k, v in addons.items() if v]
    print(f"[addons] {' '.join(on) if on else 'none (cheap discovery run)'}")
    if not a.details:
        print("[addons] note: no --details -> services/reviewsTags/peopleAlsoSearch stay empty. "
              "Fine for discovery, NOT enough for a cold-email campaign.")
    # DE and other consent-required markets: scraping is fine, emailing is not (§7 UWG).
    if a.country.upper() in ('DE', 'AT', 'CH') and (a.contacts or a.cold_email):
        print(f"[legal] {a.country.upper()}: cold email needs prior opt-in (§7 UWG). "
              "Scrape is fine, but this list feeds a phone/post motion, not Instantly.")

    rfile = f'{HERE}/regions/{a.country}.json'
    if not os.path.exists(rfile):
        sys.exit(f"[fatal] no regions/{a.country}.json — build it:\n"
                 f"        python3 build_regions.py {a.country}\n"
                 f"        (python3 build_regions.py --list shows which countries are rated, "
                 f"and how each one stands legally)")
    rgeo = json.load(open(rfile))
    cc = rgeo.get('countryCode') or CC.get(a.country, '')
    lang = rgeo.get('language', 'en')
    country = rgeo.get('country', a.country)

    # Eine Nische oder viele -- der Rest laeuft je Nische identisch ab.
    nischen = ([(slug(a.keyword), a.keyword.strip().lower())] if a.keyword
               else nischen_aufloesen(a.niches))
    if len(nischen) > 1:
        print(f"[plan] {len(nischen)} Branchen ueber {country}: "
              f"{', '.join(k for _, k in nischen)}")
    for i, (_, kw) in enumerate(nischen, 1):
        if len(nischen) > 1:
            print(f"\n{'=' * 70}\n=== {i}/{len(nischen)}  {kw}\n{'=' * 70}")
        ein_durchlauf(a, kw, addons, rgeo, cc, lang, country)


def ein_durchlauf(a, kw, addons, rgeo, cc, lang, country):
    """One trade over one country, whichever of the three modes was chosen."""
    # ---- whole country in a single run ----
    if a.country_wide:
        run_dir = os.path.join(HERE, 'output', f"{a.country.lower()}-{slug(kw)}-countrywide")
        os.makedirs(run_dir, exist_ok=True)
        print(f"[plan] COUNTRY-WIDE '{country}' · '{kw}' · one run, the actor splits it itself")
        if a.dry_run:
            print("[dry-run] 1 run. No Apify call.")
            return
        items, cost, status, _ = scrape_region(kw, country, 'country', cc, lang,
                                               a.keep_no_website, a.per_region, addons)
        union = {}
        union_add(union, items)
        rows = [{'region': country, 'level': 'country', 'returned': len(items),
                 'net_new': len(union), 'cost': cost, 'status': status}]
        finalize(run_dir, union, rows, kw, rgeo, country)
        flag = '' if status == 'SUCCEEDED' else f'  ⚠️ {status}'
        print(f"\n=== COUNTRY-WIDE {country}: {len(union)} unique places | ${cost:.2f} ==={flag}")
        print(f"raw -> {os.path.join(run_dir, 'raw.json')}")
        print(f"NEXT: filter_niche.py {os.path.join(run_dir, 'raw.json')} --keyword {kw} "
              f"--terms \"<synonyms>\"")
        return

    # ---- one region ----
    if a.state and not a.all_regions:
        run_dir = os.path.join(HERE, 'output', f"{slug(a.state)}-region-{slug(kw)}")
        os.makedirs(run_dir, exist_ok=True)
        print(f"[plan] REGION '{a.state}' ({cc}) · '{kw}' · whole region incl. Umland · "
              f"level={'auto (state→county)' if not a.region_level else a.region_level}")
        if a.dry_run:
            print("[dry-run] no Apify call.")
            return
        items, cost, status, used = scrape_region(kw, a.state, a.region_level, cc, lang,
                                                  a.keep_no_website, a.per_region, addons)
        if status != 'SUCCEEDED':
            print(f"[fatal] '{a.state}' not found as state, county or city in {cc}. "
                  f"Validate: https://nominatim.openstreetmap.org/search?q={a.state}")
            return
        print(f"[region] admin level = '{used}'")
        union = {}
        net = union_add(union, items)
        rows = [{'region': a.state, 'level': used, 'returned': len(items),
                 'net_new': net, 'cost': cost, 'status': status}]
        raw_path, nocity = finalize(run_dir, union, rows, kw, rgeo, country)
        print(f"\n=== REGION '{a.state}': {len(union)} unique | {nocity} city-less | ${cost:.2f} [{status}] ===")
        print(f"raw -> {raw_path}")
        print(f"NEXT: filter_niche.py {raw_path} --keyword {kw} --terms \"<synonyms>\"")
        return

    # ---- whole country: loop regions ----
    run_dir = os.path.join(HERE, 'output', f"{a.country.lower()}-{slug(kw)}-allregions")
    os.makedirs(run_dir, exist_ok=True)
    cov_path = os.path.join(run_dir, 'coverage.json')
    raw_path = os.path.join(run_dir, 'raw.json')
    regions = rgeo['regions']
    prev = json.load(open(cov_path)) if os.path.exists(cov_path) else {'regions': []}
    done = {r['region'] for r in prev.get('regions', [])} if not a.force else set()
    todo = [r for r in regions if r['name'] not in done]
    print(f"[plan] ALL-REGIONS '{kw}' over {a.country}: {len(todo)} to scrape "
          f"({len(regions)-len(todo)} already done), level={rgeo.get('level')}")
    if a.dry_run:
        for r in todo:
            print("  ", r['name'])
        print(f"\n[dry-run] {len(todo)} region runs. No Apify call.")
        return
    union = {}
    if os.path.exists(raw_path):
        for it in json.load(open(raw_path)):
            union[it.get('placeId') or json.dumps(it, sort_keys=True)[:80]] = it
    rows = prev.get('regions', [])
    for r in todo:
        items, cost, status, used = scrape_region(kw, r['name'], r.get('level') or rgeo.get('level'),
                                                  cc, lang, a.keep_no_website, a.per_region, addons)
        net = union_add(union, items)
        rows.append({'region': r['name'], 'level': used, 'returned': len(items),
                     'net_new': net, 'cost': cost, 'status': status})
        finalize(run_dir, union, rows, kw, rgeo, country)   # save after every region (resumable)
        flag = '' if status == 'SUCCEEDED' else f'  ⚠️ {status}'
        print(f"  {r['name']:<24} {len(items):>5} returned, {net:>5} net-new  ${cost:.2f}{flag}")
    spend = sum(x['cost'] for x in rows)
    print(f"\n=== ALL-REGIONS {a.country}: {len(union)} unique places | ${spend:.2f} total ===")
    print(f"raw -> {raw_path}")
    print(f"NEXT: filter_niche.py {raw_path} --keyword {kw} --terms \"<synonyms>\"")


if __name__ == '__main__':
    main()
