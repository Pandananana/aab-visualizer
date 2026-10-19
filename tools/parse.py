# /// script
# requires-python = ">=3.11"
# dependencies = ["beautifulsoup4", "lxml"]
# ///
import json, re
from bs4 import BeautifulSoup

soup = BeautifulSoup(open('../placeringer.html', encoding='utf-8'), 'lxml')

def txt(el):
    return re.sub(r'\s+', ' ', el.get_text(' ', strip=True)).strip()

rows = []
for tr in soup.select('tr[data-lejemaalgruppe-id]'):
    tds = tr.find_all('td', recursive=False)
    pl_td = tr.find('td', attrs={'data-opnotering-id': True})
    if not pl_td:
        continue
    pl_raw = txt(pl_td)
    placement = int(re.sub(r'\D', '', pl_raw)) if re.search(r'\d', pl_raw) else None
    i = tds.index(pl_td)
    afd_td, grp_td = tds[i+1], tds[i+2]

    afd_raw = txt(afd_td)
    m = re.match(r'Afdeling\s+(\d[\d-]*?)\s+-\s+(.*?)\s*Område:\s*(.*)$', afd_raw)
    afd_id = m.group(1) if m else None
    afd_nr = int(afd_id.split('-')[0]) if afd_id else None
    afd_navn = m.group(2).strip() if m else afd_raw
    omraade = m.group(3).strip() if m else ''

    grp = re.sub(r'\s*Boligforeningen AAB\.?\s*', ' ', txt(grp_td)).strip()
    rm = re.match(r'(\d+(?:-\d+)?)?\s*rums?\s+Familieboliger\s*(.*)$', grp)
    rooms_raw = (rm.group(1) or '') if rm else ''
    nums = [int(x) for x in rooms_raw.split('-') if x]
    rooms_min, rooms_max = (min(nums), max(nums)) if nums else (None, None)
    variant = (rm.group(2).strip() if rm else grp) or ''
    variant = {'+': 'Ekstra faciliteter'}.get(variant, variant)
    boligtype = ('Familieboliger' + (' – ' + variant if variant else '')) if rm else grp

    husleje = txt(tds[i+3])
    areal   = txt(tds[i+4])
    etage   = re.sub(r'\s*-\s*', ' - ', txt(tds[i+5])).strip()
    match_t = txt(tds[i+6])
    n_match = int(m2.group(1)) if (m2 := re.search(r'(\d+)', match_t)) else None

    def rng(s):
        nums = [float(x.replace('.', '').replace(',', '.')) for x in re.findall(r'[\d.]+,?\d*', s)]
        return (min(nums), max(nums)) if nums else (None, None)

    rmin, rmax = rng(husleje)
    amin, amax = rng(areal)

    rows.append(dict(
        placement=placement, placement_raw=pl_raw, afd_id=afd_id, afd_nr=afd_nr, afd_navn=afd_navn, omraade=omraade,
        rooms=rooms_min, rooms_raw=rooms_raw, rooms_min=rooms_min,
        rooms_max=rooms_max, variant=variant, boligtype=boligtype, gruppe_txt=grp, husleje=husleje, rent_min=rmin, rent_max=rmax,
        areal=areal, area_min=amin, area_max=amax, etage=etage,
        matches=n_match,
    ))

json.dump(rows, open('rows.json', 'w'), ensure_ascii=False, indent=1)
print('rows:', len(rows))
print('afdelinger:', len({r['afd_nr'] for r in rows}))
act=[r['placement'] for r in rows if r['placement']]
print('placement range:', min(act), '-', max(act), '| inactive:', len(rows)-len(act))
