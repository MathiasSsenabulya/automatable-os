#!/usr/bin/env python3
"""verify_emails.py — deliverability-verify a lead CSV via MillionVerifier, drop the bouncers.

Runs EARLY in the pipeline (right after clean_run + recover_emails, before the expensive enrich +
site-reading) so DataForSEO and the Haiku site-reads never burn budget on dead emails. Scraped emails
are raw strings — unverified sends bounce and torch the sending domains' reputation, which is fatal
while inboxes are warming.

MillionVerifier single endpoint (~$0.0004/email): GET api.millionverifier.com/api/v3/?api=KEY&email=X
Buckets: ok (keep) · catch_all (keep, usually deliverable) · unknown (keep by default, greylisting —
re-run to resolve) · invalid / disposable (DROP, they bounce). Adds an `mv_status` column.

Usage: python3 verify_emails.py --in runs/<slug>/cleaned.csv --out runs/<slug>/cleaned.csv [--drop-unknown]
"""
import os, csv, argparse, requests
from concurrent.futures import ThreadPoolExecutor
from collections import Counter

KEY = os.environ['MILLIONVERIFIER_API_KEY']
DROP = {'invalid', 'disposable', 'error_no_email'}      # always bounce -> remove


def verify(email):
    e = (email or '').strip()
    if not e or '@' not in e:
        return e, 'invalid'
    try:
        r = requests.get('https://api.millionverifier.com/api/v3/',
                         params={'api': KEY, 'email': e, 'timeout': 10}, timeout=20).json()
        return e, (r.get('result') or 'error')
    except Exception:
        return e, 'unknown'                              # network blip -> keep (don't drop on our error)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='inp', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--drop-unknown', action='store_true', help='also drop unknown (greylisted) — stricter')
    ap.add_argument('--workers', type=int, default=20)
    a = ap.parse_args()

    rows = list(csv.DictReader(open(a.inp)))
    emails = [r.get('email', '') for r in rows]
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        status = dict(ex.map(verify, emails))

    drop = set(DROP) | ({'unknown'} if a.drop_unknown else set())
    kept = []
    for r in rows:
        st = status.get((r.get('email') or '').strip(), 'unknown')
        r['mv_status'] = st
        if st not in drop:
            kept.append(r)

    fields = list(rows[0].keys())
    if 'mv_status' not in fields:
        fields.append('mv_status')
    with open(a.out, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(kept)

    c = Counter(status.values())
    bd = ' · '.join(f'{k} {n}' for k, n in c.most_common())
    print(f"VERIFIED {len(rows)} -> kept {len(kept)} (dropped {len(rows)-len(kept)}: {', '.join(sorted(drop))})")
    print(f"  breakdown: {bd}")


if __name__ == '__main__':
    main()
