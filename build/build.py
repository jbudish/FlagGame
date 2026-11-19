"""Build index.html for the Flag Game."""
import json
from pathlib import Path

from countries import QUIZ_COUNTRIES

ROOT = Path(__file__).resolve().parent.parent
BUILD = Path(__file__).resolve().parent
EXPECTED = {"nfl": 32, "nhl": 32, "nba": 30, "mlb": 30, "mls": 30}
REQUIRED = {
    "nhl": ["Utah Mammoth"],
    "nfl": ["Washington Commanders", "Chicago Bears"],
    "mlb": ["Cleveland Guardians", "Athletics"],
    "mls": ["San Diego FC"],
    "nba": ["Philadelphia 76ers"],
}
BANNED = ("Coyotes", "Redskins", "Football Team", "Oakland", "Indians", "Hockey Club", "TBD")
LEAGUES = {
    "nfl": ("NFL", "🏈", "linear-gradient(165deg,#8d6e63,#5d4037)", "#3e2723"),
    "nhl": ("NHL", "🏒", "linear-gradient(165deg,#26c6da,#00838f)", "#006064"),
    "nba": ("NBA", "🏀", "linear-gradient(165deg,#ffa726,#ef6c00)", "#e65100"),
    "mlb": ("MLB", "⚾", "linear-gradient(165deg,#ef5350,#c62828)", "#b71c1c"),
    "mls": ("MLS", "⚽", "linear-gradient(165deg,#66bb6a,#2e7d32)", "#1b5e20"),
}


def main():
    teams = json.loads((BUILD / "teams.json").read_text())
    geo = json.loads((BUILD / "quiz.json").read_text())
    maps = json.loads((BUILD / "maps.json").read_text())
    if len(maps["us"]["places"]) != 50:
        raise SystemExit("US map should have 50 states")
    tiny = {"RI", "DE", "CT", "NJ", "MD", "MA", "VT", "NH", "HI"}
    have_hits = {p["id"] for p in maps["us"]["places"] if p.get("hit")}
    if tiny - have_hits:
        raise SystemExit(f"tiny states missing hit targets: {tiny - have_hits}")
    regions = {p["id"] for p in geo["sportsMap"]["places"]}
    for need in ("IL", "MD", "DC", "WI", "UT", "ON", "QC", "BC", "AB", "MB", "NY", "CA"):
        if need not in regions:
            raise SystemExit(f"sports map missing {need}")
    leagues = {}
    for league, (title, icon, bg, shadow) in LEAGUES.items():
        locs = {row["id"]: row for row in geo["teams"][league]}
        items = []
        for row in teams["leagues"][league]:
            loc = locs[row["id"]]
            if loc["region"] not in regions:
                raise SystemExit(f"{league} {row['id']} region {loc['region']} missing")
            logo = ROOT / row["file"]
            if not logo.is_file():
                raise SystemExit(f"missing logo {logo}")
            item = {
                "id": row["id"], "name": row["name"], "img": row["file"],
                "region": loc["region"], "x": loc["x"], "y": loc["y"],
            }
            if row.get("say"):
                item["say"] = row["say"]
            text = item["name"] + " " + item.get("say", "")
            for word in BANNED:
                if word in text:
                    raise SystemExit(f"banned word in {item['name']}")
            items.append(item)
        if len(items) != EXPECTED[league]:
            raise SystemExit(f"{league}: expected {EXPECTED[league]}, got {len(items)}")
        have = {item["name"] for item in items}
        for name in REQUIRED.get(league, []):
            if name not in have:
                raise SystemExit(f"{league} missing {name}")
        leagues[league] = {"title": title, "icon": icon, "bg": bg, "shadow": shadow, "teams": items}
    flagged = 0
    for place in geo["world"]["places"]:
        if place.get("img"):
            path = ROOT / place["img"]
            if not path.is_file() or path.stat().st_size < 80:
                raise SystemExit(f"missing flag {path}")
            flagged += 1
    if flagged < 150:
        raise SystemExit(f"only {flagged} flags")
    codes = [code for code, _name in QUIZ_COUNTRIES]
    if len(codes) != len(set(codes)):
        raise SystemExit("QUIZ_COUNTRIES has a duplicate code")
    if not 90 <= len(codes) <= 110:
        raise SystemExit(f"expected about 100 quiz countries, got {len(codes)}")
    world_by_id = {place["id"]: place for place in geo["world"]["places"]}
    map_ids = {place["id"] for cont in maps["continents"] for place in cont["places"]}
    for code, name in QUIZ_COUNTRIES:
        place = world_by_id.get(code)
        if place is None or not place.get("img"):
            raise SystemExit(f"quiz country {name} ({code}) has no flag on the world map")
        if code not in map_ids:
            raise SystemExit(f"quiz country {name} ({code}) is missing from the continent maps")
        if place["name"] != name:
            raise SystemExit(f"quiz country {code} is named {place['name']!r}, list says {name!r}")
    quiz = {
        "sportsMap": geo["sportsMap"],
        "leagues": leagues,
        "world": geo["world"],
        "flags": geo["flags"],
        "quiz": codes,
    }
    # Continent shapes already live in MAPS; the page looks flags up by id.
    html = (BUILD / "template.html").read_text()
    if "/*QUIZ*/" not in html or "/*MAPS*/" not in html:
        raise SystemExit("template is missing a placeholder")
    html = html.replace("/*MAPS*/", json.dumps(maps, ensure_ascii=False, separators=(",", ":")))
    html = html.replace("/*QUIZ*/", json.dumps(quiz, ensure_ascii=False, separators=(",", ":")))
    script = html.split("<script>", 1)[-1]
    if "espncdn" in script or "https://a.espn" in script or "flag-icons" in script:
        raise SystemExit("page script contains a remote image URL")
    out = ROOT / "index.html"
    out.write_text(html)
    print(
        f"wrote {out} ({out.stat().st_size} bytes) flags={flagged} quiz={len(codes)} "
        + " ".join(f"{k}={len(v['teams'])}" for k, v in leagues.items())
    )


if __name__ == "__main__":
    main()
