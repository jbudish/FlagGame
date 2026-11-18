"""Play every game in a phone-sized landscape viewport, and check portrait."""
import os
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SHOTS = Path(__file__).resolve().parent / "shots"
SHOTS.mkdir(exist_ok=True)
URL = "http://127.0.0.1:8765/"
CHROME = "/usr/local/bin/google-chrome"

FORCED = {
    "countries": "United States",
    "nfl": "Minnesota Vikings",
    "nhl": "Utah Mammoth",
    "nba": "Los Angeles Lakers",
    "mlb": "Cleveland Guardians",
    "mls": "San Diego FC",
}


def serve():
    os.chdir(ROOT)
    httpd = ThreadingHTTPServer(("127.0.0.1", 8765), partial(SimpleHTTPRequestHandler, directory=str(ROOT)))
    httpd.serve_forever()


def show_named(pg, game, name):
    return pg.evaluate(
        """({game, name}) => {
          const items = FlagGame.DATA[game];
          const i = items.findIndex(t => t.name === name);
          if (i < 0) return {ok:false};
          const deck = FlagGame.state[game].deck.filter(x => x !== i);
          deck.unshift(i);
          FlagGame.state[game].deck = deck;
          FlagGame.state[game].pos = 0;
          FlagGame.startGame(game);
          return {ok:true, shown: items[i].name};
        }""",
        {"game": game, "name": name},
    )


def main():
    threading.Thread(target=serve, daemon=True).start()
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(
            viewport={"width": 844, "height": 390},
            device_scale_factor=2,
            is_mobile=True,
            has_touch=True,
        )
        page = context.new_page()
        reqs = []
        page.on("request", lambda r: reqs.append(r.url) if not r.url.startswith((URL, "data:", "blob:")) else None)
        page.on("pageerror", lambda e: errors.append("pageerror " + str(e)))
        page.on("console", lambda m: errors.append("console " + m.text) if m.type == "error" else None)
        page.set_default_timeout(60000)
        page.goto(URL)
        page.wait_for_timeout(250)

        counts = page.evaluate("() => Object.fromEntries(Object.entries(FlagGame.DATA).map(([k,v]) => [k, v.length]))")
        print("counts", counts)
        assert counts == {"countries": 100, "nfl": 32, "nhl": 32, "nba": 30, "mlb": 30, "mls": 30}, counts

        names = page.evaluate(
            """() => {
              const all = Object.values(FlagGame.DATA).flat().map(t => t.name + '|' + (t.say || ''));
              return {
                utah: FlagGame.DATA.nhl.some(t => t.name === 'Utah Mammoth'),
                sd: FlagGame.DATA.mls.some(t => t.name === 'San Diego FC'),
                wsh: FlagGame.DATA.nfl.some(t => t.name === 'Washington Commanders'),
                cle: FlagGame.DATA.mlb.some(t => t.name === 'Cleveland Guardians'),
                ath: FlagGame.DATA.mlb.some(t => t.name === 'Athletics'),
                vikingsSay: (FlagGame.DATA.nfl.find(t => t.name === 'Minnesota Vikings').say) || 'Minnesota Vikings',
                sixers: FlagGame.DATA.nba.find(t => t.name === 'Philadelphia 76ers').say,
                banned: all.some(s => /Coyotes|Redskins|Oakland|Indians|Hockey Club|TBD/.test(s))
              };
            }"""
        )
        print("names", names)
        assert names["utah"] and names["sd"] and names["wsh"] and names["cle"] and names["ath"]
        assert names["vikingsSay"] == "Minnesota Vikings"
        assert names["sixers"] == "Philadelphia Seventy Sixers"
        assert names["banned"] is False

        bad = page.evaluate(
            """async () => {
              const bad = [];
              for (const [id, items] of Object.entries(FlagGame.DATA)) {
                for (const item of items) {
                  const img = new Image();
                  img.src = item.img;
                  try {
                    await img.decode();
                    if (img.naturalWidth < 8) bad.push([id, item.name, img.naturalWidth]);
                  } catch (e) {
                    bad.push([id, item.name, 0]);
                  }
                }
              }
              return bad;
            }"""
        )
        print("bad images", bad)
        assert bad == []

        tiles = page.locator(".tile")
        assert tiles.count() == 8
        for gid in ("countries", "nfl", "nhl", "nba", "mlb", "mls"):
            label = page.locator(f'.tile[data-game="{gid}"]').inner_text()
            assert "0" in label, label
        page.screenshot(path=str(SHOTS / "home-landscape.png"))

        for gid, name in FORCED.items():
            found = show_named(page, gid, name)
            assert found["ok"], (gid, name)
            page.wait_for_timeout(350)
            light = page.evaluate("() => document.getElementById('game').classList.contains('light')")
            bg = page.evaluate("() => getComputedStyle(document.getElementById('game')).backgroundColor")
            src = page.evaluate("() => document.getElementById('flag').src")
            print(gid, "light", light, "bg", bg, "src", src[:48])
            if gid == "countries":
                assert light is False and bg == "rgb(38, 50, 56)"
                assert src.startswith("data:image/svg+xml")
            else:
                assert light is True and bg == "rgb(255, 255, 255)"
                assert f"/assets/logos/{gid}/" in src
            page.screenshot(path=str(SHOTS / f"play-{gid}.png"))
            before = page.evaluate("([id]) => ({...FlagGame.state[id]})", [gid])
            others = page.evaluate(
                """(id) => Object.fromEntries(Object.entries(FlagGame.state).filter(([k]) => k !== id).map(([k,v]) => [k, v.score + ':' + v.played]))""",
                gid,
            )
            said = page.evaluate(
                """() => new Promise(resolve => {
                  const orig = speechSynthesis.speak.bind(speechSynthesis);
                  speechSynthesis.speak = (u) => { speechSynthesis.speak = orig; resolve(u.text); try { return orig(u); } catch (e) { return undefined; } };
                  document.getElementById('ask').click();
                  setTimeout(() => resolve('TIMEOUT'), 800);
                })"""
            )
            shown = page.inner_text("#name")
            visible = page.locator("#name").is_visible()
            print("  ask", said, "shown", shown, "visible", visible)
            expected = page.evaluate("() => FlagGame.cur.say || FlagGame.cur.name")
            assert visible and shown == name and said == expected, (gid, said, shown, expected)
            page.screenshot(path=str(SHOTS / f"name-{gid}.png"))
            page.click("#yes")
            page.wait_for_timeout(200)
            page.screenshot(path=str(SHOTS / f"yes-{gid}.png"))
            page.wait_for_timeout(700)
            after = page.evaluate("([id]) => ({score: FlagGame.state[id].score, played: FlagGame.state[id].played})", [gid])
            others_after = page.evaluate(
                """(id) => Object.fromEntries(Object.entries(FlagGame.state).filter(([k]) => k !== id).map(([k,v]) => [k, v.score + ':' + v.played]))""",
                gid,
            )
            print("  score", before["score"], "->", after)
            assert after["score"] == before["score"] + 1
            assert after["played"] == before["played"] + 1
            assert others_after == others
            page.click("#no")
            page.wait_for_timeout(400)
            played_more = page.evaluate("([id]) => FlagGame.state[id].played", [gid])
            score_same = page.evaluate("([id]) => FlagGame.state[id].score", [gid])
            assert played_more == after["played"] + 1
            assert score_same == after["score"]
            page.click("#close")
            page.wait_for_timeout(150)
            home_knew = page.locator(f'.tile[data-game="{gid}"] .knew').inner_text()
            home_played = page.locator(f'.tile[data-game="{gid}"] .played').inner_text()
            assert home_knew == str(after["score"])
            assert home_played == str(played_more)

        page.screenshot(path=str(SHOTS / "home-after-play.png"))
        page.reload()
        page.wait_for_timeout(250)
        kept = page.locator(".tile[data-game='nfl'] .knew").inner_text()
        print("nfl after reload", kept)
        assert kept == "1"

        # Legacy country score still loads when the new key is absent.
        page.evaluate(
            """() => {
              localStorage.clear();
              localStorage.setItem('flaggame.score', '4');
              localStorage.setItem('flaggame.played', '9');
            }"""
        )
        page.reload()
        page.wait_for_timeout(200)
        assert page.locator(".tile[data-game='countries'] .knew").inner_text() == "4"
        assert page.locator(".tile[data-game='countries'] .played").inner_text() == "9"
        assert page.locator(".tile[data-game='nba'] .knew").inner_text() == "0"

        # No-repeat deck, including the wrap that avoids an immediate repeat.
        unique = page.evaluate(
            """() => {
              FlagGame.startGame('nhl');
              const n = FlagGame.DATA.nhl.length;
              FlagGame.state.nhl.deck = FlagGame.shuffle(n);
              FlagGame.state.nhl.pos = 0;
              const seen = [];
              for (let i = 0; i < n; i++) { FlagGame.nextItem(); seen.push(FlagGame.cur.name); }
              const last = FlagGame.cur.name;
              FlagGame.nextItem();
              return {unique: new Set(seen).size, n, wrappedDifferent: FlagGame.cur.name !== last};
            }"""
        )
        print("deck", unique)
        assert unique["unique"] == 32 and unique["wrappedDifferent"] is True

        page.click("#close")
        page.wait_for_timeout(100)
        messages = []
        page.once("dialog", lambda d: (messages.append(d.message), d.dismiss()))
        page.click("#reset")
        page.wait_for_timeout(100)
        assert page.locator(".tile[data-game='countries'] .knew").inner_text() == "4"
        assert "Grown-ups" in messages[0]
        page.once("dialog", lambda d: d.accept())
        page.click("#reset")
        page.wait_for_timeout(100)
        for gid in ("countries", "nfl", "nhl", "nba", "mlb", "mls"):
            assert page.locator(f'.tile[data-game="{gid}"] .knew').inner_text() == "0"
            assert page.locator(f'.tile[data-game="{gid}"] .played').inner_text() == "0"

        # Long names stay fully visible.
        show_named(page, "nba", "Portland Trail Blazers")
        page.click("#ask")
        page.wait_for_timeout(200)
        clipped = page.evaluate(
            """() => {
              const n = document.getElementById('name');
              return {text: n.textContent, hidden: n.scrollWidth - n.clientWidth};
            }"""
        )
        print("long name", clipped)
        assert clipped["text"] == "Portland Trail Blazers" and clipped["hidden"] <= 1
        page.screenshot(path=str(SHOTS / "long-name.png"))

        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(300)
        print("rotate portrait", page.locator("#rotate").is_visible())
        assert page.locator("#rotate").is_visible()
        page.screenshot(path=str(SHOTS / "portrait-rotate.png"))
        page.set_viewport_size({"width": 844, "height": 390})
        page.wait_for_timeout(200)
        assert page.locator("#rotate").is_visible() is False
        page.screenshot(path=str(SHOTS / "landscape-after-rotate.png"))

        page.set_viewport_size({"width": 667, "height": 375})
        page.click("#close")
        page.wait_for_timeout(200)
        page.screenshot(path=str(SHOTS / "home-667.png"))
        box = page.locator(".tile").first.bounding_box()
        print("tile box", box)
        assert box["width"] > 80 and box["height"] > 70

        page.set_viewport_size({"width": 844, "height": 390})
        page.evaluate(
            """() => {
              localStorage.setItem('flaggame.map.us', JSON.stringify(['CA','TX','NY','FL','WA','IL']));
              localStorage.setItem('flaggame.map.africa', JSON.stringify(['NGA','ZAF','EGY','ETH','KEN']));
            }"""
        )
        page.reload()
        page.wait_for_timeout(300)
        assert page.locator('.tile[data-game="us"] .knew').inner_text() == "6/50"
        assert "Countries" in page.locator('.tile[data-game="countries"]').inner_text()
        page.screenshot(path=str(SHOTS / "home-with-maps.png"))
        page.click('.tile[data-game="us"]')
        page.wait_for_timeout(200)
        assert page.locator("#usFind").is_visible()
        page.click("#usFind")
        page.wait_for_timeout(400)
        tiny = page.evaluate(
            """() => ['RI','DE','CT','NJ','MD','MA','VT','NH','HI'].map(id => {
              const b = document.querySelector('#mapSvg [data-id="'+id+'"] .hit').getBoundingClientRect();
              return {id, w: Math.round(b.width), h: Math.round(b.height)};
            })"""
        )
        print("tiny phone", tiny)
        for t in tiny:
            assert t["w"] >= 32 and t["h"] >= 32, t
        assert page.locator("#mapSvg .place.filled").count() == 6
        assert page.locator("#mapAsk").inner_text().strip() != ""
        page.screenshot(path=str(SHOTS / "us-find.png"))
        # A correct tap fills the prompted state. A wrong tap does not.
        before = page.evaluate("() => FlagGame.mapFilled('us').size")
        spot = page.evaluate(
            """() => {
              const place = FlagGame.mapCur;
              const svg = document.getElementById('mapSvg');
              const pt = svg.createSVGPoint();
              pt.x = place.cx; pt.y = place.cy;
              const s = pt.matrixTransform(svg.getScreenCTM());
              return {x: s.x, y: s.y, id: place.id, name: place.name};
            }"""
        )
        print("tap", spot)
        page.mouse.click(spot["x"], spot["y"])
        page.wait_for_timeout(900)
        after = page.evaluate("() => FlagGame.mapFilled('us').size")
        print("filled", before, "->", after)
        assert after == before + 1, (before, after, spot)
        # Wrong tap flashes the answer and leaves it unfilled.
        wrong_name = page.locator("#mapAsk").inner_text().strip()
        page.evaluate(
            """() => {
              const cur = FlagGame.mapCur.id;
              const other = FlagGame.MAPS.us.places.find(p => p.id !== cur && !FlagGame.mapFilled('us').has(p.id));
              const svg = document.getElementById('mapSvg');
              const pt = svg.createSVGPoint();
              pt.x = other.cx; pt.y = other.cy;
              const s = pt.matrixTransform(svg.getScreenCTM());
              window.__wrong = {x: s.x, y: s.y, id: other.id};
            }"""
        )
        wrong = page.evaluate("() => window.__wrong")
        page.mouse.click(wrong["x"], wrong["y"])
        page.wait_for_timeout(400)
        assert page.locator(f'#mapSvg [data-id="{page.evaluate("() => FlagGame.mapCur.id")}"]').count() == 1
        flashed = page.evaluate("() => !!document.querySelector('#mapSvg .place.flash')")
        print("flash", flashed, "prompt was", wrong_name)
        assert flashed
        page.wait_for_timeout(1400)
        still = page.evaluate("() => FlagGame.mapFilled('us').size")
        assert still == after
        # Back home, then world maps.
        page.click("#mapClose")
        page.wait_for_timeout(150)
        page.click("#usClose")
        page.wait_for_timeout(150)
        page.click('.tile[data-game="world"]')
        page.wait_for_timeout(200)
        assert page.locator(".cont").count() == 6
        africa = page.locator('.cont[data-cont="africa"]')
        assert "5/51" in africa.inner_text()
        page.screenshot(path=str(SHOTS / "world-continents.png"))
        africa.click()
        page.wait_for_timeout(150)
        page.click("#worldFind")
        page.wait_for_timeout(400)
        assert page.locator("#mapSvg .place.filled").count() == 5
        assert page.locator("#mapAsk").inner_text().strip() != ""
        page.screenshot(path=str(SHOTS / "africa-find.png"))
        page.click("#mapClose")
        page.wait_for_timeout(100)
        page.once("dialog", lambda d: d.accept())
        page.click("#worldReset")
        page.wait_for_timeout(150)
        assert page.locator("#worldProgress").inner_text().startswith("0 of ")
        # Tablet: tiny states stay tappable.
        page.click("#worldModeClose")
        page.click("#worldClose")
        page.set_viewport_size({"width": 1180, "height": 820})
        page.wait_for_timeout(200)
        page.click('.tile[data-game="us"]')
        page.click("#usFind")
        page.wait_for_timeout(300)
        tiny_tab = page.evaluate(
            """() => ['RI','DE','HI'].map(id => {
              const b = document.querySelector('#mapSvg [data-id="'+id+'"] .hit').getBoundingClientRect();
              return {id, w: Math.round(b.width), h: Math.round(b.height)};
            })"""
        )
        print("tiny tablet", tiny_tab)
        for t in tiny_tab:
            assert t["w"] >= 32 and t["h"] >= 32, t
        page.screenshot(path=str(SHOTS / "us-find-tablet.png"))
        assert page.locator("#rotate").is_visible() is False

        print("external", reqs)
        print("errors", errors)
        assert reqs == []
        assert errors == []
        browser.close()
    print("OK")


if __name__ == "__main__":
    main()
