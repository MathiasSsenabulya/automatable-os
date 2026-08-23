#!/usr/bin/env python3
"""run_campaign.py — niche-AGNOSTIC outbound campaign loop: scrape + filter + ingest
any niche across any country's regions, with done-tracking.

This generalises the (previously locksmith-hardcoded) campaign runner so the whole
scrape→filter→ingest layer is plug-any-niche: pass --niche + --country and it loops
that country's regions, scraping each (base config, contacts OFF — emails come from
recover_emails downstream), filtering to the genuine pool (+ out-of-target bucket),
and ingesting the genuine cohort to Supabase (nearest-2 + market count for the cold
mail). Never re-scrapes a region already in Supabase for the niche.

Per region (the shared foundation — "lead scraping + email fallback", always paired):
  seo_scrape_adaptive  -> raw.json
  ingest_to_supabase   -> genuine cohort + nearest-2 + out-of-target bucket  -> ledger
  export_cohort        -> runs/<slug>/{cleaned,needs_email,cohort_vars,no_contact}.csv
  recover_emails       -> Firecrawl-fill the no-email genuine leads (skip: --no-recover)

What stays DOWNSTREAM + forked by campaign variant (NOT in this loop, copy/scripts still
in flux): lead-cleaner -> icebreaker/casualize -> {Variant A: seo_enrich_run (DataForSEO)
| Variant B: site-finding + cohort_vars join} -> assemble -> Instantly.

TRACKING (never re-scrape a done region):
  * authoritative = Supabase: a region with niche rows is DONE, skipped.
  * convenience   = output/_<niche>_<country>_ledger.csv (region · date · operators · genuine).

Usage:
  run_campaign.py --niche locksmith --country UK [--terms "locksmith,schluessel"] [--limit 15] [--dry-run]
  run_campaign.py --niche schluesseldienst --country DE --terms "schluesseldienst,aufsperr"
"""
import json, subprocess, sys, os, re, csv, argparse, urllib.request, urllib.parse, datetime
import threading, concurrent.futures

# The steps are spawned with sys.executable, so they inherit whatever interpreter started this.
# ingest_to_supabase.py uses nested quotes inside an f-string, which only parses on 3.12+ — under
# the system python (3.9 on this machine) it dies with a SyntaxError that reads like a code bug
# rather than a wrong interpreter. Fail here instead, with the reason.
if sys.version_info < (3, 12):
    sys.exit(f"[fatal] needs python 3.12+, running {sys.version.split()[0]}. Use python3.13.")

_LEDGER_LOCK = threading.Lock()

HERE = os.path.dirname(os.path.abspath(__file__))
REF = "qhlklpweondgkswptyfc"


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


def sbkey():
    for line in open(os.path.expanduser('~/.config/credentials.env')):
        if line.startswith('POCKET_DASH_SUPABASE_SERVICE_ROLE='):
            return line.split('=', 1)[1].strip().strip('"')
    sys.exit("no POCKET_DASH_SUPABASE_SERVICE_ROLE")


def done_regions(niche, iso=''):
    """Regions already in Supabase for this niche+country = scraped and ingested.

    PostgREST caps a response at 1000 rows; a busy niche (locksmith London alone is
    ~950) blows past that, so a single GET would SILENTLY MISS done regions and we'd
    re-scrape (= wasted Apify spend). Paginate via Range until a short page returns.

    Der Laenderfilter kam am 23.08.2026 dazu. Vorher zaehlte allein die Nische, was
    solange gutging, wie es zwei Laender gab, deren Regionen sich nicht ueberschneiden.
    Mit elf Laendern tut es das: 'Victoria' liegt in Australien UND in Kanada, 'Hamilton'
    in Neuseeland, Kanada und Schottland. Ohne den Filter haette der erste Lauf den
    zweiten still uebersprungen -- und ein uebersprungener Scrape sieht aus wie ein
    fertiger."""
    key = sbkey()
    out, step, off = set(), 1000, 0
    while True:
        f = {'select': 'region', 'niche': f'eq.{niche}'}
        if iso:
            f['country'] = f'eq.{iso}'
        q = urllib.parse.urlencode(f)
        req = urllib.request.Request(f"https://{REF}.supabase.co/rest/v1/industry_operators?{q}",
                                     headers={'apikey': key, 'Authorization': f'Bearer {key}',
                                              'Range-Unit': 'items', 'Range': f'{off}-{off+step-1}'})
        rows = json.load(urllib.request.urlopen(req, timeout=30))
        out |= {r['region'] for r in rows if r.get('region')}
        if len(rows) < step:
            break
        off += step
    return out


def supa_count(niche, region):
    key = sbkey()
    q = urllib.parse.urlencode({'select': 'place_id,details', 'niche': f'eq.{niche}', 'region': f'eq.{region}'})
    req = urllib.request.Request(f"https://{REF}.supabase.co/rest/v1/industry_operators?{q}",
                                 headers={'apikey': key, 'Authorization': f'Bearer {key}'})
    rows = json.load(urllib.request.urlopen(req, timeout=30))
    gen = sum(1 for r in rows if (r.get('details') or {}).get('tier') == 'genuine')
    return len(rows), gen


def ledger_path(niche, country):
    return f"{HERE}/output/_{slug(niche)}_{slug(country)}_ledger.csv"


def ledger_append(niche, country, region, operators, genuine):
    # country lives in the filename (_<niche>_<country>_ledger.csv), so the ROW stays the
    # 5-col schema run_locksmith_uk established — keeps old + new rows column-aligned.
    p = ledger_path(niche, country)
    with _LEDGER_LOCK:                       # parallel mode: serialise the shared-file append
        os.makedirs(os.path.dirname(p), exist_ok=True)
        new = not os.path.exists(p)
        with open(p, 'a', newline='') as f:
            w = csv.writer(f)
            if new:
                w.writerow(['niche', 'region', 'scraped_at', 'operators', 'genuine'])
            w.writerow([niche, region, datetime.date.today().isoformat(), operators, genuine])


# Ein paar Laender heissen hier anders als bei GeoNames oder beim Actor.
ALIAS = {"GB": "UK"}


def land_info(cc_key):
    """ISO code the actor wants + the regions file, read from regions/<C>.json.

    Das war bis zum 23.08.2026 ein festes Dict mit UK, GB und DE. Damit lief die Kampagne
    fuer genau zwei Laender, egal wie viele Regionsdateien daneben lagen -- und ein neues
    Land bedeutete, diese Zeile zu finden. Jetzt ist die Regionsdatei selbst die Wahrheit:
    liegt sie da, ist das Land bespielbar.
    """
    cc_key = ALIAS.get(cc_key.upper(), cc_key.upper())
    pfad = os.path.join(HERE, 'regions', f'{cc_key}.json')
    if not os.path.exists(pfad):
        da = sorted(f[:-5] for f in os.listdir(os.path.join(HERE, 'regions'))
                    if f.endswith('.json'))
        sys.exit(f"[fatal] keine regions/{cc_key}.json.\n"
                 f"        vorhanden: {', '.join(da)}\n"
                 f"        bauen:     python3 build_regions.py {cc_key}\n"
                 f"        (build_regions.py --list zeigt auch, wie jedes Land rechtlich steht)")
    d = json.load(open(pfad, encoding='utf-8'))
    return cc_key, (d.get('countryCode') or cc_key).upper(), f'{cc_key}.json', d


def load_cred(name):
    """Load a secret from the environment, falling back to ~/.config/credentials.env.
    Never silently skip: a missing FIRECRAWL_API_KEY used to no-op the whole recovery step."""
    if os.environ.get(name):
        return os.environ[name]
    try:
        for line in open(os.path.expanduser('~/.config/credentials.env')):
            if line.startswith(name + '='):
                os.environ[name] = line.split('=', 1)[1].strip().strip('"')
                return os.environ[name]
    except FileNotFoundError:
        pass
    return None


# Ceremonial / no-OSM-admin-boundary regions -> their scrapable administrative sub-units.
# These fail geocoding at state/county/city level (abolished county councils, metropolitan
# counties), so we scrape the unitaries/boroughs instead. Built from the 2026-06-14 UK
# locksmith full-England sweep; extend per country as new gaps surface.
DECOMPOSE = {
    'Merseyside': ['Liverpool', 'Wirral', 'Sefton', 'Knowsley', 'St Helens'],
    'Cheshire': ['Cheshire East', 'Cheshire West and Chester', 'Halton', 'Warrington'],
    'Berkshire': ['Reading', 'Slough', 'Bracknell Forest', 'West Berkshire',
                  'Windsor and Maidenhead', 'Wokingham'],
    'Cumbria': ['Westmorland and Furness', 'Cumberland'],
    'Bedfordshire': ['Bedford', 'Central Bedfordshire', 'Luton'],
}


def process_region(c, label, a, iso, terms, cc_key, allow_decompose=True):
    """Full per-region pipeline: scrape -> ingest -> ledger -> export -> Firecrawl recover.
    If the scrape yields no raw and the region has a known admin decomposition, scrape its
    sub-units instead so ceremonial counties never silently drop out. Returns a status str."""
    landweit = getattr(a, 'country_wide', False)
    rd = (f"{HERE}/output/{cc_key.lower()}-{slug(a.niche)}-countrywide/raw.json" if landweit
          else f"{HERE}/output/{slug(c)}-region-{slug(a.niche)}/raw.json")
    print(f"\n========== {label} {c} ==========", flush=True)
    if not os.path.exists(rd):
        # --cold-email = --details --contacts --leads 1. seo_scrape_adaptive nennt --details
        # in seiner eigenen Hilfe "REQUIRED for a cold-email scrape", der Orchestrator hat es
        # aber nie gesetzt. Folge: ownerUpdates und openingHours kamen bei JEDEM Place leer
        # zurueck, und ein ungeschuetzter Check macht daraus "Ihnen fehlen die
        # Oeffnungszeiten" fuer alle. Kosten: +2$/1000 fuer details, +2$/1000 fuer contacts.
        cmd = [sys.executable, f'{HERE}/seo_scrape_adaptive.py',
               '--keyword', a.niche, '--country', cc_key]
        cmd += ['--country-wide'] if landweit else ['--state', c]
        if not a.cheap_scrape:
            cmd.append('--cold-email')
        subprocess.run(cmd)
    else:
        print(f"  [resume] {c}: raw exists, re-ingest only", flush=True)

    if not os.path.exists(rd):
        if allow_decompose and c in DECOMPOSE:
            subs = DECOMPOSE[c]
            print(f"  [decompose] {c}: no admin boundary -> {len(subs)} sub-units: {', '.join(subs)}", flush=True)
            for s in subs:
                process_region(s, f"{label}·{s}", a, iso, terms, cc_key, allow_decompose=False)
            return 'DECOMPOSED'
        print(f"  [skip] {c}: no raw produced (scrape failed/empty)", flush=True)
        return 'FAILED'

    subprocess.run([sys.executable, f'{HERE}/ingest_to_supabase.py', rd,
                    '--niche', a.niche, '--region', c, '--country', iso, '--terms', terms])
    total, gen = supa_count(a.niche, c)
    ledger_append(a.niche, cc_key, c, total, gen)
    print(f"  [ledger] {c}: {total} operators ({gen} genuine)", flush=True)

    subprocess.run([sys.executable, f'{HERE}/export_cohort.py', '--niche', a.niche, '--region', c])
    rundir = f"{HERE}/runs/{slug(a.niche)}-{slug(c)}"
    needs = f"{rundir}/needs_email.csv"
    if a.no_recover:
        print(f"  [recover] {c}: skipped (--no-recover)", flush=True)
    elif not os.environ.get('FIRECRAWL_API_KEY'):
        print(f"  [recover] {c}: SKIPPED — no FIRECRAWL_API_KEY in env or credentials.env", flush=True)
    elif os.path.exists(needs) and sum(1 for _ in open(needs)) > 1:
        subprocess.run([sys.executable, f'{HERE}/recover_emails.py',
                        '--needs', needs, '--out', f'{rundir}/cleaned.csv',
                        '--push-supabase'])   # cohort = source of truth: persist recovered emails
    else:
        print(f"  [recover] {c}: nothing to recover (no website-but-no-email leads)", flush=True)
    return 'OK'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--niche', help="e.g. locksmith / schluesseldienst / dentist")
    ap.add_argument('--niches', default='',
                    help="statt --niche: all | emergency | slug,slug aus maerkte.json. "
                         "Laeuft die Branchen nacheinander durch, jede mit eigenem Scrape "
                         "und eigener Kohorte.")
    ap.add_argument('--country', default='UK',
                    help="Laenderkuerzel; es zaehlt, ob regions/<CC>.json existiert "
                         "(build_regions.py --list zeigt die vorhandenen)")
    ap.add_argument('--country-wide', action='store_true',
                    help="EIN Scrape-Lauf fuer das ganze Land statt Region fuer Region. "
                         "Gemessen an Neuseeland (23.08.2026): ein Landlauf fand 330 Betriebe "
                         "fuer 1,65$, dieselbe Nische ueber die generierte Regionsliste kam "
                         "nach 9 von 31 Laeufen auf 97. Grund: die automatischen Polygone fuer "
                         "generierte Regionsnamen sind zu eng -- 'Auckland' als city gab 17 "
                         "Treffer fuer ein Drittel des Landes. Bei einer KURATIERTEN Liste (UK) "
                         "gilt das nicht, dort ist der Regionsweg genauer und wiederaufnehmbar.")
    ap.add_argument('--terms', default='', help="comma niche-match synonyms for the filter; default = niche + stem")
    ap.add_argument('--limit', type=int, default=15)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--force-region', default='', help="scrape exactly this region (ignores done-tracking)")
    ap.add_argument('--cheap-scrape', action='store_true',
                    help="Basis-Scrape ohne --cold-email (spart ~4$/1000). ACHTUNG: ohne "
                         "scrapePlaceDetailPage bleiben ownerUpdates und openingHours leer, "
                         "die Findings dazu koennen dann nichts aussagen.")
    ap.add_argument('--no-recover', action='store_true',
                    help="skip the Firecrawl email-recovery step (just scrape+ingest+export)")
    ap.add_argument('--parallel', type=int, default=1,
                    help="scrape N regions concurrently (Apify STARTER pool allows ~5-8)")
    a = ap.parse_args()

    # load the recovery key up front (env, then credentials.env) so it can't silently no-op
    if not a.no_recover and not load_cred('FIRECRAWL_API_KEY'):
        print("[warn] FIRECRAWL_API_KEY not in env or credentials.env — email recovery will skip", flush=True)

    if bool(a.niche) == bool(a.niches):
        sys.exit("[fatal] entweder --niche \"<begriff>\" oder "
                 "--niches all|emergency|<slug,slug>.")
    cc_key, iso, regions_file, rgeo = land_info(a.country)

    # Rechtslage einmal ansagen, bevor Geld ausgegeben wird. Scrapen ist ueberall zulaessig,
    # anschreiben nicht -- und wer das erst nach dem Versand merkt, hat das falsche Problem.
    markt = os.path.join(HERE, 'maerkte.json')
    if os.path.exists(markt):
        eintrag = next((l for l in json.load(open(markt, encoding='utf-8'))['countries']
                        if l['code'] == cc_key), None)
        if eintrag and eintrag['light'] != 'green':
            wort = {'amber': 'nur bedingt', 'red': 'nicht empfohlen'}[eintrag['light']]
            print(f"[legal] {eintrag['name']}: Kaltmail {wort} ({eintrag['regime']}). "
                  f"{eintrag['catch']}\n"
                  f"        Scrapen ist davon unberuehrt -- der Versand ist die Frage.",
                  flush=True)
        elif not eintrag:
            print(f"[legal] {cc_key} steht nicht in maerkte.json -- Rechtslage ungeprueft.",
                  flush=True)

    # Eine Branche oder viele. Bei mehreren laeuft der ganze Block je Branche einmal
    # durch -- eigener Scrape, eigene Kohorte, eigenes Ledger.
    if a.niche:
        branchen = [(slug(a.niche), a.niche.strip().lower())]
    else:
        from seo_scrape_adaptive import nischen_aufloesen
        branchen = nischen_aufloesen(a.niches)
        print(f"[campaign] {len(branchen)} Branchen ueber {rgeo.get('country', cc_key)}: "
              f"{', '.join(k for _, k in branchen)}", flush=True)

    schaetze_kosten(rgeo, len(branchen), cc_key)
    for nr, (_, branche) in enumerate(branchen, 1):
        if len(branchen) > 1:
            print(f"\n{'#' * 70}\n### {nr}/{len(branchen)}  {branche}\n{'#' * 70}", flush=True)
        a.niche = branche
        eine_branche(a, cc_key, iso, rgeo)


# Zwei gemessene Groessen, aus denen sich der Preis eines Laufs vorher abschaetzen laesst.
# Beide stehen hier statt in einem Kommentar, damit sie korrigierbar sind, wenn ein Lauf
# etwas anderes zeigt.
TREFFER_JE_MIO = 87      # Greater London: 1.359 Schluesseldienste auf 15,7 Mio Stadtbevoelkerung
DOLLAR_JE_TREFFER = 0.005   # Neuseeland landweit: 330 Treffer fuer $1.65


def schaetze_kosten(rgeo, n_branchen, cc_key):
    """Was der Lauf ungefaehr kostet -- gesagt, BEVOR er laeuft.

    Der Anlass (Luka, 23.08.2026): "verbrate jetzt nicht alle meine Apify-Credits."
    Ein Befehl, der 17 Branchen ueber ein Land schickt, kann dreistellig werden, und man
    sah es vorher nirgends. Die Schaetzung ist grob -- Schluesseldienste sind dichter
    gesaet als Dachdecker -- aber die Groessenordnung stimmt, und die entscheidet.
    """
    pop = rgeo.get('_urban_pop')
    if not pop:
        return
    treffer = pop / 1e6 * TREFFER_JE_MIO
    dollar = treffer * DOLLAR_JE_TREFFER * n_branchen
    je = f", ~${dollar / n_branchen:.0f} je Branche" if n_branchen > 1 else ""
    print(f"[kosten] geschaetzt ~${dollar:.0f} fuer {n_branchen} Branche(n) ueber {cc_key}"
          f"{je} -- rund {treffer:,.0f} Betriebe je Branche erwartet.".replace(',', '.'),
          flush=True)
    print(f"         Grundlage: {TREFFER_JE_MIO} Betriebe je Mio Stadtbevoelkerung "
          f"(Schluesseldienste London) und ${DOLLAR_JE_TREFFER}/Treffer (Neuseeland landweit). "
          f"Eine duennere Branche kostet weniger.", flush=True)


def eine_branche(a, cc_key, iso, rgeo):
    """Ein Gewerbe ueber ein Land -- landweit in einem Lauf oder Region fuer Region."""
    terms = a.terms or f"{a.niche},{a.niche.rstrip('s')}"
    # Landweit ist die "Region" das Land selbst: eine Einheit, ein Lauf, ein Ledger-Eintrag.
    if a.country_wide:
        land = rgeo.get('country', cc_key)
        if not a.force_region and land in done_regions(a.niche, iso):
            print(f"[campaign] {a.niche} {cc_key}: landweit bereits gescrapt, uebersprungen. "
                  f"(--force-region \"{land}\" erzwingt neu)", flush=True)
            return
        print(f"[campaign] {a.niche} {cc_key} · EIN Lauf ueber {land}", flush=True)
        if a.dry_run:
            print("[dry-run] no scrape/ingest.")
            return
        process_region(land, "[1/1]", a, iso, terms, cc_key, allow_decompose=False)
        return

    regions = [r['name'] for r in rgeo['regions']]
    if a.force_region:
        todo = [a.force_region]
        done = set()
    else:
        done = done_regions(a.niche, iso)
        # a ceremonial county counts as done once all its decomposition sub-units are scraped
        # (it never gets a Supabase row under its own name), else it re-attempts forever.
        def is_done(c):
            return c in done or (c in DECOMPOSE and all(s in done for s in DECOMPOSE[c]))
        todo = [c for c in regions if not is_done(c)][:a.limit]
    print(f"[campaign] {a.niche} {cc_key} · {len(done)}/{len(regions)} regions done "
          f"({', '.join(sorted(done)) or 'none'})", flush=True)
    print(f"[campaign] this run ({a.limit}): {', '.join(todo) or 'nothing left'}", flush=True)
    if a.dry_run or not todo:
        print("[dry-run] no scrape/ingest." if a.dry_run else "[campaign] nothing to do.")
        return

    n = max(1, a.parallel)
    if n == 1:
        for i, c in enumerate(todo, 1):
            process_region(c, f"[{i}/{len(todo)}]", a, iso, terms, cc_key)
    else:
        print(f"[campaign] {len(todo)} regions, {n} concurrent", flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=n) as ex:
            futs = {ex.submit(process_region, c, f"[{i}/{len(todo)}]", a, iso, terms, cc_key): c
                    for i, c in enumerate(todo, 1)}
            for fut in concurrent.futures.as_completed(futs):
                try:
                    fut.result()
                except Exception as e:
                    print(f"  [error] {futs[fut]}: {e}", flush=True)
    # Entdoppelung ZUM SCHLUSS, ueber alle Regionen zusammen. Pro Regionsdatei rutschen
    # 220 Ketten-Standorte durch, weil eine Kette regional unter der Schwelle bleibt
    # (Keytek in 38 von 62 Regionen). Supabase ist der einzige Ort mit dem Gesamtblick.
    # Laeuft als Dry-Run: markiert wird erst mit --apply, weil es Prod-Daten aendert.
    print(f"\n[campaign] Entdoppelung (Vorschau, alle Regionen):", flush=True)
    subprocess.run([sys.executable, f'{HERE}/dedupe_leads.py', '--supabase', a.niche])
    print(f"  -> zum Anwenden: python3 dedupe_leads.py --supabase {a.niche} --apply", flush=True)

    print(f"\n[campaign] DONE — ledger: {ledger_path(a.niche, cc_key)}", flush=True)


if __name__ == '__main__':
    main()
