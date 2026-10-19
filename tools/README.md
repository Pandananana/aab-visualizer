# Datapipeline bag kort.html

Kortet bygges lokalt ud fra din egen placeringsliste. Repoet indeholder ingen
persondata – kun skabelonen `../kort.template.html`, scripts og AAB's offentlige
kontoradresser.

Kilder:

* `../placeringer.html` – "Mine boligønsker" fra AAB's selvbetjening. Log ind,
  åbn siden med dine boligønsker og gem den (Gem som… → "Webside, kun HTML")
  som `placeringer.html` i repoets rod. Filen er gitignored.
* `https://aab.dk/beboer/kontakt-din-afdeling/` – afdelingskontorernes adresser
  (hentet én gang til `aab_addr.json`).
* `afdeling_geo.json` – koordinater for alle AAB's afdelinger (offentlige
  data). Afdelinger der mangler heri, geokodes med OpenStreetMap Nominatim
  (åbent, ingen nøgle, max 1 kald/sek.) og caches i `geocache.json`.

Kør fra repoets rod (kræver `uv`):

```
./build.sh
```

som kører trinene i rækkefølge:

```
uv run parse.py     # placeringer.html -> rows.json
uv run geocode.py   # rows.json        -> afdelinger.json (afdelinger m. koordinater)
uv run build.py     # begge            -> map_data.json + ../kort.html
```

Åbn derefter `../kort.html` i en browser. `rows.json`, `afdelinger.json`,
`map_data.json` og `kort.html` indeholder dine placeringer og er gitignored.

## Geokodning

`uv run geocode.py --all` tilføjer alle afdelinger fra `aab_addr.json`, der
mangler i `afdeling_geo.json` (fx hvis AAB får nye afdelinger).

Tabellen blev oprindeligt bygget med DAWA, som er lukket (svarer `410 Gone`).
Hver afdeling har to mulige positioner: afdelingens eget vejnavn fra
placeringslisten, og afdelingskontorets adresse fra aab.dk. Kontoradressen er et
præcist punkt og vinder, når den ser troværdig ud; ellers bruges vejmidten.
AAB's hovedkontor (Havneholmen 21) tæller ikke som afdelingsadresse.

`conf` i data:

* `high` – kontoret ligger på eller tæt ved afdelingens vej
* `medium` – kontoradresse eller vejmidte uden krydsbekræftelse
* `low` – kun område kendt (se `MANUAL` i `geocode.py`)

## Baggrundskort

Esri ArcGIS Online (`server.arcgisonline.com`) – ingen API-nøgle og ingen
Referer påkrævet, så `kort.html` virker direkte fra `file://`. OpenStreetMaps
egne fliser blev fravalgt: deres brugspolitik afviser kald uden Referer, hvilket
er præcis det en lokal HTML-fil sender.

* zoom ≤ 16: World Light/Dark Gray Canvas + matchende navnelag
* zoom ≥ 17: World Street Map (dæmpet med et CSS-filter)
