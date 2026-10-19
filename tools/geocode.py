# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///
"""Geocode AAB departments.

Coordinates for every AAB department are committed in afdeling_geo.json, so a
normal run is just a lookup. Departments missing from it are geocoded with
OpenStreetMap Nominatim and cached in geocache.json.

Two independent sources are combined:
  1. the department's own street name                 -> street search
  2. the department office address from aab.dk        -> address search

A local office address is a precise point, so it wins whenever it looks
credible (same street as the department, or within 1.5 km of the street).
Otherwise the street is used. AAB's head office is not a department address
and is ignored.

    uv run geocode.py         # rows.json -> afdelinger.json
    uv run geocode.py --all   # add every department in aab_addr.json to afdeling_geo.json
"""
import json, os, re, math, sys, time, unicodedata
import httpx

NOMINATIM = "https://nominatim.openstreetmap.org/search"
HQ = "Havneholmen 21"                       # AAB head office, not a department
GEO = "afdeling_geo.json"
CACHE = "geocache.json"
# Every AAB department sits in Region Hovedstaden; used to throw away
# same-named streets elsewhere in the country (Bellahøj in Kolding, Egegade in Aarhus, ...).
REGION_H_BOX = "11.85,56.15,12.75,55.45"    # lon1,lat1,lon2,lat2
MANUAL = {
    # department -> (address to geocode, note) for cases neither source resolves
    90: ("Egedal Centret 1, 3660 Stenløse",
         "Kun område kendt (Stenløse Syd, Egedal) – markør sat ved Stenløse centrum"),
}
FIELDS = ("lat", "lon", "geo_label", "geo_source", "geo_conf", "geo_note",
          "office_addr", "street_label")

c = httpx.Client(timeout=30, headers={
    "User-Agent": "aab-visualizer (https://github.com/Pandananana/aab-visualizer)"})
_cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
_last = 0.0

def search(**params):
    """Nominatim search, cached on disk and throttled to its 1 request/second policy."""
    global _last
    params = dict(format="jsonv2", addressdetails=1, countrycodes="dk",
                  viewbox=REGION_H_BOX, bounded=1, **params)
    key = json.dumps(params, sort_keys=True, ensure_ascii=False)
    if key in _cache:
        return _cache[key]
    for attempt in range(3):
        time.sleep(max(0, _last + 1.1 - time.time()))
        _last = time.time()
        try:
            r = c.get(NOMINATIM, params=params)
            r.raise_for_status()
            _cache[key] = r.json()
            return _cache[key]
        except Exception as e:
            if attempt == 2 or (isinstance(e, httpx.HTTPStatusError) and e.response.status_code < 500):
                print("  ! fail", params.get("q") or params, e, file=sys.stderr)
                return []

def dist(a, b):
    (lon1, lat1), (lon2, lat2) = a, b
    p = math.pi / 180
    h = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 12742000 * math.asin(math.sqrt(h))

def norm(s):
    """Loose street-name key: 'Lersø Park Allé' == 'Lersø Parkallé', 'Jakobsens' == 'Jacobsens'."""
    s = unicodedata.normalize("NFKD", s.lower())
    s = s.replace("æ", "ae").replace("ø", "o").replace("å", "aa")
    s = re.sub(r"[^a-z]", "", s)
    for a, b in (("boulevard", "blvd"), ("sdr", "sonder"), ("edv", "edvard"), ("k", "c")):
        s = s.replace(a, b)
    return s

def spellings(name):
    """The spellings AAB uses next to the official one: 'Carl Jakobsens Vej', 'Peter Bangsvej', 'Sdr.'..."""
    out = [name]
    for a, b in (("Alle", "Allé"), ("Allé", "Alle"), ("Sdr.", "Sønder"), ("Edv.", "Edvard"),
                 ("Jakob", "Jacob")):
        if a in name:
            out.append(name.replace(a, b))
    for v in list(out):                   # 'Carl Jacobsensvej' -> 'Carl Jacobsens Vej'
        if m := re.match(r"(.*\S)(vej|gade|allé|alle)\b(.*)$", v):
            out.append(f"{m.group(1)} {m.group(2).capitalize()}{m.group(3)}")
    return list(dict.fromkeys(out))

def kommune(addr):
    k = addr.get("municipality") or addr.get("city") or addr.get("town") or ""
    return k.replace("Københavns Kommune", "København Kommune")

def geocode_address(betegnelse):
    """'Nyelandsvej 57, st. th, 2000 Frederiksberg' -> point at the house number."""
    parts = [p.strip() for p in betegnelse.split(",") if p.strip()]
    street, postby = parts[0], parts[-1]
    for variant in spellings(street):
        for hit in search(q=f"{variant}, {postby}", limit=1):
            a = hit["address"]
            if a.get("house_number") and a.get("road"):
                return {"lon": float(hit["lon"]), "lat": float(hit["lat"]),
                        "label": f"{a['road']} {a['house_number'].replace(' ', '')}, {postby}",
                        "vejnavn": a["road"]}
    return None

def street_candidates(name):
    """Street segments with this name in Region Hovedstaden, one per municipality."""
    out, seen = [], set()
    hits = []
    for variant in spellings(name):
        hits = search(q=variant, limit=20)
        if hits:
            break
    for hit in hits:
        a = hit["address"]
        if hit.get("category") != "highway" or norm(a.get("road", "")) != norm(name):
            continue
        k = kommune(a)
        if k in seen:
            continue
        seen.add(k)
        out.append({"lon": float(hit["lon"]), "lat": float(hit["lat"]),
                    "label": f"{a['road']}, {k}", "vejnavn": a["road"]})
    return out

def locate(nr, name, office_raw):
    is_hq = bool(office_raw and office_raw.startswith(HQ))
    office = geocode_address(office_raw) if (office_raw and not is_hq) else None

    base = re.sub(r"\s*\d.*$", "", re.split(r"[/,]", name)[0]).strip()
    cands = street_candidates(base) if base else []
    street = None
    if cands:
        street = (min(cands, key=lambda v: dist((v["lon"], v["lat"]),
                                                (office["lon"], office["lat"])))
                  if office else (cands[0] if len(cands) == 1 else None))

    chosen = src = note = None
    if office:
        chosen = office
        if street:
            d = dist((office["lon"], office["lat"]), (street["lon"], street["lat"]))
            same = norm(office["vejnavn"]) == norm(street["vejnavn"])
            src = ("kontor på afdelingens vej" if same else "afdelingskontor nær vejen")
            if not same and d > 1500:
                src = "afdelingskontor"
                note = (f"Afdelingens vej ({street['vejnavn']}) ligger "
                        f"{d/1000:.1f} km herfra – markøren viser kontoret")
        else:
            src = "afdelingskontor"
    elif street:
        chosen, src = street, "vejmidte"
    elif nr in MANUAL:
        chosen = geocode_address(MANUAL[nr][0])
        src, note = "manuel", MANUAL[nr][1]

    conf = ("high" if src in ("kontor på afdelingens vej", "afdelingskontor nær vejen")
            else "medium" if src in ("afdelingskontor", "vejmidte")
            else "low")
    return dict(lat=chosen["lat"] if chosen else None,
                lon=chosen["lon"] if chosen else None,
                geo_label=chosen["label"] if chosen else None,
                geo_source=src, geo_conf=conf, geo_note=note,
                office_addr=None if is_hq else office_raw,
                street_label=street["label"] if street else None)

aab = json.load(open("aab_addr.json"))
geo = json.load(open(GEO)) if os.path.exists(GEO) else {}

def office_of(nr):
    entry = aab.get(str(nr))
    return entry["addr"].replace(" | ", ", ") if entry else None

if "--all" in sys.argv:
    for k, entry in sorted(aab.items(), key=lambda kv: int(kv[0])):
        if k in geo or "ANONYM" in entry["addr"]:
            continue
        g = locate(int(k), entry["title"].split(" - ", 1)[-1], office_of(k))
        geo[k] = g
        print(f"{k:>6} {g['geo_conf']:<6} {g['geo_source'] or 'NONE':<32} {g['geo_label']}")
    json.dump(dict(sorted(geo.items(), key=lambda kv: int(kv[0]))), open(GEO, "w"),
              ensure_ascii=False, indent=1)
    json.dump(_cache, open(CACHE, "w"), ensure_ascii=False)
    sys.exit()

rows = json.load(open("rows.json"))
afd = {}
for r in rows:
    afd.setdefault(r["afd_nr"], {"afd_nr": r["afd_nr"], "afd_id": r["afd_id"],
                                 "afd_navn": r["afd_navn"], "omraade": r["omraade"]})

for nr in sorted(afd):
    a = afd[nr]
    g = geo.get(str(nr))
    if not g:                             # not in the committed table: look it up
        g = locate(nr, a["afd_navn"], office_of(nr))
        print(f"{a['afd_id']:>6} {a['afd_navn'][:30]:<30} {g['geo_conf']:<6} "
              f"{g['geo_source'] or 'NONE':<32} {g['geo_label']}")
    a.update({k: g[k] for k in FIELDS})

json.dump(list(afd.values()), open("afdelinger.json", "w"), ensure_ascii=False, indent=1)
json.dump(_cache, open(CACHE, "w"), ensure_ascii=False)
miss = [a["afd_id"] for a in afd.values() if a["lat"] is None]
print(f"{len(afd)} afdelinger | uden koordinat: {miss or 'ingen'}")
