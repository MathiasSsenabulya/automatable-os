# Apify oder Outscraper — gemessen, nicht gelesen

Stand 23.08.2026. Alle Zahlen aus eigenen Läufen am selben Tag, dieselbe Branche
(Schlüsseldienste), dasselbe Land (Neuseeland). Die Outscraper-Läufe zusammen 268
Datensätze und damit innerhalb der kostenlosen ersten 500.

## Das Ergebnis in einer Tabelle

| Weg | Treffer | Kosten |
|---|---|---|
| Outscraper, Land als Suchanfrage (API) | 70 | frei |
| Outscraper, Land als Suchanfrage (Plattform-Modus, `ui=true`) | 93 | frei |
| **Apify, Land als Gebiet** | **330** | 1,65 $ |
| Outscraper, nur Auckland | **105** | frei |
| Apify, nur Auckland (automatisches Stadtpolygon) | 17 | 0,09 $ |

## Was daraus folgt

**Apify rastert eine Fläche selbst, Outscraper nicht.** Gibt man Apify ein Gebiet — ein
County, ein Bundesland, ein ganzes Land — legt es selbst ein Raster darüber und sucht Kachel
für Kachel ab. Outscraper nimmt eine Suchanfrage und gibt zurück, was Google dafür hergibt.
Deshalb 330 gegen 70.

**Outscrapers Marketing behauptet inzwischen, der Plattform-Modus rastere doch selbst.** Das
ist geprüft und stimmt nicht: `ui=true` gab 93 statt 70, nicht die Hunderte, die ein Raster
liefern würde. Die eigene API-Doku und ihr Postleitzahlen-Tutorial sagen das Gegenteil des
Marketings, und der Test entscheidet für die Doku.

**Pro einzelnem Ort ist Outscraper deutlich besser.** 105 Betriebe in Auckland gegen Apifys
17. Der Grund liegt bei Apify: sein automatisches Stadtpolygon hört an der Stadtgrenze auf
und lässt die Agglomeration weg — der Actor warnt in seiner eigenen Doku davor.

**Der Weg für Outscraper wäre deshalb eine Städteliste plus Batching** (bis 1.000 Anfragen je
Request, Entdoppeln inklusive). Die Liste läge bereit: `build_regions.py` lädt GeoNames'
`cities15000`, und daraus liesse sich statt einer Regionsliste eine Städteliste bauen. Für
Neuseeland wären das 58 Städte über 15.000 Einwohner. **Was dabei herauskäme, ist nicht
gemessen** — Auckland hochzurechnen wäre geraten, weil kleine Städte steil abfallen. Ein
Lauf über alle 58 kostet geschätzt 3 bis 6 Dollar und wäre die endgültige Antwort.

## Die Felder, über alle 70 Betriebe des Landlaufs geprüft

| Feld (Outscraper-Name) | gefüllt | im Score |
|---|---|---|
| `subtypes` (alle Kategorien) | 100 % | ✓ zwei Faktoren |
| `phone` | 100 % | — |
| `photos_count` | 98 % | ✓ |
| `reviews_per_score` (Sterne einzeln) | 98 % | ✓ |
| `working_hours` | 97 % | ✓ zwei Faktoren |
| `website` | 91 % | — |
| `about` (Google-Attribute) | 74 % | — |
| **`description`** (Profiltext) | **0 %** | **✓ fehlt** |
| **`reviews_tags`** (Google-Schlagworte) | **0 %** | **✓ fehlt** |

Zwei der zwölf Score-Faktoren kommen im Basislauf also nicht. Ob ein Zusatzparameter sie
holt, ist offen.

**Kein `services`-Feld, in der ganzen API nicht.** Auch kein `menu`, `products` oder
`offerings`. Die Leistungsliste — bei Schlüsseldiensten im Median 24 Einträge, ein eigener
Score-Faktor — bleibt DataForSEO. Das ist kein Problem: `dfs_listings.py` holt sie für
0,37 $ je 1.000 Betriebe und ist damit der billigste Schritt der ganzen Pipeline.
Outscrapers `about` ist NICHT dasselbe: das sind Attribute wie „Lieferung" oder
„Rollstuhlzugang", nicht die Leistungen.

## Preise

| | Apify | Outscraper |
|---|---|---|
| Basis | 1,70 $/1.000 (gemessen) | 3 $/1.000, erste 500 frei |
| mit Detailseite + Kontakten | ~5,70 $/1.000 | + 3 $/1.000 je Anreicherung |
| ab 100.000 Datensätzen | unverändert | **1 $/1.000** |

In der Masse wird Outscraper also billiger — aber erst jenseits von 100.000.

## Was Outscraper zusätzlich kann

Mehrere unserer Pipeline-Schritte gibt es dort als fertigen Dienst:

| Ihr Dienst | Ersetzt bei uns |
|---|---|
| `ai_chain_info` | die Ketten-Erkennung, immerhin −24 % im Trichter |
| `company_websites_finder` | Teil von `recover_emails.py` |
| `leads_n_contacts` | die Firecrawl-Mailsuche |
| `emails_validator_service` | MillionVerifier |
| Filter `only_with_website`, `verified`, `operational_only` | würde vor dem Bezahlen filtern statt danach |

Dazu eine **Business Data API** (`POST /businesses`, `businesses/similar/{domain}`) — eine
fertige Firmendatenbank statt eines Live-Scrapes. Ungeprüft.

## Der Vorbehalt aus eigener Erfahrung

`leads_n_contacts` ist genau der Dienst, der im Juni 2026 bei rund 9.000 australischen
Betrieben häufig die Adresse einer **fremden Firma** lieferte — bei einem Poolbauer die einer
Finanzberatung. Ihre eigene Zustellbarkeitsprüfung fällt darauf herein, weil das fremde
Postfach existiert. Nichts deutet darauf hin, dass das behoben ist.

**Korrektur zur damaligen Notiz:** Das Website-Feld heisst in der **API** `website`. Das
`site`, an dem es damals brach, ist der Spaltenname im CSV-Export der Oberfläche. Wer die API
nutzt, hat ein anderes Mapping als wer den Export nutzt — und genau dort lag der Fehler.

## Nachtrag: die Landanfrage bei Outscraper, an einem zweiten Land geprüft

Neuseeland ist klein — deshalb dieselbe Anfrage nochmal gegen ein Land, dessen Wahrheit wir
kennen.

| | Outscraper, eine Landanfrage | Apify |
|---|---|---|
| Neuseeland | 70 | 330 |
| **Vereinigtes Königreich** | **141** | **4.746** |

34-mal weniger. Dazu ein Warnsignal: unter den 141 UK-Treffern standen vier aus **New York**.
Die Doku erklärt es selbst — „die IP-Adressen unserer Server liegen möglicherweise in anderen
Ländern", weshalb der Ort in den Suchtext gehört.

**Der Widerspruch zur Erfahrung des Nutzers löst sich an der Grenze zwischen Oberfläche und
API.** In der Weboberfläche liegt eine fertige Auswahlliste aus Ländern, Regionen und Städten
bereit, und Outscraper bildet daraus das Kreuzprodukt: „Categories will be combined into
Google search queries by multiplying with the locations." Wer dort ein Land anklickt, bekommt
seine mehreren tausend. **An der API gibt es diese Liste nicht** — kein `locations`-Parameter,
nur der Verweis auf die Weboberfläche. Für eine Pipeline, die ohne Menschen davor läuft, zählt
die API.

## Der eigentliche Fund: DataForSEO kann den ganzen Scrape

Geprüft am 23.08.2026, dieselbe Branche, dasselbe Land, ein einziger Aufruf über
`business_data/business_listings/search/live`:

| | Treffer | Preis je 1.000 |
|---|---|---|
| **DataForSEO** | **246** (`total_count` 246, also kein Deckel) | **0,41 $** |
| Apify, gefiltert auf „mit Website" | 330 | ~5 $ |
| Outscraper | 70 | 3 $ |

Und es liefert **alle zwölf Score-Faktoren in einem Aufruf**, auch die beiden, die Outscraper
gar nicht hat:

| Feld | DataForSEO | Outscraper |
|---|---|---|
| Kategorien | 100 % | 100 % |
| `rating_distribution` | 93 % | 98 % |
| `total_photos` | 97 % | 98 % |
| `work_time` | 92 % | 97 % |
| `description` | **73 %** | **0 %** |
| `place_topics` (Bewertungs-Themen) | **75 %** | **0 %** |
| `services` (Median 25 Einträge) | **27 %** | **fehlt ganz** |

Der Median von 25 Leistungen deckt sich mit den 24 aus dem UK-Lauf — es ist dieselbe Quelle,
die `dfs_listings.py` heute schon anzapft, nur als separater zweiter Schritt.

**Zwei Gründe, warum es Apify trotzdem nicht ersetzt:**

1. **E-Mails: 25 %** gegen Apifys rund 70 % vom Profil. Das Feld heisst übrigens `mail`, nicht
   `email`, und die Quelle sind Backlinks. Der Unterschied ist der zwischen 2.500 und 900
   anschreibbaren Betrieben.
2. **Frische: Median 110 Tage**, ältester Datensatz 1.074 Tage, nur 23 von 246 jünger als ein
   Monat. Für Öffnungszeiten und Kategorien egal, für Bewertungszahlen fatal — und die
   Bewertungszahl ist der stärkste Satz in der Mail.

## Empfehlung

**Die bestehende Architektur ist bereits die richtige, und jetzt ist auch belegt warum.**
Apify macht den Scrape, weil es frisch ist, die Fläche selbst rastert und die Mailadressen
mitbringt. DataForSEO zieht die Leistungsliste nach, weil sie dort für 0,41 $/1.000 liegt und
ein träges Feld ist, bei dem 110 Tage nichts ausmachen. Outscraper passt in keine der beiden
Rollen.

**Wo Outscraper trotzdem eine Prüfung verdient:** dichte Ballungsräume, wo es sechsmal so viel
findet wie Apifys automatisches Stadtpolygon (Auckland 105 gegen 17), und sehr grosse Mengen
jenseits von 100.000 Datensätzen, wo der Preis auf 1 $/1.000 fällt. Der Testlauf über eine
Städteliste steht aus und würde für UK rund 9 bis 18 Dollar kosten.

**Ein Feld sollte man sich trotzdem holen:** `place_topics` aus DataForSEO ersetzt Apifys
`reviewsTags`, für die dort die Detailseite mit +2 $/1.000 fällig wird. Bei 75 % Abdeckung und
0,41 $/1.000 ist das eine der wenigen Stellen, an denen ein Wechsel sofort Geld spart.
