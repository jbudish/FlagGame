"""Build index.html from the template, flag SVGs, and bundled team logos."""
import base64
import json
from pathlib import Path

from countries import L, SPEAK

ROOT = Path(__file__).resolve().parent.parent
BUILD = Path(__file__).resolve().parent
EXPECTED = {"countries": 100, "nfl": 32, "nhl": 32, "nba": 30, "mlb": 30, "mls": 30}
REQUIRED = {
    "nhl": ["Utah Mammoth"],
    "nfl": ["Washington Commanders", "Minnesota Vikings"],
    "mlb": ["Cleveland Guardians", "Athletics"],
    "mls": ["San Diego FC", "Los Angeles FC"],
    "nba": ["Philadelphia 76ers"],
}
BANNED = ("Coyotes", "Redskins", "Football Team", "Oakland", "Indians", "Hockey Club", "TBD")


def countries():
    items = []
    for name, code in L:
        path = BUILD / "svgo" / f"{code.lower()}.svg"
        raw = path.read_bytes()
        if not raw.startswith(b"<svg") and b"<svg" not in raw[:200]:
            raise SystemExit(f"not an svg: {path}")
        item = {"name": name, "img": "data:image/svg+xml;base64," + base64.b64encode(raw).decode()}
        if name in SPEAK:
            item["say"] = SPEAK[name]
        items.append(item)
    return items


def teams():
    blob = json.loads((BUILD / "teams.json").read_text())
    data = {}
    for league, rows in blob["leagues"].items():
        items = []
        for row in rows:
            rel = row["file"]
            path = ROOT / rel
            if not path.is_file() or path.stat().st_size < 400:
                raise SystemExit(f"missing logo {path}")
            if path.suffix.lower() != ".webp":
                raise SystemExit(f"logo should be webp: {path}")
            item = {"name": row["name"], "img": rel}
            if row.get("say"):
                item["say"] = row["say"]
            items.append(item)
        data[league] = items
    return data


def main():
    data = {"countries": countries(), **teams()}
    for key, count in EXPECTED.items():
        if len(data.get(key, [])) != count:
            raise SystemExit(f"{key}: expected {count}, got {len(data.get(key, []))}")
    for league, names in REQUIRED.items():
        have = {item["name"] for item in data[league]}
        for name in names:
            if name not in have:
                raise SystemExit(f"{league} missing {name}")
    for league, items in data.items():
        for item in items:
            text = item["name"] + " " + item.get("say", "")
            for word in BANNED:
                if word in text:
                    raise SystemExit(f"banned word in {league} {item['name']}: {word}")
            if item["img"].startswith(("http://", "https://")):
                raise SystemExit(f"remote image for {item['name']}")
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    maps = json.loads((BUILD / "maps.json").read_text())
    if len(maps["us"]["places"]) != 50:
        raise SystemExit("US map should have 50 states")
    tiny = {"RI", "DE", "CT", "NJ", "MD", "MA", "VT", "NH", "HI"}
    have_hits = {p["id"] for p in maps["us"]["places"] if p.get("hit")}
    if tiny - have_hits:
        raise SystemExit(f"tiny states missing hit targets: {tiny - have_hits}")
    if len(maps["continents"]) != 6:
        raise SystemExit("expected 6 continents")
    if any(c["id"] == "antarctica" for c in maps["continents"]):
        raise SystemExit("Antarctica should be omitted")
    html = (BUILD / "template.html").read_text()
    if "/*DATA*/" not in html or "/*MAPS*/" not in html:
        raise SystemExit("template is missing a placeholder")
    html = html.replace("/*DATA*/", blob).replace(
        "/*MAPS*/", json.dumps(maps, ensure_ascii=False, separators=(",", ":"))
    )
    out = ROOT / "index.html"
    out.write_text(html)
    print(f"wrote {out} ({out.stat().st_size} bytes) " + " ".join(f"{k}={len(v)}" for k, v in data.items()))


if __name__ == "__main__":
    main()
