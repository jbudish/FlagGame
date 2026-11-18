"""Build simplified SVG maps for the US States and World Map games.

US shapes: us-atlas states-albers-10m (U.S. Census Bureau cartography, public
domain), already projected with Alaska and Hawaii as insets.
World shapes: Natural Earth 110m admin-0 countries (public domain).

Writes build/maps.json. No network is required once the two source files are
cached in build/data/.
"""
import json
import math
import urllib.request
from pathlib import Path

from countries import SPEAK

BUILD = Path(__file__).resolve().parent
DATA = BUILD / "data"
OUT = BUILD / "maps.json"

US_URL = "https://cdn.jsdelivr.net/npm/us-atlas@3.0.1/states-albers-10m.json"
NE_URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/ne_110m_admin_0_countries.geojson"

PALETTE = [
    "#ef5350", "#ab47bc", "#5c6bc0", "#29b6f6", "#26a69a", "#66bb6a",
    "#ffca28", "#ffa726", "#ff7043", "#ec407a", "#7e57c2", "#26c6da",
    "#9ccc65", "#8d6e63", "#42a5f5", "#d4e157",
]
POSTAL = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA",
    "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE", "Florida": "FL", "Georgia": "GA",
    "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA",
    "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS", "Missouri": "MO",
    "Montana": "MT", "Nebraska": "NE", "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ",
    "New Mexico": "NM", "New York": "NY", "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH",
    "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT", "Vermont": "VT",
    "Virginia": "VA", "Washington": "WA", "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
}
TINY_STATES = {"RI", "DE", "CT", "NJ", "MD", "MA", "VT", "NH", "HI"}
RENAME = {
    "United States of America": "United States",
    "Dem. Rep. Congo": "DR Congo",
    "Dominican Rep.": "Dominican Republic",
    "S. Sudan": "South Sudan",
    "Central African Rep.": "Central African Republic",
    "Eq. Guinea": "Equatorial Guinea",
    "Bosnia and Herz.": "Bosnia and Herzegovina",
    "W. Sahara": "Western Sahara",
    "Solomon Is.": "Solomon Islands",
    "Falkland Is.": "Falkland Islands",
    "N. Cyprus": "Northern Cyprus",
    "eSwatini": "Eswatini",
    "Congo": "Republic of the Congo",
}
CONTINENTS = [
    ("africa", "Africa", "Africa"),
    ("asia", "Asia", "Asia"),
    ("europe", "Europe", "Europe"),
    ("north-america", "North America", "North America"),
    ("south-america", "South America", "South America"),
    ("oceania", "Oceania", "Oceania"),
]


def fetch(url, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 1000:
        return
    req = urllib.request.Request(url, headers={"User-Agent": "FlagGameFamilyBuild/1.0"})
    dest.write_bytes(urllib.request.urlopen(req, timeout=60).read())


def shoelace(pts):
    a = cx = cy = 0.0
    n = len(pts)
    if n < 3:
        return 0.0, (pts[0] if pts else (0.0, 0.0))
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        cross = x1 * y2 - x2 * y1
        a += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    a *= 0.5
    if abs(a) < 1e-12:
        return 0.0, pts[0]
    return abs(a), (cx / (6 * a), cy / (6 * a))


def bbox(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def decode_arcs(topo):
    scale = topo["transform"]["scale"]
    translate = topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append((x * scale[0] + translate[0], y * scale[1] + translate[1]))
        arcs.append(pts)
    return arcs


def stitch(indexes, arcs):
    pts = []
    for idx in indexes:
        seq = arcs[~idx] if idx < 0 else arcs[idx]
        if idx < 0:
            seq = list(reversed(seq))
        pts.extend(seq[1:] if pts else seq)
    return pts


def topo_polygons(geom, arcs):
    polys = geom["arcs"]
    if geom["type"] == "Polygon":
        polys = [polys]
    out = []
    for poly in polys:
        rings = [stitch(ring, arcs) for ring in poly]
        out.append(rings)
    return out


def geo_polygons(geom):
    coords = geom["coordinates"]
    if geom["type"] == "Polygon":
        coords = [coords]
    return coords


def fix_dateline(ring):
    lons = [p[0] for p in ring]
    if max(lons) - min(lons) <= 180:
        return ring
    if sum(1 for lon in lons if lon < 0) < len(lons) / 2:
        return [(lon + 360 if lon < 0 else lon, lat) for lon, lat in ring]
    return [(lon - 360 if lon > 0 else lon, lat) for lon, lat in ring]


def clip_halfplane(ring, inside, intersect):
    if len(ring) < 2:
        return []
    out = []
    prev = ring[-1]
    prev_in = inside(prev)
    for cur in ring:
        cur_in = inside(cur)
        if cur_in:
            if not prev_in:
                out.append(intersect(prev, cur))
            out.append(cur)
        elif prev_in:
            out.append(intersect(prev, cur))
        prev, prev_in = cur, cur_in
    return out


def clip_box(ring, minx, miny, maxx, maxy):
    def vline(x):
        return lambda a, b: (x, a[1] + (b[1] - a[1]) * ((x - a[0]) / ((b[0] - a[0]) or 1e-9)))

    def hline(y):
        return lambda a, b: (a[0] + (b[0] - a[0]) * ((y - a[1]) / ((b[1] - a[1]) or 1e-9)), y)

    ring = clip_halfplane(ring, lambda p: p[0] >= minx, vline(minx))
    ring = clip_halfplane(ring, lambda p: p[0] <= maxx, vline(maxx))
    ring = clip_halfplane(ring, lambda p: p[1] >= miny, hline(miny))
    ring = clip_halfplane(ring, lambda p: p[1] <= maxy, hline(maxy))
    return ring


def shift_pacific(polys):
    """Move dateline islands (Fiji's west-side ring) next to the rest of the country."""
    cents = []
    for poly in polys:
        if poly and poly[0]:
            cents.append(sum(p[0] for p in poly[0]) / len(poly[0]))
    if not cents or sorted(cents)[len(cents) // 2] < 30:
        return polys
    shifted = []
    for poly in polys:
        rings = []
        for ring in poly:
            lon = sum(p[0] for p in ring) / len(ring)
            if lon < 0:
                ring = [(p[0] + 360, p[1]) for p in ring]
            rings.append(ring)
        shifted.append(rings)
    return shifted


def keep_part(name, continent, lon, lat):
    """Drop overseas scraps so a continent map stays about that continent."""
    if name == "Russia":
        return 19 <= lon <= 52 and 43 <= lat <= 70
    if name == "France":
        return lon > -12 and lat > 41
    if name == "Norway":
        return lat < 72
    if continent == "North America" and lat > 77:
        return False
    if lat < -60:
        return False
    return True


def path_from_rings(rings):
    parts = []
    for ring in rings:
        if len(ring) < 3:
            continue
        cmds = []
        for i, (x, y) in enumerate(ring):
            cmds.append(("M" if i == 0 else "L") + f"{round(x)} {round(y)}")
        parts.append(" ".join(cmds) + " Z")
    return " ".join(parts)


def normalize(records, width=1000):
    pts = [p for rec in records for ring in rec["rings"] for p in ring]
    minx, miny, maxx, maxy = bbox(pts)
    span_x = max(maxx - minx, 1e-6)
    span_y = max(maxy - miny, 1e-6)
    pad = 0.04
    minx -= span_x * pad
    maxx += span_x * pad
    miny -= span_y * pad
    maxy += span_y * pad
    span_x = maxx - minx
    span_y = maxy - miny
    height = width * span_y / span_x

    def conv(x, y):
        return (x - minx) / span_x * width, (y - miny) / span_y * height

    places = []
    for rec in records:
        rings = [[conv(x, y) for x, y in ring] for ring in rec["rings"]]
        areas = []
        for ring_i, ring in enumerate(rings):
            # Outer rings are the first ring of each polygon; holes follow.
            if ring_i in rec["outers"]:
                area, center = shoelace(ring)
                x0, y0, x1, y1 = bbox(ring)
                areas.append((area, center, x1 - x0, y1 - y0))
        area, center, bw, bh = max(areas, key=lambda item: item[0])
        places.append({
            "id": rec["id"],
            "name": rec["name"],
            "d": path_from_rings(rings),
            "area": area,
            "bw": bw,
            "bh": bh,
            "cx": center[0],
            "cy": center[1],
        })
    return f"0 0 {round(width)} {round(height)}", places


def colorize(places, force_hit):
    places.sort(key=lambda p: p["name"])
    out = []
    for i, p in enumerate(places):
        item = {
            "id": p["id"], "name": p["name"], "d": p["d"], "fill": PALETTE[i % len(PALETTE)],
            "cx": round(p["cx"]), "cy": round(p["cy"]),
        }
        if p["name"] in SPEAK:
            item["say"] = SPEAK[p["name"]]
        small = p["id"] in force_hit or min(p["bw"], p["bh"]) < 36 or p["area"] < 700
        if small:
            item["hit"] = [round(p["cx"]), round(p["cy"]), 34]
        out.append(item)
    return out


def build_us(topo):
    arcs = decode_arcs(topo)
    records = []
    for geom in topo["objects"]["states"]["geometries"]:
        name = geom["properties"]["name"]
        if name not in POSTAL:
            continue
        polys = topo_polygons(geom, arcs)
        rings = []
        outers = []
        for poly in polys:
            for i, ring in enumerate(poly):
                if i == 0:
                    outers.append(len(rings))
                rings.append(ring)
        records.append({"id": POSTAL[name], "name": name, "rings": rings, "outers": outers})
    vb, places = normalize(records)
    return {"id": "us", "title": "US States", "vb": vb, "places": colorize(places, TINY_STATES)}


def build_world(geo):
    by_cont = {key: [] for key, _, _ in CONTINENTS}
    name_of = {label: key for key, _, label in CONTINENTS}
    for feat in geo["features"]:
        props = feat["properties"]
        label = props.get("CONTINENT")
        if label not in name_of:
            continue
        raw = props.get("NAME") or props.get("ADMIN")
        name = RENAME.get(raw, raw)
        fid = props.get("ADM0_A3") or raw
        kept = []
        polys = []
        for poly in geo_polygons(feat["geometry"]):
            rings = []
            for ring in poly:
                ring = fix_dateline([(lon, lat) for lon, lat in ring])
                if raw == "Russia":
                    # Natural Earth files all of Russia under Europe. Keep the
                    # European portion so France and Italy stay big enough to tap.
                    ring = clip_box(ring, 19, 43, 52, 70)
                    if len(ring) >= 3 and shoelace(ring)[0] < 4:
                        ring = []
                if len(ring) >= 3:
                    rings.append(ring)
            if rings:
                polys.append(rings)
        polys = shift_pacific(polys)
        for rings in polys:
            area, (lon, lat) = shoelace(rings[0])
            if area <= 0 or not keep_part(raw, label, lon, lat):
                continue
            kept.append(rings)
        if not kept:
            print(f"  dropped all parts of {raw}")
            continue
        by_cont[name_of[label]].append({"id": fid, "name": name, "polys": kept})

    continents = []
    for key, title, _label in CONTINENTS:
        feats = by_cont[key]

        def project_records():
            records = []
            for feat in feats:
                rings = []
                outers = []
                for poly in feat["polys"]:
                    for i, ring in enumerate(poly):
                        projected = [mercator(lon, lat) for lon, lat in ring]
                        if i == 0:
                            outers.append(len(rings))
                        rings.append(projected)
                records.append({"id": feat["id"], "name": feat["name"], "rings": rings, "outers": outers})
            return records

        vb, places = normalize(project_records())
        entry = {"id": key, "title": title, "vb": vb, "places": colorize(places, set())}
        continents.append(entry)
        marked = [p["name"] for p in entry["places"] if "hit" in p]
        print(f"{title}: {len(entry['places'])}  markers: {', '.join(marked)}")
    return continents


def mercator(lon, lat):
    lat = max(min(lat, 84), -56)
    x = math.radians(lon)
    y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    return x, -y


def main():
    fetch(US_URL, DATA / "states-albers-10m.json")
    fetch(NE_URL, DATA / "ne_110m_admin_0_countries.geojson")
    us = build_us(json.loads((DATA / "states-albers-10m.json").read_text()))
    world = build_world(json.loads((DATA / "ne_110m_admin_0_countries.geojson").read_text()))
    if len(us["places"]) != 50:
        raise SystemExit(f"expected 50 states, got {len(us['places'])}")
    tiny_missing = TINY_STATES - {p["id"] for p in us["places"] if "hit" in p}
    if tiny_missing:
        raise SystemExit(f"tiny states missing hit targets: {tiny_missing}")
    blob = {
        "note": "US: Census Bureau via us-atlas (public domain), Albers with Alaska and Hawaii insets. World: Natural Earth 110m (public domain). Russia is the European portion so the Europe map stays tappable. France is metropolitan France.",
        "us": us,
        "continents": world,
    }
    OUT.write_text(json.dumps(blob, ensure_ascii=False, separators=(",", ":")))
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
    # Preview SVGs for a visual check.
    preview = Path("/tmp/map_preview")
    preview.mkdir(exist_ok=True)
    write_preview(preview / "us.svg", us, ocean="#b3e5fc")
    for cont in world:
        write_preview(preview / f"{cont['id']}.svg", cont, ocean="#b3e5fc")


def write_preview(path, group, ocean):
    vb = group["vb"]
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" width="1000" style="background:{ocean}">']
    for p in group["places"]:
        parts.append(f'<path d="{p["d"]}" fill="{p["fill"]}" stroke="#fff" stroke-width="1"/>')
        if "hit" in p:
            cx, cy, r = p["hit"]
            parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#000" stroke-width="2"/>')
            parts.append(f'<text x="{cx}" y="{cy}" font-size="14" text-anchor="middle">{p["id"]}</text>')
    parts.append("</svg>")
    path.write_text("".join(parts))


if __name__ == "__main__":
    main()
