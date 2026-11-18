"""Project a US + Canada map and locate every team on it.

Geometry: Natural Earth 50m admin-1 (public domain), simplified.
City positions are the team's home city. Washington Commanders use Maryland
(the stadium is in Landover). Alaska and Hawaii are insets.
"""
import json
import math
import urllib.request
from pathlib import Path

from countries import SPEAK
from make_maps import RENAME, clip_box, fix_dateline, keep_part, shift_pacific, shoelace

BUILD = Path(__file__).resolve().parent
ROOT = BUILD.parent
DATA = BUILD / "data"
FLAGS = ROOT / "assets" / "flags"
SRC = DATA / "na_admin1.json"
NE = DATA / "ne_110m_admin_0_countries.geojson"
OUT = BUILD / "quiz.json"
FLAG_CDN = "https://cdn.jsdelivr.net/npm/flag-icons@7.2.3/flags/4x3/{}.svg"

# league, id -> region postal, latitude, longitude
LOC = {
    "nfl": {
        "ari": ("AZ", 33.53, -112.10), "atl": ("GA", 33.76, -84.40), "bal": ("MD", 39.28, -76.62),
        "buf": ("NY", 42.77, -78.79), "car": ("NC", 35.23, -80.84), "chi": ("IL", 41.86, -87.62),
        "cin": ("OH", 39.10, -84.51), "cle": ("OH", 41.51, -81.70), "dal": ("TX", 32.75, -97.09),
        "den": ("CO", 39.74, -105.02), "det": ("MI", 42.34, -83.05), "gb": ("WI", 44.50, -88.06),
        "hou": ("TX", 29.68, -95.41), "ind": ("IN", 39.76, -86.16), "jax": ("FL", 30.32, -81.64),
        "kc": ("MO", 39.05, -94.48), "lv": ("NV", 36.09, -115.18), "lac": ("CA", 33.95, -118.34),
        "lar": ("CA", 33.95, -118.34), "mia": ("FL", 25.96, -80.24), "min": ("MN", 44.97, -93.26),
        "ne": ("MA", 42.09, -71.26), "no": ("LA", 29.95, -90.08), "nyg": ("NY", 40.81, -74.07),
        "nyj": ("NY", 40.75, -74.07), "phi": ("PA", 39.90, -75.17), "pit": ("PA", 40.45, -79.99),
        "sf": ("CA", 37.40, -121.97), "sea": ("WA", 47.60, -122.33), "tb": ("FL", 27.98, -82.50),
        "ten": ("TN", 36.17, -86.77), "wsh": ("MD", 38.91, -76.86),
    },
    "nhl": {
        "ana": ("CA", 33.81, -117.88), "bos": ("MA", 42.37, -71.06), "buf": ("NY", 42.87, -78.88),
        "cgy": ("AB", 51.04, -114.07), "car": ("NC", 35.80, -78.72), "chi": ("IL", 41.88, -87.67),
        "col": ("CO", 39.75, -105.01), "cbj": ("OH", 39.97, -83.01), "dal": ("TX", 32.79, -96.81),
        "det": ("MI", 42.34, -83.06), "edm": ("AB", 53.55, -113.50), "fla": ("FL", 26.16, -80.33),
        "la": ("CA", 34.04, -118.27), "min": ("MN", 44.94, -93.10), "mtl": ("QC", 45.50, -73.57),
        "nsh": ("TN", 36.16, -86.78), "nj": ("NJ", 40.73, -74.17), "nyi": ("NY", 40.72, -73.59),
        "nyr": ("NY", 40.75, -73.99), "ott": ("ON", 45.30, -75.69), "phi": ("PA", 39.90, -75.17),
        "pit": ("PA", 40.44, -79.99), "sj": ("CA", 37.33, -121.90), "sea": ("WA", 47.62, -122.35),
        "stl": ("MO", 38.63, -90.20), "tb": ("FL", 27.94, -82.45), "tor": ("ON", 43.64, -79.38),
        "utah": ("UT", 40.77, -111.90), "van": ("BC", 49.28, -123.11), "vgk": ("NV", 36.10, -115.18),
        "wsh": ("DC", 38.90, -77.02), "wpg": ("MB", 49.89, -97.14),
    },
    "nba": {
        "atl": ("GA", 33.76, -84.40), "bos": ("MA", 42.37, -71.06), "bkn": ("NY", 40.68, -73.97),
        "cha": ("NC", 35.23, -80.84), "chi": ("IL", 41.88, -87.67), "cle": ("OH", 41.50, -81.69),
        "dal": ("TX", 32.79, -96.81), "den": ("CO", 39.75, -105.01), "det": ("MI", 42.34, -83.06),
        "gs": ("CA", 37.77, -122.39), "hou": ("TX", 29.75, -95.36), "ind": ("IN", 39.76, -86.16),
        "lac": ("CA", 34.04, -118.27), "lal": ("CA", 34.04, -118.27), "mem": ("TN", 35.14, -90.05),
        "mia": ("FL", 25.78, -80.19), "mil": ("WI", 43.04, -87.92), "min": ("MN", 44.98, -93.28),
        "no": ("LA", 29.95, -90.08), "ny": ("NY", 40.75, -73.99), "okc": ("OK", 35.46, -97.52),
        "orl": ("FL", 28.54, -81.38), "phi": ("PA", 39.90, -75.17), "phx": ("AZ", 33.45, -112.07),
        "por": ("OR", 45.53, -122.67), "sac": ("CA", 38.58, -121.50), "sa": ("TX", 29.43, -98.44),
        "tor": ("ON", 43.64, -79.38), "utah": ("UT", 40.77, -111.90), "wsh": ("DC", 38.90, -77.02),
    },
    "mlb": {
        "ari": ("AZ", 33.45, -112.07), "ath": ("CA", 38.58, -121.51), "atl": ("GA", 33.89, -84.47),
        "bal": ("MD", 39.28, -76.62), "bos": ("MA", 42.35, -71.10), "chc": ("IL", 41.95, -87.66),
        "chw": ("IL", 41.83, -87.63), "cin": ("OH", 39.10, -84.51), "cle": ("OH", 41.50, -81.69),
        "col": ("CO", 39.76, -104.99), "det": ("MI", 42.34, -83.05), "hou": ("TX", 29.76, -95.36),
        "kc": ("MO", 39.05, -94.48), "laa": ("CA", 33.80, -117.88), "lad": ("CA", 34.07, -118.24),
        "mia": ("FL", 25.78, -80.22), "mil": ("WI", 43.03, -87.97), "min": ("MN", 44.98, -93.28),
        "nym": ("NY", 40.76, -73.85), "nyy": ("NY", 40.83, -73.93), "phi": ("PA", 39.91, -75.17),
        "pit": ("PA", 40.45, -80.01), "sd": ("CA", 32.71, -117.16), "sf": ("CA", 37.78, -122.39),
        "sea": ("WA", 47.59, -122.33), "stl": ("MO", 38.62, -90.19), "tb": ("FL", 27.77, -82.65),
        "tex": ("TX", 32.75, -97.08), "tor": ("ON", 43.64, -79.38), "wsh": ("DC", 38.87, -77.01),
    },
    "mls": {
        "atl": ("GA", 33.76, -84.40), "atx": ("TX", 30.27, -97.74), "mtl": ("QC", 45.56, -73.55),
        "clt": ("NC", 35.23, -80.84), "chi": ("IL", 41.86, -87.62), "col": ("CO", 39.81, -104.89),
        "clb": ("OH", 39.97, -83.01), "dc": ("DC", 38.87, -77.01), "cin": ("OH", 39.11, -84.52),
        "dal": ("TX", 33.15, -96.84), "hou": ("TX", 29.75, -95.35), "mia": ("FL", 25.96, -80.16),
        "la": ("CA", 33.86, -118.26), "lafc": ("CA", 34.01, -118.28), "min": ("MN", 44.95, -93.16),
        "nsh": ("TN", 36.13, -86.77), "ne": ("MA", 42.09, -71.26), "nyc": ("NY", 40.83, -73.93),
        "orl": ("FL", 28.54, -81.39), "phi": ("PA", 39.83, -75.38), "por": ("OR", 45.52, -122.69),
        "rsl": ("UT", 40.58, -111.89), "rbny": ("NJ", 40.74, -74.15), "sd": ("CA", 32.78, -117.12),
        "sj": ("CA", 37.35, -121.92), "sea": ("WA", 47.60, -122.33), "skc": ("KS", 39.12, -94.82),
        "stl": ("MO", 38.63, -90.21), "tor": ("ON", 43.63, -79.42), "van": ("BC", 49.28, -123.11),
    },
}
A3_ISO = {"FRA": "fr", "NOR": "no", "KOS": "xk", "SAH": "eh", "SOL": "so", "TWN": "tw"}


def dp(pts, eps):
    if len(pts) < 3:
        return pts
    closed = pts[0] == pts[-1]
    if closed:
        core = _dp(pts[:-1], eps)
        return core + [core[0]]
    return _dp(pts, eps)


def _dp(pts, eps):
    if len(pts) < 3:
        return pts
    ax, ay = pts[0]
    bx, by = pts[-1]
    dmax, idx = 0, 0
    for i in range(1, len(pts) - 1):
        px, py = pts[i]
        num = abs((by - ay) * px - (bx - ax) * py + bx * ay - by * ax)
        den = math.hypot(bx - ax, by - ay) or 1
        dist = num / den
        if dist > dmax:
            dmax, idx = dist, i
    if dmax > eps:
        return _dp(pts[: idx + 1], eps)[:-1] + _dp(pts[idx:], eps)
    return [pts[0], pts[-1]]


def albers(lon, lat):
    p1, p2, p0 = math.radians(29.5), math.radians(45.5), math.radians(37.5)
    l0 = math.radians(-96)
    n = 0.5 * (math.sin(p1) + math.sin(p2))
    c = math.cos(p1) ** 2 + 2 * n * math.sin(p1)
    rho0 = math.sqrt(c - 2 * n * math.sin(p0)) / n
    phi = math.radians(max(min(lat, 75), 15))
    rho = math.sqrt(c - 2 * n * math.sin(phi)) / n
    theta = n * (math.radians(lon) - l0)
    return rho * math.sin(theta), -(rho0 - rho * math.cos(theta))


def rings_of(geom):
    coords = geom["coordinates"]
    if geom["type"] == "Polygon":
        coords = [coords]
    out = []
    for poly in coords:
        rings = []
        for i, ring in enumerate(poly):
            ring = [(p[0], p[1]) for p in ring]
            ring = dp(ring, 0.05)
            if len(ring) >= 4:
                rings.append(ring)
        if rings:
            out.append(rings)
    return out


def path_d(rings):
    parts = []
    for ring in rings:
        cmds = [("M" if i == 0 else "L") + f"{round(x)} {round(y)}" for i, (x, y) in enumerate(ring)]
        parts.append(" ".join(cmds) + " Z")
    return " ".join(parts)


def fit(records, width=1000):
    pts = [p for rec in records for ring in rec["rings"] for p in ring]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    span_x, span_y = maxx - minx, maxy - miny
    pad = 0.03
    minx -= span_x * pad
    maxx += span_x * pad
    miny -= span_y * pad
    maxy += span_y * pad
    span_x, span_y = maxx - minx, maxy - miny
    height = width * span_y / span_x

    def conv(x, y):
        return (x - minx) / span_x * width, (y - miny) / span_y * height

    return conv, width, height


def inset(records, box):
    x0, y0, x1, y1 = box
    pts = [p for rec in records for ring in rec["rings"] for p in ring]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    bw, bh = x1 - x0, y1 - y0
    scale = min(bw / (maxx - minx), bh / (maxy - miny)) * 0.9
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    ox, oy = (x0 + x1) / 2, (y0 + y1) / 2

    def conv(x, y):
        return ox + (x - cx) * scale, oy + (y - cy) * scale

    return conv


def classify(postal, lon, lat):
    if postal == "AK" or (lon < -130 and lat > 50):
        return "ak"
    if postal == "HI" or (lon < -150 and lat < 30):
        return "hi"
    return "main"


def build_sports_map(geo):
    groups = {"main": [], "ak": [], "hi": []}
    for feat in geo["features"]:
        props = feat["properties"]
        admin = props.get("admin")
        if admin not in ("United States of America", "Canada"):
            continue
        postal = (props.get("postal") or "").upper()
        if not postal:
            continue
        name = props.get("name")
        if name == "Québec":
            name = "Quebec"
        polys = rings_of(feat["geometry"])
        if not polys:
            continue
        # Centroid of the largest outer ring, in lon/lat, for classification.
        best = max(polys, key=lambda rings: shoelace(rings[0])[0])
        area, (lon, lat) = shoelace(best[0])
        kind = classify(postal, lon, lat)
        projected = []
        for rings in polys:
            projected.append([[albers(x, y) for x, y in ring] for ring in rings])
        groups[kind].append({"id": postal, "name": name, "polys": projected, "kind": kind})

    main_records = []
    for feat in groups["main"]:
        # Drop far-north vertices so Nunavut does not shrink the whole map.
        rings, outers = [], []
        for poly in feat["polys"]:
            for i, ring in enumerate(poly):
                if i == 0:
                    outers.append(len(rings))
                rings.append(ring)
        main_records.append({"id": feat["id"], "rings": rings, "outers": outers})
    # Bbox from the populated belt only.
    belt = []
    for rec in main_records:
        for ring in rec["rings"]:
            belt.extend([p for p in ring if -128 <= p[0] <= 40 and -8 <= p[1] <= 8])
    # The Albers numbers are arbitrary; filter by lat via inverse is hard.
    # Instead recompute belt in lon/lat before projection: rebuild records from raw.
    return groups


def project_groups(geo):
    buckets = {"main": [], "ak": [], "hi": []}
    for feat in geo["features"]:
        props = feat["properties"]
        if props.get("admin") not in ("United States of America", "Canada"):
            continue
        postal = (props.get("postal") or "").upper()
        if not postal:
            continue
        name = "Quebec" if props.get("name") == "Québec" else props.get("name")
        raw = rings_of(feat["geometry"])
        if not raw:
            continue
        best = max(raw, key=lambda rings: abs(shoelace(rings[0])[0]))
        _, (lon, lat) = shoelace(best[0])
        kind = classify(postal, lon, lat)
        if kind == "main":
            trimmed = []
            for rings in raw:
                keep = []
                for ring in rings:
                    keep.append([(x, y) for x, y in ring if y <= 62])
                keep = [r for r in keep if len(r) >= 4]
                if keep:
                    trimmed.append(keep)
            raw = trimmed
        if not raw:
            continue
        buckets[kind].append({
            "id": postal, "name": name,
            "polys": [[[albers(x, y) for x, y in ring] for ring in rings] for rings in raw],
        })
    return buckets


def pack(buckets):
    main = []
    for feat in buckets["main"]:
        rings, outers = [], []
        for poly in feat["polys"]:
            for i, ring in enumerate(poly):
                if i == 0:
                    outers.append(len(rings))
                rings.append(ring)
        main.append({"id": feat["id"], "name": feat["name"], "rings": rings, "outers": outers})
    conv, width, height = fit(main)
    places = []
    for rec in main:
        rings = [[conv(x, y) for x, y in ring] for ring in rec["rings"]]
        places.append({"id": rec["id"], "name": rec["name"], "d": path_d(rings), "rings": rings})
    # Insets sit in the lower-left ocean of the main map.
    boxes = {"ak": (18, height - 168, 210, height - 18), "hi": (220, height - 130, 360, height - 22)}
    for kind, box in boxes.items():
        feats = buckets[kind]
        records = []
        for feat in feats:
            rings = [ring for poly in feat["polys"] for ring in poly]
            records.append({"rings": rings, "id": feat["id"], "name": feat["name"]})
        iconv = inset(records, box)
        for feat in feats:
            rings = [[iconv(x, y) for x, y in ring] for poly in feat["polys"] for ring in poly]
            places.append({"id": feat["id"], "name": feat["name"], "d": path_d(rings), "rings": rings})
    vb = f"0 0 {round(width)} {round(height)}"

    def conv_city(lon, lat):
        x, y = albers(lon, lat)
        return conv(x, y)

    return vb, places, conv_city


def nearest_point(pt, rings):
    if inside(pt, rings):
        return pt
    best, dist = pt, 1e18
    for ring in rings:
        for x, y in ring:
            d = (x - pt[0]) ** 2 + (y - pt[1]) ** 2
            if d < dist:
                dist, best = d, (x, y)
    return best


def inside(pt, rings):
    x, y = pt
    ok = False
    for ring in rings:
        n = len(ring)
        j = n - 1
        hit = False
        for i in range(n):
            xi, yi = ring[i]
            xj, yj = ring[j]
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi):
                hit = not hit
            j = i
        if hit:
            ok = not ok
    return ok


def ensure_na():
    if SRC.exists() and SRC.stat().st_size > 1000:
        return
    url = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/ne_50m_admin_1_states_provinces.geojson"
    raw = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "FlagGame"}), timeout=60))
    keep = [f for f in raw["features"] if f["properties"].get("admin") in ("United States of America", "Canada")]
    SRC.write_text(json.dumps({"type": "FeatureCollection", "features": keep}))


def iso_for(props):
    iso = (props.get("ISO_A2") or "").lower()
    if len(iso) == 2 and iso.isalpha():
        return iso
    return A3_ISO.get(props.get("ADM0_A3") or "")


def fetch_flag(iso):
    dest = FLAGS / f"{iso}.svg"
    if dest.exists() and dest.stat().st_size > 80:
        return True
    local = BUILD / "svgo" / f"{iso}.svg"
    if local.exists():
        dest.write_bytes(local.read_bytes())
        return True
    try:
        req = urllib.request.Request(FLAG_CDN.format(iso), headers={"User-Agent": "FlagGameFamilyBuild/1.0"})
        data = urllib.request.urlopen(req, timeout=30).read()
    except Exception:
        return False
    if data[:20].find(b"<svg") == -1 and b"<svg" not in data[:200]:
        return False
    FLAGS.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return True


def build_world():
    geo = json.loads(NE.read_text())
    feats = []
    flags = {}
    for feat in geo["features"]:
        props = feat["properties"]
        label = props.get("CONTINENT")
        cont = {
            "Africa": "africa", "Asia": "asia", "Europe": "europe",
            "North America": "north-america", "South America": "south-america", "Oceania": "oceania",
        }.get(label)
        if not cont:
            continue
        raw_name = props.get("NAME") or props.get("ADMIN")
        name = RENAME.get(raw_name, raw_name)
        fid = props.get("ADM0_A3") or raw_name
        iso = iso_for(props)
        img = None
        if iso and fetch_flag(iso):
            img = f"assets/flags/{iso}.svg"
            flags[fid] = img
        polys = []
        for poly in (feat["geometry"]["coordinates"] if feat["geometry"]["type"] == "MultiPolygon" else [feat["geometry"]["coordinates"]]):
            rings = []
            for ring in poly:
                ring = fix_dateline([(p[0], p[1]) for p in ring])
                if raw_name == "Russia":
                    ring = clip_box(ring, 19, 43, 52, 70)
                    if len(ring) >= 3 and shoelace(ring)[0] < 4:
                        ring = []
                if len(ring) >= 3:
                    rings.append(ring)
            if rings:
                polys.append(rings)
        polys = shift_pacific(polys)
        kept = []
        for rings in polys:
            area, (lon, lat) = shoelace(rings[0])
            if area > 0 and keep_part(raw_name, label, lon, lat):
                kept.append(rings)
        if not kept:
            continue
        feats.append({"id": fid, "name": name, "cont": cont, "img": img, "polys": kept, "say": SPEAK.get(name)})
    # Equirectangular, width 1000.
    records = []
    for feat in feats:
        rings, outers = [], []
        for poly in feat["polys"]:
            for i, ring in enumerate(poly):
                proj = [(lon, -lat) for lon, lat in ring]
                if i == 0:
                    outers.append(len(rings))
                rings.append(proj)
        records.append({"id": feat["id"], "rings": rings, "outers": outers, "feat": feat})
    conv, width, height = fit(records)
    places = []
    for rec in records:
        rings = [[conv(x, y) for x, y in ring] for ring in rec["rings"]]
        outers = rec["outers"]
        areas = []
        for i in outers:
            area, center = shoelace(rings[i])
            xs, ys = [p[0] for p in rings[i]], [p[1] for p in rings[i]]
            areas.append((area, center, max(xs) - min(xs), max(ys) - min(ys)))
        area, center, bw, bh = max(areas)
        feat = rec["feat"]
        item = {
            "id": feat["id"], "name": feat["name"], "cont": feat["cont"],
            "d": path_d(rings), "cx": round(center[0]), "cy": round(center[1]),
        }
        if feat["img"]:
            item["img"] = feat["img"]
        if feat["say"]:
            item["say"] = feat["say"]
        if min(bw, bh) < 26 or area < 500:
            item["dot"] = True
        places.append(item)
    missing = [p["name"] for p in places if "img" not in p]
    print(f"world places {len(places)} with flags {sum(1 for p in places if 'img' in p)} missing {missing}")
    return {"vb": f"0 0 {round(width)} {round(height)}", "places": places}, flags


def main():
    ensure_na()
    FLAGS.mkdir(parents=True, exist_ok=True)
    # Seed flags we already drew for the top 100.
    for svg in (BUILD / "svgo").glob("*.svg"):
        dest = FLAGS / svg.name
        if not dest.exists():
            dest.write_bytes(svg.read_bytes())
    geo = json.loads(SRC.read_text())
    buckets = project_groups(geo)
    vb, places, conv_city = pack(buckets)
    by_id = {p["id"]: p for p in places}
    teams = json.loads((BUILD / "teams.json").read_text())
    located = {}
    for league, rows in teams["leagues"].items():
        located[league] = []
        for row in rows:
            region, lat, lon = LOC[league][row["id"]]
            x, y = conv_city(lon, lat)
            place = by_id.get(region)
            if place is None:
                raise SystemExit(f"no region {region} for {league} {row['id']}")
            if not inside((x, y), place["rings"]):
                x, y = nearest_point((x, y), place["rings"])
            item = {"id": row["id"], "region": region, "x": round(x), "y": round(y)}
            located[league].append(item)
        print(league, "teams", len(located[league]))
    world, flags = build_world()
    # Drop bulky rings from the saved map.
    for p in places:
        p.pop("rings", None)
    blob = {"sportsMap": {"vb": vb, "places": places}, "teams": located, "world": world, "flags": flags}
    OUT.write_text(json.dumps(blob, ensure_ascii=False, separators=(",", ":")))
    print("wrote", OUT, OUT.stat().st_size, "regions", len(places))


if __name__ == "__main__":
    main()
