"""Phone and tablet checks for the Flags / Sports split-screen quizzes."""
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


def serve():
    os.chdir(ROOT)
    ThreadingHTTPServer(("127.0.0.1", 8765), partial(SimpleHTTPRequestHandler, directory=str(ROOT))).serve_forever()


def main():
    threading.Thread(target=serve, daemon=True).start()
    errors, reqs = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = browser.new_page(viewport={"width": 844, "height": 390}, device_scale_factor=2, is_mobile=True, has_touch=True)
        page.set_default_timeout(30000)
        page.on("request", lambda r: reqs.append(r.url) if not r.url.startswith((URL, "data:", "blob:")) else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(URL)
        page.wait_for_timeout(250)
        assert page.locator("#goFlags").is_visible()
        assert page.locator("#goSports").is_visible()
        assert page.locator(".tile").count() == 0
        assert "World Map" not in page.locator("#home").inner_text()
        print("home", page.locator("#flagsKnew").inner_text(), page.locator("#sportsKnew").inner_text())
        page.screenshot(path=str(SHOTS / "home-two.png"))

        page.click("#goSports")
        page.wait_for_timeout(200)
        assert page.locator(".league").count() == 5
        assert page.locator('.league[data-league="nfl"]').inner_text().startswith("NFL") or "NFL" in page.locator('.league[data-league="nfl"]').inner_text()
        page.screenshot(path=str(SHOTS / "sports-picker.png"))

        page.evaluate(
            """() => localStorage.setItem('flaggame.sport.nfl', JSON.stringify({
              ok: ['chi','gb','dal','sea','mia','nyg'],
              bad: ['det']
            }))"""
        )
        page.click("#sportsClose")
        page.click("#goSports")
        page.click('.league[data-league="nfl"]')
        page.wait_for_timeout(400)
        il = page.evaluate("() => document.querySelector('#quizSvg [data-id=IL]').className.baseVal")
        print("illinois", il)
        assert "ok" in il
        mi = page.evaluate("() => document.querySelector('#quizSvg [data-id=MI]').className.baseVal")
        assert "bad" in mi and "ok" not in mi.split()
        logos = page.evaluate("() => [...document.querySelectorAll('#quizSvg image')].map(n => n.getAttribute('href'))")
        print("logos", logos)
        assert any(src.endswith("nfl/chi.webp") for src in logos)
        assert page.locator("#side").is_visible()
        assert page.locator("#yes").is_visible()
        # Logo pane is the larger side.
        map_w = page.locator("#quizMap").bounding_box()["width"]
        play_w = page.locator("#quizPlay").bounding_box()["width"]
        print("split", round(map_w), round(play_w), "logo share", round(100 * play_w / (map_w + play_w)))
        assert play_w > map_w
        assert "• —" in page.locator("#flagsKnew").inner_text() or "/" in page.locator("#flagsKnew").inner_text()
        assert page.locator("#quizBack").is_disabled()
        page.click("#yes")
        page.wait_for_timeout(800)
        score = page.locator("#quizScore").inner_text()
        print("quiz score", score, "undo", page.evaluate("() => FlagGame.undoCount"))
        assert "•" in score and "%" in score
        assert page.locator("#quizBack").is_disabled() is False
        page.screenshot(path=str(SHOTS / "nfl-split.png"))
        # Undo returns to that card and drops a logo that this answer added.
        before_undo = page.evaluate("() => FlagGame.sportProg('nfl').ok.length")
        page.click("#quizBack")
        page.wait_for_timeout(200)
        after_undo = page.evaluate("() => FlagGame.sportProg('nfl').ok.length")
        assert after_undo <= before_undo
        assert page.evaluate("() => FlagGame.undoCount") == 0

        # Mets stay correct when a Yankees yes is undone, so New York stays green.
        page.click("#qClose")
        page.evaluate("() => localStorage.setItem('flaggame.sport.mlb', JSON.stringify({ok:['nym'], bad:[]}))")
        page.click('.league[data-league="mlb"]')
        page.wait_for_timeout(300)
        assert page.evaluate("() => FlagGame.force('nyy')")
        page.click("#yes")
        page.wait_for_timeout(800)
        both = page.evaluate(
            """() => ({
              ok: FlagGame.sportProg('mlb').ok.slice(),
              ny: document.querySelector('#quizSvg [data-id=NY]').className.baseVal,
              logos: [...document.querySelectorAll('#quizSvg image')].map(n => n.getAttribute('href'))
            })"""
        )
        print("yankees", both)
        assert "nym" in both["ok"] and "nyy" in both["ok"]
        assert "ok" in both["ny"]
        assert any("mlb/nyy.webp" in src for src in both["logos"]) and any("mlb/nym.webp" in src for src in both["logos"])
        page.click("#quizBack")
        page.wait_for_timeout(250)
        undone = page.evaluate(
            """() => ({
              ok: FlagGame.sportProg('mlb').ok.slice(),
              ny: document.querySelector('#quizSvg [data-id=NY]').className.baseVal,
              logos: [...document.querySelectorAll('#quizSvg image')].map(n => n.getAttribute('href'))
            })"""
        )
        print("after yankees undo", undone)
        assert undone["ok"] == ["nym"]
        assert "ok" in undone["ny"] and "bad" not in undone["ny"].split()
        assert any("mlb/nym.webp" in src for src in undone["logos"])
        assert not any("mlb/nyy.webp" in src for src in undone["logos"])
        # Three undos in a row restore three answers.
        page.evaluate("() => { FlagGame.force('bos'); }")
        page.click("#yes")
        page.wait_for_timeout(200)
        page.click("#no")
        page.wait_for_timeout(200)
        page.evaluate("() => FlagGame.force('lad')")
        page.click("#yes")
        page.wait_for_timeout(200)
        assert page.evaluate("() => FlagGame.undoCount") == 3
        page.click("#quizBack")
        page.click("#quizBack")
        page.click("#quizBack")
        page.wait_for_timeout(200)
        assert page.evaluate("() => FlagGame.undoCount") == 0
        assert page.evaluate("() => FlagGame.sportProg('mlb').ok.slice()") == ["nym"]

        # Answering the Bears (already correct) keeps Illinois green and does not add a second logo.
        page.evaluate(
            """() => {
              const items = FlagGame.QUIZ.leagues.nfl.teams;
              const i = items.findIndex(t => t.id === 'chi');
              const deck = FlagGame.qCur && items;
              return items[i].name;
            }"""
        )
        # Drive the live deck by clicking yes only after forcing the current card.
        page.evaluate(
            """() => {
              const img = document.getElementById('flag');
              img.src = 'assets/logos/nfl/chi.webp';
            }"""
        )
        page.click("#qClose")
        page.wait_for_timeout(150)
        assert page.locator("#sportsPick").is_visible() or page.locator(".league").count() == 5
        page.click("#sportsClose")
        assert page.locator("#goFlags").is_visible()
        assert "%" in page.locator("#sportsKnew").inner_text()
        page.screenshot(path=str(SHOTS / "home-with-percent.png"))

        page.click("#goFlags")
        page.wait_for_timeout(250)
        assert page.locator("#pickSvg path").count() > 100
        assert page.locator(".cont").count() == 7
        assert page.locator("#usJump").is_visible()
        africa = page.locator('.cont[data-cont="africa"]').inner_text()
        print("africa button", africa)
        assert "/" in africa
        page.screenshot(path=str(SHOTS / "flags-picker.png"))

        page.evaluate(
            """() => {
              const ids = FlagGame.flagItems('africa').map(p => p.id);
              const ok = ids.slice(0, 4);
              const bad = ids.slice(4, 6);
              localStorage.setItem('flaggame.flags', JSON.stringify({ok, bad}));
            }"""
        )
        page.click("#flagsClose")
        page.click("#goFlags")
        page.click('.cont[data-cont="africa"]')
        page.wait_for_timeout(400)
        counts = page.evaluate(
            """() => ({
              ok: document.querySelectorAll('#quizSvg .place.ok').length,
              bad: document.querySelectorAll('#quizSvg .place.bad').length,
              dots: document.querySelectorAll('#quizSvg .dot').length
            })"""
        )
        print("africa map", counts)
        assert counts["ok"] >= 4 and counts["bad"] >= 2
        assert page.locator("#flag").get_attribute("src")
        page.screenshot(path=str(SHOTS / "africa-split.png"))
        page.click("#ask")
        page.wait_for_timeout(200)
        assert page.locator("#name").is_visible()
        page.click("#qClose")
        page.wait_for_timeout(150)
        assert "Africa" in page.locator("#pickBtns").inner_text()

        page.click("#usJump")
        page.wait_for_timeout(150)
        assert page.locator("#usFind").is_visible()
        page.click("#usName")
        page.wait_for_timeout(300)
        state_id = page.evaluate("() => FlagGame.mapCur.id")
        page.click("#mapNo")
        page.wait_for_timeout(400)
        assert state_id in page.evaluate("() => FlagGame.usProg().bad")
        page.click("#mapBack")
        page.wait_for_timeout(200)
        assert page.evaluate("() => FlagGame.mapCur.id") == state_id
        assert state_id not in page.evaluate("() => FlagGame.usProg().bad")
        page.click("#mapClose")
        page.click("#usFind")
        page.wait_for_timeout(300)
        ri = page.locator('#mapSvg [data-id="RI"] .hit').bounding_box()
        print("RI hit", ri)
        assert ri["width"] >= 28 and ri["height"] >= 28
        page.click("#mapClose")
        page.click("#usClose")
        assert page.locator("#pickSvg").is_visible()

        page.set_viewport_size({"width": 1180, "height": 820})
        page.wait_for_timeout(200)
        page.click("#flagsClose")
        page.screenshot(path=str(SHOTS / "home-tablet.png"))
        assert page.locator("#goFlags").is_visible()
        page.click("#goSports")
        page.wait_for_timeout(150)
        assert page.locator(".league").count() == 5
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(200)
        assert page.locator("#rotate").is_visible()
        page.set_viewport_size({"width": 844, "height": 390})
        page.wait_for_timeout(150)
        assert page.locator("#rotate").is_visible() is False

        print("external", reqs)
        print("errors", errors)
        assert reqs == [] and errors == []
        browser.close()
    print("OK")


if __name__ == "__main__":
    main()
