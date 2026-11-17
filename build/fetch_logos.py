"""Download current team logos from ESPN's public CDN and write assets/.

Logos are saved at build time (about 300px WebP) so the site never hotlinks.
Run from anywhere: python3 build/fetch_logos.py
"""
import io
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "logos"
TEAMS_PATH = Path(__file__).resolve().parent / "teams.json"
UA = {"User-Agent": "FlagGameFamilyBuild/1.0"}

LEAGUES = {
    "nfl": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams?limit=50",
    "nhl": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/teams?limit=50",
    "nba": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams?limit=50",
    "mlb": "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/teams?limit=50",
    "mls": "https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/teams?limit=50",
}
EXPECTED = {"nfl": 32, "nhl": 32, "nba": 30, "mlb": 30, "mls": 30}

# Fuller than ESPN's short label, still the name a kid should see and hear.
RENAME = {
    ("mls", "LAFC"): "Los Angeles FC",
    ("mls", "Vancouver Whitecaps"): "Vancouver Whitecaps FC",
}
SAY = {
    "Los Angeles FC": "Los Angeles F C",
    "Vancouver Whitecaps FC": "Vancouver Whitecaps F C",
    "LA Galaxy": "L.A. Galaxy",
    "LA Clippers": "L.A. Clippers",
    "D.C. United": "D C United",
    "CF Montréal": "C F Montreal",
    "Philadelphia 76ers": "Philadelphia Seventy Sixers",
    "San Francisco 49ers": "San Francisco Forty Niners",
    "Athletics": "The Athletics",
    "St. Louis Blues": "Saint Louis Blues",
    "St. Louis Cardinals": "Saint Louis Cardinals",
    "St. Louis CITY SC": "Saint Louis City S C",
    "Inter Miami CF": "Inter Miami C F",
}
MUST = {
    "nhl": "Utah Mammoth",
    "nfl": "Washington Commanders",
    "nba": "Philadelphia 76ers",
    "mlb": "Cleveland Guardians",
    "mls": "San Diego FC",
}
FONT = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf", 14)


def get_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=40) as resp:
        return json.load(resp)


def get_bytes(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=40) as resp:
        return resp.read()


def rels(logo):
    rel = logo.get("rel") or []
    return rel if isinstance(rel, list) else [rel]


def logo_url(logos, kind):
    for logo in logos:
        rel = rels(logo)
        if kind == "default" and "default" in rel and "dark" not in rel and "scoreboard" not in rel:
            return logo.get("href")
        if kind == "on_white" and "primary_logo_on_white_color" in rel:
            return logo.get("href")
        if kind == "scoreboard" and "scoreboard" in rel and "dark" not in rel:
            return logo.get("href")
    return None


def is_placeholder(team):
    abbr = (team.get("abbreviation") or "").upper()
    name = (team.get("displayName") or "").upper()
    if abbr.startswith("TBD") or name.startswith("TBD"):
        return True
    if not team.get("logos"):
        return True
    return False


def speakable(name):
    if name in SAY:
        return SAY[name]
    spoken = name
    if spoken.startswith("FC "):
        spoken = "F C " + spoken[3:]
    spoken = spoken.replace(" FC", " F C").replace(" CF", " C F")
    if spoken.endswith(" SC"):
        spoken = spoken[:-3] + " S C"
    return spoken if spoken != name else None


def prepare(png_bytes):
    im = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    bbox = im.getbbox()
    if bbox:
        im = im.crop(bbox)
    im.thumbnail((300, 300), Image.Resampling.LANCZOS)
    return im


def luminance(im):
    pixels = list(im.getdata())
    opaque = [(r, g, b, a) for r, g, b, a in pixels if a > 20]
    if not opaque:
        return 0.0, 0.0, 0.0
    lums = [0.2126 * r + 0.7152 * g + 0.0722 * b for r, g, b, a in opaque]
    white = sum(1 for lum in lums if lum > 225)
    return sum(lums) / len(lums), len(opaque) / len(pixels), white / len(opaque)


def save_webp(im, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, "WEBP", quality=90, alpha_quality=100, method=6)


def fetch_team(league, team):
    abbr = team["abbreviation"].lower()
    name = RENAME.get((league, team["displayName"]), team["displayName"])
    logos = team.get("logos") or []
    order = ["default", "on_white", "scoreboard"]
    chosen = None
    stats = None
    raw_url = None
    for kind in order:
        url = logo_url(logos, kind)
        if not url:
            continue
        im = prepare(get_bytes(url))
        lum, frac, white = luminance(im)
        chosen, stats, raw_url = im, (lum, frac, white, kind), url
        # Default color marks are right for a white page. Swap only if the
        # pixels are mostly white (a dark-mode alternate) or nearly empty.
        if frac > 0.02 and white < 0.62 and lum < 200:
            break
    if chosen is None:
        raise RuntimeError(f"no logo for {league} {name}")
    path = OUT / league / f"{abbr}.webp"
    save_webp(chosen, path)
    row = {
        "id": abbr,
        "name": name,
        "file": f"assets/logos/{league}/{abbr}.webp",
        "source": raw_url,
        "variant": stats[3],
    }
    spoken = speakable(name)
    if spoken:
        row["say"] = spoken
    return row, stats, chosen


def contact_sheet(league, rows, images):
    cols = 8
    cell_w, logo_h, cap_h = 168, 132, 36
    rows_n = (len(rows) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell_w, rows_n * (logo_h + cap_h) + 28), "white")
    draw = ImageDraw.Draw(sheet)
    draw.text((8, 4), league.upper(), fill=(20, 40, 80), font=FONT)
    for i, (row, im) in enumerate(zip(rows, images)):
        c, r = i % cols, i // cols
        x, y = c * cell_w, 28 + r * (logo_h + cap_h)
        tile = Image.new("RGB", (cell_w - 8, logo_h - 4), (255, 255, 255))
        thumb = im.copy()
        thumb.thumbnail((cell_w - 16, logo_h - 12), Image.Resampling.LANCZOS)
        tile.paste(thumb, ((tile.width - thumb.width) // 2, (tile.height - thumb.height) // 2), thumb)
        sheet.paste(tile, (x + 4, y))
        label = row["name"]
        if len(label) > 22:
            label = label[:21] + "…"
        draw.text((x + 6, y + logo_h - 2), label, fill=(30, 30, 30), font=FONT)
    dest = Path("/tmp/logo_review")
    dest.mkdir(parents=True, exist_ok=True)
    sheet.save(dest / f"{league}.png")


def main():
    catalog = {}
    warnings = []
    for league, url in LEAGUES.items():
        payload = get_json(url)
        teams = [t["team"] for t in payload["sports"][0]["leagues"][0]["teams"]]
        teams = [t for t in teams if not is_placeholder(t)]
        print(f"{league}: {len(teams)} teams")
        rows, images = [], []
        with ThreadPoolExecutor(max_workers=8) as pool:
            futs = {pool.submit(fetch_team, league, t): t for t in teams}
            done = []
            for fut in as_completed(futs):
                row, stats, im = fut.result()
                done.append((row, stats, im))
        done.sort(key=lambda item: item[0]["name"])
        for row, stats, im in done:
            lum, frac, white, kind = stats
            flag = ""
            if white >= 0.62 or lum >= 200 or frac < 0.02:
                flag = " LIGHT" if white >= 0.62 or lum >= 200 else " EMPTY"
                warnings.append(f"{league} {row['name']} lum={lum:.0f} white={white:.2f} fill={frac:.2f} via {kind}")
            print(f"  {row['id']:8} {row['name']:28} {kind:10} lum={lum:5.0f} white={white:.2f}{flag}")
            rows.append(row)
            images.append(im)
        if len(rows) != EXPECTED[league]:
            raise SystemExit(f"{league}: expected {EXPECTED[league]} teams, got {len(rows)}")
        names = {r["name"] for r in rows}
        if MUST[league] not in names:
            raise SystemExit(f"{league}: missing {MUST[league]}")
        ids = [r["id"] for r in rows]
        if len(ids) != len(set(ids)):
            raise SystemExit(f"{league}: duplicate ids")
        contact_sheet(league, rows, images)
        catalog[league] = rows
    blob = {
        "note": "Current teams and logos fetched from ESPN's public API/CDN for this private family game. Do not hotlink; files live in assets/logos/.",
        "leagues": catalog,
    }
    TEAMS_PATH.write_text(json.dumps(blob, ensure_ascii=False, indent=2) + "\n")
    total = sum(p.stat().st_size for p in OUT.rglob("*.webp"))
    print(f"wrote {TEAMS_PATH} and {total/1e6:.2f} MB of webp")
    if warnings:
        print("WARNINGS:")
        for line in warnings:
            print(" ", line)


if __name__ == "__main__":
    main()
