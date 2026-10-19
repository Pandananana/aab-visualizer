# /// script
# requires-python = ">=3.11"
# ///
"""Merge parsed rows + geocoded departments and write ../kort.html from the template."""
import json, re
from datetime import date
from collections import defaultdict

def category(variant):
    """Collapse the free-text boliggruppe suffix into a filterable type.

    Some suffixes are just the department's own street names, not a housing
    type – those are plain family flats and are kept as the note only.
    """
    v = (variant or "").lower()
    if "rækkehus" in v and "2 plan" in v:
        return "Rækkehus, 2 plan"
    if "rækkehus" in v:
        return "Rækkehus"
    if "dobbelthus" in v:
        return "Dobbelthus"
    if "midlertidig" in v:
        return "Midlertidig udlejning"
    if "ekstra faciliteter" in v:
        return "Ekstra faciliteter"
    return "Etagebolig"


rows = json.load(open("rows.json"))
afd = {a["afd_nr"]: a for a in json.load(open("afdelinger.json"))}

# Nudge apart departments that resolved to the exact same address.
seen = defaultdict(list)
for a in afd.values():
    seen[(round(a["lat"], 6), round(a["lon"], 6))].append(a)
for group in seen.values():
    if len(group) > 1:
        for i, a in enumerate(sorted(group, key=lambda x: x["afd_nr"])[1:], 1):
            a["lat"] += 0.00022 * i
            a["lon"] += 0.00035 * i
            a["geo_note"] = ((a.get("geo_note") or "")
                             + " Markøren er rykket en anelse for ikke at dække"
                               " en anden afdeling på samme adresse.").strip()

places = []
for nr, a in sorted(afd.items()):
    mine = [r for r in rows if r["afd_nr"] == nr]
    groups = sorted(
        [dict(placement=r["placement"], raw=r["placement_raw"], rooms=r["rooms"],
              rooms_raw=r["rooms_raw"], rooms_max=r["rooms_max"],
              variant=r["variant"], cat=category(r["variant"]), type=r["boligtype"], rent=r["husleje"], rent_min=r["rent_min"],
              rent_max=r["rent_max"], area=r["areal"], area_min=r["area_min"],
              area_max=r["area_max"], floor=r["etage"], matches=r["matches"])
         for r in mine],
        key=lambda g: (g["placement"] is None, g["placement"] or 0))
    places.append(dict(
        id=a["afd_id"], nr=nr, name=a["afd_navn"], omraade=a["omraade"],
        lat=round(a["lat"], 6), lon=round(a["lon"], 6),
        geo=a["geo_label"], geo_src=a["geo_source"], conf=a["geo_conf"],
        note=a.get("geo_note"), office=a.get("office_addr"), groups=groups))

# Waiting-list number from the user's own export; only ends up in the local kort.html.
vl = re.search(r"Ventelistenummer\s*([\d-]+)", open("../placeringer.html", encoding="utf-8").read())
data = dict(
    generated=date.today().isoformat(),
    venteliste=vl.group(1) if vl else None,
    source="Boligforeningen AAB – placeringsliste",
    places=places,
)
payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
open("map_data.json", "w").write(payload)
html = open("../kort.template.html", encoding="utf-8").read().replace("__PAYLOAD__", payload)
open("../kort.html", "w", encoding="utf-8").write(html)

n = sum(len(p["groups"]) for p in places)
act = [g["placement"] for p in places for g in p["groups"] if g["placement"]]
print(f"{len(places)} afdelinger, {n} opnoteringer, placering {min(act)}–{max(act)}")
print("værelser:", sorted({g["rooms"] for p in places for g in p["groups"]},
                          key=lambda x: (x is None, x)))
print("typer:", sorted({g["cat"] for p in places for g in p["groups"]}))
