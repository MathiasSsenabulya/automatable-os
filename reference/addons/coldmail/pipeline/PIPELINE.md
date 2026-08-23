# Die Pipeline vom Initial-Scrape bis zur Cold Mail

Festgelegt am 2026-07-25. Jede Zahl hier ist an echten Daten gemessen (7.291 Locksmith-Places,
22 gespeicherte Lead-Seiten, 25 gebaute Reports), nicht geschätzt. Wo eine Zahl fehlt, steht
das da.

Verwandte Dateien: [`findings.py`](findings.py) (GBP-Findings) · [`web_findings.py`](web_findings.py)
(Website-Findings) · [`../../skills/lead-magnet/`](../../skills/lead-magnet/) (Report-Pfad)

---

## 0. DER ABLAUF — welches Skript wann, und was diese Kampagne NICHT ist

> Festgelegt am 23.08.2026, weil die Abgrenzung nirgends stand. In `campaigns/engine/` liegen
> **41 Python-Dateien**, und nur die zehn unten gehören zur laufenden Google-Business-Profil-
> Kampagne. Der Rest ist Werkzeug für andere Varianten, Altlast aus der Sonnet-Zeit oder
> Sonderzüge, die Geld kosten und ausdrücklich angestoßen werden.

### Schritt 0: welches Land, welche Branche

Steht in [`maerkte.json`](maerkte.json) — elf Länder mit ihrer Rechtslage, zwanzig Branchen
mit dem Suchbegriff, unter dem Maps sie kennt. Dieselbe Datei speist die Erklärseite, damit
Seite und Pipeline nicht auseinanderlaufen.

```bash
python3 build_regions.py --list          # welche Länder, wie sie rechtlich stehen
python3 build_regions.py US              # Regionen für ein neues Land bauen
```

**Die Ebene ist eine gemessene Größe, keine gesetzte.** `build_regions.py` arbeitet
standardmäßig adaptiv: Bundesstaaten als Region, und nur die, die für einen Lauf zu groß
sind, werden in Countys zerlegt. Australien bekommt so 8 Regionen (Western Australia bleibt
ganz — 2,8 Mio Einwohner, davon 2,4 in Perth, das Umland kostet fast nichts mit), die USA
195 statt 954. Die Schwelle stammt vom größten Lauf, der nachweislich vollständig war:
Greater London, 1.359 Treffer für 9,51 $.

**Ein ganzes Land geht auch in einem einzigen Lauf** — gemessen am 23.08.2026 an
Neuseeland, Schlüsseldienste:

| | Treffer | Kosten | Läufe |
|---|---|---|---|
| `--country-wide` | **330** | 1,65 $ | 1, sechs Minuten |
| über die generierte Regionsliste | 97 | 0,52 $ | 9 von 31, dann abgebrochen |

Der Unterschied liegt an den Namen, nicht am Rastern: „Auckland" scheitert als County ganz
und gibt als City 17 Treffer für ein Drittel des Landes, weil automatische Stadtpolygone die
Agglomeration nicht enthalten. **Bei einer kuratierten Liste dreht sich das um** — UK wird
county-weise gescrapt, weil die Namen dort geprüft sind und ein Lauf, der bei County 40
stirbt, bei 41 weitermacht statt von vorn.

```bash
# eine Branche, ein Land, ein Lauf
python3 run_campaign.py --niche locksmith --country NZ --country-wide
# alle 17 Notfall-Branchen über ein Land
python3 run_campaign.py --niches emergency --country AU --country-wide
```

Beide sagen vor dem Start, was sie ungefähr kosten (~11 $ je Branche für Australien, 181 $
für alle siebzehn) und wie das Zielland rechtlich steht. Scrapen ist überall zulässig,
anschreiben nicht.

### Die zehn Schritte, in Reihenfolge

| # | Schritt | Skript | rein → raus | Kosten |
|---|---|---|---|---|
| 1 | **Scrapen** | `run_campaign.py` | Nische + Land → `industry_operators` in Supabase | Apify, ~0,002 $/Betrieb |
| 2 | **Leistungen nachziehen** | `dfs_listings.py` | Kohorte → `raw_dataforseo.services` | DataForSEO, ~1,34 $/Nische |
| 3 | **Landesvergleich rechnen** | `benchmark.py --refresh` | alle Zeilen der Nische → `benchmarks.json` | keine, reine Rechnung |
| 4 | **Mailadressen finden** | `recover_emails.py` | Leads mit Website ohne Mail → Mail | Firecrawl, nur für die Lücken |
| 5 | **Kohorte exportieren** | `export_cohort.py` | Supabase → `runs/<slug>/` + alle Variablen | keine |
| 6 | **Stichpunkte bauen** | `pool.py` (via `stapel.py`) | Blatt je Lead → 3 bis 5 Stichpunkte | keine, kein Modell |
| 7 | **Prüfen** | `stapel.py` → vier Prüfer | Mail → Mängel oder frei | keine |
| 8 | **Nachzählen** | `mail_audit.py` | ganzer Bestand → stille Ausfälle | keine |
| 9 | **Versanddatei** | `export_cohort.py` → `instantly.csv` | nur versandfertige Leads, nur Vorlagen-Variablen | keine |
| 10 | **Hochladen** | `tools/cold-email-pipeline/execution/upload_leads_to_campaign.py` | `instantly.csv` → Instantly-Kampagne | Instantly-Abo |

**Kein Modell schreibt in diesem Weg mit.** Schritt 6 war bis zum 22.08. Sonnet-Arbeit, zehn
Stichpunkte je Runde von Hand angestoßen. Bei 2.483 Leads sind das rund 250 Runden — der
Engpass war nie die Datenlage und nie das Geld, sondern dass jemand tippen musste.

### Die vier Prüfer (Schritt 7), und was jeder fängt

| Prüfer | fängt |
|---|---|
| `preview_mail.render` | fehlende Variable, doppelte Leerzeile, kaputter Aufbau |
| `verify_mail` | Zahl ohne Beleg, Superlativ über den Ort, Füllwort, über 80 Zeichen |
| `fact_sheet.widerspricht` | ein Rat, den der Betrieb laut Datenblatt längst umgesetzt hat |
| `fact_sheet.formel` | Zeile ohne Status quo, ohne Handlung oder ohne echte Folge |

Ein Lead, bei dem einer anschlägt, geht **nicht** in `instantly.csv`. Gemessen am 23.08.:
99 % erreichen drei oder mehr Stichpunkte, der Rest fällt sauber heraus statt halb versandt zu
werden.

### Was NICHT dazugehört

| Datei | wofür sie da ist |
|---|---|
| `write_mail.py`, `brief.py`, `batch_briefs.py` | die Sonnet-Fassung: Briefe raus, Mails zurück. Läuft nicht mehr im Standardweg, bleibt für Sonderfälle |
| `score.py`, `findings.py`, `web_findings.py` | der alte Audit-Katalog mit Site-Hälfte. Der Site-Read läuft nicht mehr, `gbp_score.py` hat ihn ersetzt |
| `site_read.py`, `seo_scrape_adaptive.py`, `seo_enrich_run.py` | Website-Abruf für die `seo`-Variante, nicht für `markt` |
| `deeper_pull.py`, `rank_pull.py`, `reviews_pull.py` | Sonderzüge, die Geld kosten. Nur für einzelne Leads, nie im Stapel |
| `build_vars.py`, `build_lead_findings.py` | Vorstufen aus der Zeit vor `export_cohort.py` |

**Der Test, ob etwas dazugehört:** Läuft es bei einem normalen Durchlauf über eine ganze Nische
mit, ohne dass jemand es einzeln anstößt? Dann steht es in der Tabelle oben. Sonst nicht.

---

## 0a. Die Datengrundlage — festgelegt am 27.07.2026

> Wer hier etwas ändern will, ändert es HIER zuerst. Jede Quelle steht drin, weil sie
> einen Befund trägt, den keine andere trägt. Doppelt gescrapte Felder gibt es nicht.

| Quelle | Liefert | Warum genau diese |
|---|---|---|
| **Apify** `crawler-google-places` mit `--details --contacts` | **E-Mail**, Bewertungen, Sterne, Fotos, Kategorien, Öffnungszeiten, **Beiträge** | Die E-Mail gibt es **nirgends sonst**: Google veröffentlicht keine, DataForSEO hat in 42 Feldern keine. Apify ruft die Firmenwebsite auf. Gemessen 82% Abdeckung gegen 31% bei DataForSEO, echter Zugewinn durch DFS nur 11 von 546 Leads. Dazu taggenau: der Live-Abgleich stimmte Zeichen für Zeichen (1328 Bewertungen, 51 Fotos). |
| **DataForSEO** `business_listings/search` | **Leistungsliste**, Attribute, `place_topics` mit Häufigkeit | Repariert einen **falschen Befund**: `gbp-services` prüfte nur die Kategorien und behauptete "your profile mentions neither", obwohl die Leistung in der Leistungs-Sektion stand. 2 von 6 Bedford-Leads betroffen, der Check feuert bei 63%. |
| **DataForSEO** `serp/google/maps/live` **je Ort** | der echte **Maps-Rang** | Der Apify-`rank` ist keiner: in Bedford war Platz 13 dreimal vergeben, sechs Plätze fehlten. DataForSEO liefert 1 bis 20 lückenlos. Eine Abfrage je Ort statt je Lead, weil die Antwort 20 Treffer **mit place_id** enthält. |
| **DataForSEO** `business_data/google/reviews` | **Antwortquote** des Inhabers | Der stärkste Unterscheider, den wir gefunden haben: von 0% (Marktführer mit 1328 Bewertungen) bis 97%. Gibt es aus keiner anderen Quelle. |
| **DNS-Abfrage** | tote Website im Profil | Kostenlos, kein Scrape. ~200 Betriebe schicken Leute auf eine Domain, die nicht mehr existiert. |

**Bewusst NICHT dabei:**

- **Der HTML-Scrape der Startseite.** 13 Markup-Checks, bei denen **81 % der Leads 70 Punkte oder mehr erreichen** — ein Lob, das vier von fünf bekommen, ist keine Information. Er hat die einzige Aussage produziert, die ein Empfänger aus eigener Anschauung widerlegen kann, und rettet dünne Leads nur mit den schwächsten Zeilen des Katalogs ("no LocalBusiness markup"). Die Zeit und das Firecrawl-Guthaben stehen in keinem Verhältnis.
- **SEO-Daten** (Organic-Rang, Backlinks, Ranked Keywords, Lighthouse). Bei einem Notdienst kommen die Anrufe aus dem Kartenblock, nicht aus Platz 4 der blauen Links. Backlinks sind Agentur-Sprache, kein Nachmittagsjob. **Das sind die Dimensionen, die den Report rechtfertigen** — sie gehören nicht in die Mail, sie sind ihr Angebot.
- **`questions_and_answers`** — bei 6 von 6 Leads leer.
- **`my_business_updates`** — Apify liefert die Beiträge zuverlässig, DataForSEO in 1 von 6 Fällen.
- **`my_business_info/live`** für Massenfelder — $0.0054 gegen $0.00037 je Betrieb, 14× teurer für Felder, deren Frische nichts ändert.

**Frische, gemessen statt vermutet.** Die billige `business_listings`-Datenbank ist im Median 28 Tage alt. Über 540 Leads gegen unseren frischen Apify-Scrape geprüft: Öffnungszeiten **0,0 %** Abweichung, beansprucht 0,4 %, Kategorien 2,0 % — die trägen Felder stimmen. Nur Bewertungen (16,5 %) und Fotos (16,1 %) laufen auseinander, und genau die kommen aus Apify. **Rang und Antwortquote laufen deshalb über die Live-Endpunkte, alles Träge über die Datenbank.**

**Kosten für 3.593 Leads:** Apify $24,90 (einmalig, bezahlt) · Leistungslisten $1,34 · Maps-Rang $1,15 · Antwortquote $2,69. Zusammen **$30,08**, also **0,8 Cent je recherchiertem Lead**.

---

## 0b. Der Grundsatz, dem alles folgt

> **Python entscheidet, was wahr ist und was es bedeutet. Das Modell setzt es nur zusammen.**

Eine falsche Behauptung geht an einen Fremden, der sie in fünf Sekunden prüfen kann. Deshalb ist
kein einziges Finding eine Modell-Entscheidung. Das Modell bekommt fertige Aussagen und darf
nichts hinzufügen.

**Und: nicht gemessen ist nie ein Mangel.** Ein Feld, das wir nicht abgerufen haben, erzeugt
kein Finding. Es erzeugt gar nichts. Diese Regel ist am 25.07. dreimal verletzt worden
(Öffnungszeiten, Google Posts, Website-Lücken bei blockierten Seiten) und jedes Mal hätte sie
uns eine nachweislich falsche Aussage gekostet.

---

## 1. Stufe A — Initial-Scrape (Hunderte bis Tausende)

**Werkzeug:** Apify `compass/crawler-google-places`, ~4 $/1000 Basis.

**Schalter, die gesetzt sein müssen:**

| Schalter | Kosten | Warum nicht optional |
|---|---|---|
| `scrapePlaceDetailPage` | +2 $/1000 | Ohne ihn sind `ownerUpdates` und `openingHours` bei **jedem** Place leer. Ein ungeschützter Check macht daraus „Ihnen fehlen die Öffnungszeiten" für alle. |
| `scrapeContacts` | +2 $/1000 | E-Mail-Adressen. Alternativ `recover_emails.py`. |

**Was danach an GBP-Findings möglich ist** (`findings.py`, gemessen):
Kategorien, Bewertungszahl und Schnitt, Fotos, Öffnungszeiten, Google Posts, Beanspruchungs-Status,
Buchungslink, Bewertungs-Themen.

---

## 2. Die Lead-Qualität ist der eigentliche Engpass

Vor jedem Website-Abruf. Gemessen an der Locksmith-Liste:

| | |
|---|---|
| Places mit Website | 7.291 |
| **verschiedene Domains** | **3.984** |
| Places auf einer geteilten Domain | 3.668 (**50%**) |
| Timpson allein | **2.170 Places (30% der Liste)** |
| „Website" ist eine Facebook-Seite | 64 |

**Konsequenz: pro Domain nur EIN Lead.** Ohne diese Entdopplung gingen 1.877 fast identische
Mails an Timpson-Filialen. Das ist kein Personalisierungsfehler, das ist Spam, und es verbrennt
die Sende-Domain.

### Die Verteilung, an der die Schwelle hängt

| Filialen je Domain | Domains | Places | Anteil |
|---|---|---|---|
| **1** | **3.623** | 3.623 | 50% |
| 2 | 266 | 532 | 7% |
| 3–5 | 60 | 218 | 3% |
| 6–10 | 17 | 134 | 2% |
| 11–25 | 8 | 119 | 2% |
| 26–100 | 7 | 351 | 5% |
| **101+** | **3** | **2.314** | **32%** |

91% der Domains haben genau einen Standort; drei Domains tragen ein Drittel aller Places.

### Zwei Schritte, nicht einer

**Gebaut als [`dedupe_leads.py`](dedupe_leads.py).** Echter Lauf über alle 62 Regionen:
**7.291 Zeilen → 3.922 anschreibbare Betriebe.** Nichts wird gelöscht, alles Aussortierte geht
mit Grund in `_deduped_out.json` (dieselbe „never drop, bucket"-Regel wie `ingest_to_supabase.py`).

> **Immer alle Regionen auf einmal übergeben, nie Datei für Datei.** Bei regionaler Zählung
> rutschen **220 Ketten-Standorte** durch, weil eine Kette pro Region unter der Schwelle bleibt:
> Keytek in 38 von 62 Regionen, Timpson in 15. Die CLI nimmt deshalb mehrere Dateien und warnt,
> wenn nur eine kommt.

**1. Entdoppeln nach Domain.** 7.291 Places → 3.984 Leads. Timpson wird von 1.877 Mails zu einer.
Damit ist die teure Katastrophe abgewendet.

**2. Kettenfilter, Schwelle 10.** Er beantwortet nur noch die kleinere Frage: soll der eine
übrig gebliebene Lead überhaupt angeschrieben werden? Bei einer Kette nein — Timpson hat eine
Marketingabteilung, und „dein Profil ist dünn" ist bei einer nationalen Marke sinnlos, deren
Standortseiten absichtlich nach Vorlage gebaut sind.

| Schwelle | verworfene Domains | bleiben |
|---|---|---|
| ab 3 | 95 | 98% |
| **ab 10 (gewählt)** | **35** | **99,5%** |
| ab 25 | 18 | 100% |

Bei 10 fliegen genau die Marken raus (Timpson, Lockfit, Keytek, Lockforce, Able Group, Go Assist)
und **kein Handwerker mit drei Transportern**. Die Asymmetrie entscheidet: eine Kette anzuschreiben
kostet einen Send, einen wachsenden Lokalbetrieb wegzuwerfen kostet einen Kunden.

**Immer raus, unabhängig von der Schwelle:**
- `facebook.com`, `instagram.com` und andere Profile als „Website" (135 Fälle)

**Nebenbefund aus dem echten Lauf: die Liste enthält Maps-Spam.** Der Kettenfilter fängt neben
den Marken auch `fastlocksmithbirmingham.store` (53), `eldriclocksmith.shop` (18),
`homelytics.store` (16), `belsizelocksmith.shop` (10), `lockwisegroup.site` (10) — und
**`seomappro.us` (11)**, wörtlich der Name eines Maps-Spam-Werkzeugs. Billige TLDs plus
Dutzende Standorte plus generischer Name sind das Muster gefälschter Einträge. Sie fallen
hier zufällig mit heraus; ob sie einen eigenen Filter verdienen, ist offen.

---

## 3. Stufe B — Website-Abruf

Zwei Wege, gemessen an 120 zufälligen Locksmith-Domains:

| Ergebnis | Anteil |
|---|---|
| **verwertbar** | **60%** |
| blockiert (403/401/429) | **34%** |
| nicht erreichbar | 2% |
| sonstige Fehler | 4% |

**Firecrawl als Fallback: 12 von 12 blockierten Seiten gerettet.** Damit steigt die Abdeckung
rechnerisch von 60% auf über 90%.

**Empfohlener Ablauf:**
1. Nackter HTTP-Abruf (kostenlos) → deckt 60% ab
2. Nur bei `blocked` oder leerem Ergebnis: Firecrawl → holt den Großteil des Rests
3. Bleibt es leer: **kein Website-Finding.** Die Mail läuft auf GBP-Findings, die für jeden da sind.

Bei den qualifizierten Leads (die geantwortet haben) liegt die Quote höher: 86% erreichbar,
73% verwertbar. Kalte Listen sind schlechter, damit ist zu rechnen.

---

## 4. Welche Findings — und welche bewusst nicht

Trefferquoten an 22 echten Lead-Seiten gemessen. **Eine Lücke, die jeden trifft, ist wahr und
sagt trotzdem nichts über diesen Betrieb** — und ab der zehnten Mail liest sie sich als Vorlage.

### Genommen

| Finding | feuert | Warum |
|---|---|---|
| Title ohne Leistung **und** Stadt | 23% | Zitierbar, stärkster Copy-Fund |
| H1-Platitüde | 36% | Zitierbar |
| Title ohne Leistung | 32% | Zitierbar |
| Kein Tap-to-Call | 41% | Sofort verständlich, körperlich nachvollziehbar |
| Kein Formular | ~48% | Konkrete Folge |
| Kein LocalBusiness-Schema | 55% | Echte Folge |
| Bewertungen nicht ausgezeichnet | 86% | Universell, **aber** knüpft an etwas an, das ihnen gehört. Gedeckelt auf Stärke 45, nie führend. |
| Dünner Text | 32% | |

### Verworfen

| Finding | feuert | Warum nicht |
|---|---|---|
| Karte nicht eingebettet | 95% | Universell, niemanden interessiert es |
| FAQ-Schema fehlt | 77% | Universell, emotional wertlos |
| Viewport fehlt | **0%** | Trifft niemanden, tote Prüfung |
| NAP-Abgleich | — | Adress-Stringvergleich zu fragil („St." gegen „Street") |
| Copy-Qualität als Urteil | 27% | Heuristisch. Nur mit wörtlichem Zitat, dann belegt sich die Aussage selbst |

### Nur mit Full-Crawl (Report-Leads)

Doppelte Titel · fast leere Seiten · Leistungen ohne eigene Seite (GBP × Website, das kann keine
Quelle allein) · Tag-Archiv-Ballast.

---

## 4b. DIE FESTLEGUNG — was in einen Stichpunkt darf, und wie verglichen wird

> Festgelegt am **22.08.2026** mit Luka ("wir müssen klar festlegen, was wir für Findings in
> die Bulletpoint-Listen schreiben können, und wie wir die Vergleiche zu den Competitors
> herstellen"). Alle Zahlen unten sind über die **2.717 offenen Locksmith-Leads** gemessen,
> nicht geschätzt. Wer hier etwas ändert, ändert es HIER zuerst.

### Die eine Datenquelle: der GBP-Scraper mit Details

**Nur `raw` aus Apify `crawler-google-places` mit `scrapePlaceDetailPage`** (Luka, 22.08.:
"wir nutzen ja nur die Daten aus dem Google-Business-Profil-Scraper mit den Details").
Gemessen über die 2.744 anschreibbaren Leads deckt er **acht von neun Bausteinen** ab, und die
Review-Themen sogar besser als die gekaufte Alternative: `raw.reviewsTags` liefert **258**
verwertbare Themen je 600 Leads gegen **230** bei DataForSEOs `place_topics`. Deshalb kommen
sie seit 22.08. aus Apify, mit `place_topics` nur noch als Rückfall für Altbestände.

**Nicht mehr benutzt, und warum:**

| Quelle | Abdeckung | Grund |
|---|---|---|
| `web_signals.site_finding` | 74 % bei locksmith, **0 % überall sonst** | Alles aus Juni 2026, der Site-Read läuft nicht mehr. Für jede neue Nische wäre das Feld leer, die Pipeline also nicht übertragbar. Verbot 5 der Schreibkarte bleibt richtig. |
| `raw_dataforseo.antworten` | **3 %** | Zwei Stunden Laufzeit für fast nichts. |
| `raw_dataforseo.attributes` | 74 % | Enthält für Handwerker nur Irrelevantes (Rollstuhlzugang, LGBTQ-freundlich). |
| `raw.ownerUpdates`, `raw.bookingLinks` | 81 % / 100 % **`None`** | Nie gemessen, also kein Befund. |

**DataForSEO bleibt — aber NUR für die Felder, die Google Maps nicht hergibt** (Luka, 22.08.).
Das ist nach vollständiger Gegenprüfung genau **eins**:

| DFS-Feld | Apify-Gegenstück | Urteil |
|---|---|---|
| **`services`** | **keins** | **BEHALTEN.** $1,34 je Nische. |
| `place_topics` | `reviewsTags`, deckt besser ab | redundant, seit 22.08. auf Apify umgestellt |
| `attributes` | `additionalInfo` | redundant, und der Inhalt trägt ohnehin keinen Befund |
| `antworten` | keins, aber **3 %** gefüllt | aus dem Standardlauf raus |
| `stand` | — | nur ein Zeitstempel |

Warum die Leistungsliste den Aufpreis wert ist: ohne sie prüft der Services-Check nur die
Kategorien und behauptet "nothing under services", obwohl die Leistung dort steht — bei 2 von 6
Bedford-Leads passiert. **Fiele sie weg, müsste der Services-Stichpunkt mit** (28 % der Mails),
sonst behauptet die Mail Ungemessenes.

### Der GBP-Audit gegen die zwölf Sektionen des `gbp-setup`-Specs

Wie weit der Kaltlead-Audit den vollen Setup-Spec abdeckt, **ohne Mehrkosten** — nur aus dem
GBP-Scraper plus der einen DataForSEO-Abfrage. Stand 22.08.2026:

| # | Sektion (`spec.md`) | prüfbar? | Faktor | trifft zu |
|---|---|---|---|---:|
| 1 | Identity (Name, NAP, Telefon) | teilweise | fehlende Nummer/Adresse | 1 % / 33 %¹ |
| 2 | **Categories** | **ja, zweifach** | Hauptkategorie weicht ab · zu wenige gesetzt | **25 %** · 84 % |
| 3 | **Services** | **ja, zweifach** | Liste leer · unter 20 (Ziel 20–30) | 13 % · **21 %** |
| 4 | **Description** | **ja** | fehlt ganz | **99 %** |
| 5 | **Hours** | **ja** | keine 24 h · gar keine gesetzt | **49 %** · 3 % |
| 6 | **Photos** | **ja** | unter Landesmedian 14 | **39 %** |
| 7 | Attributes | nein² | — | — |
| 8 | Service area | nein | — | — |
| 9 | Products | nein | Feld nicht im Scrape | — |
| 10 | Booking link | nein | `bookingLinks` zu 100 % `None` | — |
| 11 | FAQ / Q&A | nein | Feld bei allen leer | — |
| 12 | NAP citations | nein | extern, nicht scrapebar | — |

**Sechs von zwölf Sektionen vollständig, eine teilweise.** Dazu sechs Faktoren, die der Spec
nicht als eigene Sektion führt, die aber aus denselben Daten fallen: Review-Themen gegen das
Profil (53 %), 1–2-Sterne-Bewertungen (37 %), Bewertungszahl gegen den Landesmedian (33 %), der
nächste Nachbar mit Entfernung (62 %), Googles eigene Paarung (2 %), der Kontrast aus Stärke und
Lücke (28 %). **Zusammen 20 Faktoren** (Stand 23.08.2026, `mail_audit.py` zählt sie bei jedem
Lauf nach).

**Der Landesvergleich trägt seit 23.08. drei Zahlen statt einer.** Neben Foto- und
Bewertungsmedian steht jetzt der **Leistungs-Median (24)** in `benchmark.py`, dazu der
**24-Stunden-Anteil (53 %)**. Beide lagen vorher nur als Kommentar im Quelltext und konnten
deshalb in keinem Stichpunkt stehen. Der Anlass war Lukas Befund, dass die Stichpunkt-Liste
„keinen Vergleich und keine Erklärung" trug: aus *„add more so you match more searches"* wurde
*„you list 8 services where most run 24, add more so the rest show"*. Kosten: null, die Daten
lagen im Scrape.

### Die zwei stärksten, und warum sie nichts extra kosten

**1. Welche Kategorie die Bestbewerteten führen und er nicht — greift bei 47 %.**
`spec.md` schreibt ausdrücklich *"competitor categories are NOT pulled"* und lässt sie per
WebSearch nachholen. **Bei uns fallen sie aus dem Regions-Scrape, den wir ohnehin fahren** — wir
kennen die Kategorien jedes Wettbewerbers, weil wir die ganze Region gescrapt haben. Das ist der
strukturelle Vorteil dieser Pipeline gegenüber einem Einzel-Audit, und er kostet keinen Aufruf.
Gemessen: 71 % der Leads fehlt eine Kategorie, die mindestens zwei der fünf Bestbewerteten
führen; nach Abzug generischer Sammelbegriffe ("Service establishment", "Hardware store")
bleiben 47 %. Häufigste Lücke: **"Emergency locksmith service"** bei 321 Leads.

Der Befund ist kein Mangel, sondern ein Wettbewerbsbefund: *die, die vor dir stehen, führen X.*

**2. Ein Attribut, das WEG muss — greift bei 23 %.**
`spec.md § 7`, wörtlich: *"Counter-intuitive: REMOVE 'onsite services' and 'online appointment'
attributes — they push reviews out of view on the profile."* Ob es gesetzt ist, steht in
`raw.additionalInfo`. **Es ist der einzige Rat der ganzen Mail, der etwas WEGNIMMT** — und
deshalb der wertvollste: jeder schreibt "dir fehlt etwas", niemand "nimm das weg, und zwar aus
diesem Grund". Das kann keine Vorlage.

¹ Ohne Adresse ist bei Service-Area-Betrieben der Normalfall, nicht ein Mangel — 1.798 der
Leads blenden sie bewusst aus. Kein Befund.
² `additionalInfo` ist bei 41 % gefüllt und enthält für Handwerker nur Irrelevantes
(Rollstuhlzugang, LGBTQ-freundlich). Dazu wissen wir nicht, welche Attribute für seine
Kategorie überhaupt wählbar wären — ein Rat, den er nicht umsetzen kann.

### Die sieben erlaubten Stichpunkte

Ein Finding entsteht **nur, wenn sein Feld gemessen ist**. Ein Feld, das `None` ist, erzeugt
gar nichts — nicht "fehlt", nicht "hat er nicht".

| Stichpunkt | greift bei | Quelle |
|---|---:|---|
| Review-Themen: seine eigenen Kundenworte fehlen im Profil | **72 %** | Apify Detail `reviewsTags` |
| nur 1–2 von 10 Kategorien gesetzt | **58 %** | Apify Basis `categories` |
| zeigt keine 24 Stunden | **49 %** | Apify Detail `openingHours` |
| Fotos unter dem Landesmedian 14 | **39 %** | Apify Detail `imagesCount` |
| Bewertungen unter dem Landesmedian 20 | **33 %** | Apify Basis `reviewsCount` |
| Leistungsliste gemessen und leer | **13 %** | DataForSEO `services` |
| gar keine Öffnungszeiten gesetzt | **3 %** | Apify Detail `openingHours` |

### Zwei, die RAUS sind

- **Google-Posts.** `raw.ownerUpdates` ist bei **81 %** der Leads `None`, also nie gemessen —
  nur 19 % tragen überhaupt eine Liste, und **keiner** eine nachweislich leere. "Er postet
  nicht" ist damit nirgends belegbar. Trotzdem tragen **664 Findings** eine Posts-Aussage.
- **Buchungslink.** `raw.bookingLinks` ist bei **100 %** `None`. Es gibt dazu nichts zu sagen.

### Wie verglichen wird — die eine Regel

**Jeder Vergleich geht gegen das LAND, nie gegen den Ort.** Die Landeszahlen sind über
n=4.746 gemessen: Bewertungen Median **20**, Fotos Median **14**, 24 Stunden zeigen **53 %**.

| | |
|---|---|
| **erlaubt** | `where most uk locksmiths have 20` · `your 135 reviews put you in the top 25%` |
| **verboten** | `where 4 of the 11 in town do` · `the rest of reading has 17` · `4th in bedford` |

Der Grund ist gemessen: der Scrape nahm nur Betriebe **mit Website** und suchte je Grafschaft
statt je Ort. In Bedford kennen wir 11 von 27, in Hornchurch 1 von 20. Eine Aussage über
**einen** Nachbarn hält das aus, eine über **alle im Ort** nicht — und der Inhaber kennt
seinen Ort besser als wir.

### Der Competitor-Vergleich — nur beim Namen, nie als Menge

**Ein Nachbar mit Namen ist bei 100 % der Leads verfügbar, zwei bei 99 %** (`details.nearest`,
gemessen, im Median 900 m entfernt). Das ist der stärkste Beleg, den die Mail hat: eine Zahl
kann jeder behaupten, den Namen des Nachbarn nicht.

- **In Satz 1** stehen ein bis zwei Namen plus der Ort — gebaut von `export_cohort.opener()`,
  ohne Zahl ("a few other of your competitors", nie "the other 7").
- **In einem Stichpunkt** darf **ein** Name stehen, wenn er den Verlust konkret macht
  ("so that search goes to keygen instead"). Nie eine Menge, nie ein Rang im Ort.
- **Die Position im Drei-Kasten steht in KEINER Mail mehr** (seit 22.08.). Sie ist ortsabhängig
  und in Sekunden widerlegbar: vier von vier geprüften Betrieben standen an der eigenen Tür im
  Kasten. Der Rang (bei 66 % gemessen) entscheidet nur noch, **welche** Zeilen kommen —
  außerhalb der drei zählt Sichtbarkeit, innerhalb was nach dem Klick passiert.

### Was daraus folgt, und noch nicht umgesetzt ist

**42 % aller 10.692 erzeugten Findings tragen einen Ortsvergleich** — `gbp-hours` 2.225,
`gbp-reviews-volume` 850, `gbp-posts` 664, `gbp-secondary-categories` 583, `gbp-photos` 225.
Sie sind Rohmaterial, keine Mailzeilen, aber sie verleiten zu genau dem Satz, der verboten ist.
`enrich_cohort_findings.py` muss auf den Landesvergleich umgestellt werden; bis dahin ist es
Aufgabe des Schreibers, und das ist die schwächere Absicherung.

---

## 5. Welche Findings in die Mail — die psychologische Ordnung

Drei Findings, und die Reihenfolge ist kein Zufall.

**1. Ein Positives zuerst.** Es senkt die Abwehr und es ist ehrlich: wir liefern ein Audit, keine
Mängelliste. Regel bleibt: unter zwei Positiven fällt der Block weg, er wird **nie** aufgefüllt.
Ein erfundenes Lob ist so schlimm wie ein erfundener Mangel.

**2. Dann eine Lücke, die er in fünf Sekunden selbst prüfen kann.** Am besten ein Zitat seines
eigenen Textes: *„your page title reads 'Booking Demo'"*. Das beweist, dass wir hingesehen haben,
und zwar unwiderlegbar. Eine allgemeine Aussage („Ihr SEO ist schwach") beweist nichts.

**3. Zuletzt eine Lücke mit Geldfolge.** Nicht die technisch schlimmste, sondern die, deren
Konsequenz er sofort spürt: *„jemand auf dem Handy muss deine Nummer abtippen"*.

**Warum diese Reihenfolge:** Glaubwürdigkeit, dann Beweis, dann Motivation. Umgekehrt liest sich
dieselbe Mail als Angriff.

**Harte Regeln:**
- **Spezifisch schlägt groß.** „Dein Titel sagt 'Booking Demo'" wirkt stärker als „dir fehlen
  40 Ranking-Faktoren".
- **Nie das kritisieren, worauf er stolz ist.** Wer 200 Bewertungen hat, bekommt keine Zeile
  über Bewertungen.
- **Die Lücke muss lösbar wirken.** Zu viele Probleme lähmen, sie motivieren nicht.
- **Nie unser Vokabular.** „Meta-Description" disqualifiziert einen Stichpunkt. Der Betrieb soll
  den Satz verstehen, ohne ihn zu übersetzen.
- **Mischung aus bekannt und neu.** Etwas, das er ahnt, erzeugt Zustimmung. Etwas Neues erzeugt
  Neugier. Beides zusammen erzeugt eine Antwort.

---

## 6. Wo das Modell hinkommt — und wo nicht

> **Welches Modell, und auf wessen Rechnung (27.07.2026).** Sonnet, und zwar als
> **In-Session-Subagent**, nicht über `write_mail.py`. Das ist kein Detail: `seo/CLAUDE.md`
> verbietet `anthropic.Anthropic(api_key=…)` für Copy, weil das Abo dieselbe Arbeit schon
> bezahlt. `write_mail.py` verletzt diese Regel und ist damit der Ausnahme-, nicht der
> Regelpfad. Subagenten laufen auf dem Abo.
>
> **Welche Blöcke.** Nur 4 und 5 (`markt_copy.md` § Rahmen). Am 27.07. wurden beide
> versehentlich deterministisch nachgebaut (`read_block.py`, `bullet()` in
> `enrich_cohort_findings.py`), weil dessen Docstring „VARIANTE B BRAUCHT KEIN MODELL"
> behauptete. Das widersprach dem festgelegten Rahmen. Die elf von Luka abgenommenen
> Mails waren modellgeschrieben — die deterministische Fassung ist kein abgenommener Ersatz.

**Nicht:** Prüfen, messen, urteilen. Ein Title-Tag zu lesen ist keine Sprachaufgabe. Ein Parser
liest ihn zu 100% richtig, ein Modell zu vielleicht 95, und die fehlenden 5% sind eine
Falschaussage an einen Fremden. Bei 1.000 Empfängern sind das 50 Betriebe.

**Doch:** Formulieren. Das Modell bekommt fertige `fact`/`means`-Paare und schreibt daraus einen
Absatz in Lukas Stimme. Es darf **nichts** hinzufügen, was nicht in den Paaren steht.

**Der Prompt-Vertrag:**
- Eingabe: 3 Findings mit `fact`, `means`, `kind`, plus Firmenname und Ort
- Ausgabe: Anrede, Markt-Aussage, 3 Stichpunkte, CTA
- Verboten: neue Zahlen, neue Behauptungen, Em-Dashes, Fachbegriffe
- Jeder Stichpunkt: sofort verständlich und benennt eine Folge

Ein Nachprüfer sollte gegenlesen, dass jede Zahl in der fertigen Mail in den Eingabe-Findings
vorkommt. Das ist dieselbe Idee wie `verify.py` im Report-Pfad und steht noch aus.

---

## 6b. Wenn die „Website" gar keine ist

**Gemessen:** 127 der 7.291 Places (2%) verweisen auf ein fremdes Profil statt auf eine eigene
Seite — 68 auf Facebook, dazu Wix-Subdomains, Instagram, `sites.google.com`, `yell.com`.

**Facebook-Seiten sind meist lesbar** (3 von 4 ohne Login-Wall, 6.000 bis 14.500 Wörter). Genau
das ist die Falle: der Auditor läuft durch und liefert selbstbewussten Unsinn. Ein echter Lauf
gegen `facebook.com/arcadecobbler` erzeugte fünf Findings, alle falsch — er zitierte Facebooks
Seitentitel als deren eigenen, vermisste LocalBusiness-Markup auf Facebook, und warf einem
Schuhmacher in Sleaford vor, sein Titel nenne nicht „locksmith Leicester".

**Regel:** `is_own_site(url)` in `web_findings.py` fängt das ab. Ein Social- oder Verzeichnis-Host
erzeugt **genau ein** Finding und keine Website-Prüfung:

> „your Google profile sends people to facebook.com instead of your own site"
> → *you cannot rank a page you do not own, and whoever does rank takes the call*

Stärke 98, also führend. Für eine Agentur, die Websites baut, ist das der klarste Pitch überhaupt:
kein Mangel an einer Seite, sondern eine fehlende Seite.

**Strategisch offen:** `seo_scrape_adaptive.py:102` wirft Betriebe **ohne jede Website** schon beim
Scrape raus (`--keep-no-website` behält sie, laut Hilfe „+25% Scrape-Kosten, der Website-Finder
holt ~30% zurück"). Wir sehen dieses Segment also gar nicht. Das ist eine Entscheidung wert: wer
keine Website hat, ist für ein Website-Angebot der beste Lead, den es gibt, und braucht nur einen
anderen Pitch. Über diese Leads wissen wir weiterhin genug — bei den 127 Ersatz-Fällen sind
Kategorien zu 100%, Öffnungszeiten zu 98%, Fotos zu 98% und Bewertungen zu 92% belegt.

---

## 7. Kein Website-Ergebnis — was dann

Nach Stufe B bleibt ein Rest ohne verwertbares HTML. Für den gilt:

1. **Kein Website-Finding erzeugen.** Nicht raten, nicht mit einem Standard füllen.
2. Die Mail läuft auf **GBP-Findings**, die für jeden Lead da sind (25 von 27 Prüfpunkten sind
   automatisch messbar).
3. Ist auch das GBP dünn, gehört der Lead nicht in die Kampagne. Eine Mail ohne konkreten
   Befund ist eine Vorlage, und Vorlagen bekommen keine Antworten.

`web_findings.evaluate("")` gibt eine leere Liste zurück. Das ist die erste Zusicherung im
Selbstcheck und der Grund, warum diese Regel nicht vergessen werden kann.

---

## 8. Wo die Personalisierung liegt

**In der Datenbank, nicht in einer Datei.** `export_cohort.py` baut `cohort_vars.csv` bei
jedem Lauf neu aus Supabase. Eine Anreicherung, die nur in der CSV steht, ist beim nächsten
Export weg — genau das wäre passiert.

Die Findings liegen deshalb in `industry_operators.web_signals` (JSONB, war leer, keine
Migration nötig):

```
{ "good": [...], "gaps": [...], "site_finding": "...", "findings": [...], "built": "2026-07-27" }
```

Der Weg ist eine Richtung, immer dieselbe:

```
scrape → industry_operators           run_campaign.py
enrich → web_signals                  enrich_cohort_findings.py --push --apply
export → cohort_vars.csv              export_cohort.py
senden → Instantly                    (CSV-Upload, Spalten = Variablen)
```

Was als Variable in Instantly ankommt, je Lead:

| Spalte | Inhalt |
|---|---|
| `subject` | die fertige Betreffzeile, je Lead verschieden (siehe `markt_copy.md`) |
| `company_casual` · `town_casual` | fertige Anrede und Ort, nicht der Rohname |
| `good_1` · `good_2` | was gut läuft, stärkstes zuerst |
| `gap_1` · `gap_2` · `gap_3` | die drei Lücken in psychologischer Reihenfolge |
| `competitor_1/2` (+ `_km`) · `market_count` | der Marktbezug |
| `findings_json` | alle Bausteine, für die Prosa-Variante A |

Leer bleibt leer. Ein Lead ohne dritten Befund bekommt `gap_3 = ""` und eine Mail mit zwei
Stichpunkten — nie einen aufgefüllten Standardsatz.

**Variante B braucht kein Modell.** Die Stichpunkte sind `fact` + `", so "` + `means`, also
mechanisch. Nur die Prosa von Variante A geht durch Haiku, und auch die bekommt nur fertige
Paare und darf nichts hinzufügen.

**Ohne Ort:** 1.798 von 4.277 Schlüsseldiensten haben bei Google keine Adresse — Service-Area-
Betriebe, bei denen `city`, `street` und `address` allesamt leer sind. Der Ort ist nicht
verloren gegangen, es gibt ihn nicht. Rückfall ist die Suchregion, denn dort arbeiten sie.

---

## 9. Was in die Mail kommt, und was nicht

**Was gemessen wurde, wird gesagt. Was nicht gemessen wurde, wird zum Grund für den Report.**

Eine Behauptung über ein Feld, das der Scrape nicht gezogen hat, ist der teuerste Fehler in
der ganzen Kette: der Empfänger widerlegt sie in zehn Sekunden. Deshalb `score.limits()` —
die ungeprüften Punkte stehen als eigene Zeile in der Mail, in seiner Sprache, und genau
diese Lücke schließt der Report.

Belegt, warum das nötig war: acht von 24 Bedford-Places tragen eine Profil-Beschreibung, und
**alle acht sind Timpson-Filialen.** Ob die anderen 16 keine haben oder das Feld im
Kurz-Scrape fehlt, ist daran nicht zu entscheiden. Also wird es nicht behauptet.

**Zwei Punkte je Seite, jeder eine Lage.** Fünf Einzelbefunde lesen sich wie eine Prüfliste;
zwei Sätze, die je mehrere Beobachtungen zu einer Lage bündeln, lesen sich wie jemand, der
verstanden hat. Gebündelt wird nach Thema (`themes.py`) — *werde ich gefunden* · *trauen die
mir zu* · *erreicht mich jemand* — nicht nach unserer Bereichseinteilung. Gedeckelt auf
26 Wörter.

**Die Mail nennt WAS und WAS ES KOSTET, nie WIE.** Das Wie ist der Report. Steht die Lösung
schon in der Kaltmail, gibt es keinen Grund mehr zu antworten.

**Scores mit Faktorenzahl.** „88 von 100" ist eine Behauptung, „88 von 100 über 7 Faktoren"
eine Rechnung, nach der man fragen kann. Unter **sieben** gemessenen Faktoren gibt es gar keine
Zahl (`gbp_score.MINDESTENS`, von fünf angehoben am 22.08.), und eine
glatte 100 wird als Satz gesagt statt als Zahl geschickt — eine 100 in einer Mail, die etwas
finden will, arbeitet gegen sie.

| | im ersten Audit | im Plattform-Katalog |
|---|---|---|
| Google-Profil | 5 bis 8 (je nach Detailseite) | 27 |
| Website | 12 | 23 |
| SEO · AI · Technik | 0 | 23 |

**Wenn nur Technik übrig bleibt, wird nicht versendet.** `score.needs_deeper()` markiert
Betriebe, deren restliche Lücken keinen Auftrag benennen. Gemessen in Bedford: 2 von 12, und
es waren die zwei bestaufgestellten — ihre Mails waren wortgleich identisch. Die gehören in
einen Ranking-Zug (DataForSEO), nicht in den Standardversand. Es sind wenige, und es sind die,
bei denen sich die Kosten lohnen.

---

## Offene Punkte

- **`dedupe_leads.py` in `run_campaign.py` einhängen** — vor Stufe 4 (Kontakt), damit
  MillionVerifier keine Adressen für die 3.369 Zeilen prüft, die ohnehin wegfallen. Das Modul
  steht und ist getestet, es läuft nur noch von Hand.
- **Maps-Spam als eigener Filter?** Billige TLD plus viele Standorte plus generischer Name
  (siehe § 2). Fällt derzeit zufällig durch den Kettenfilter.
- **Der Nachprüfer für die generierte Mail** fehlt (siehe § 6).
- **Firecrawl-Fallback** ist getestet, aber noch nicht verdrahtet.
- **`--details on`** muss im Kampagnen-Ablauf verbindlich werden, nicht per Flag wählbar bleiben.
- **`web-own-site` fehlt im Prüfkatalog.** Die ID wird von `web_findings.py` benutzt, steht aber
  nicht in `playbook/checklists/audit-checklist.json`. Damit kann Mail und Report zu diesem Punkt
  auseinanderlaufen, und genau das sollen geteilte IDs verhindern. Nachtragen.
- **Segment „ohne Website"** ist eine Geschäftsentscheidung, keine technische (siehe § 6b).
