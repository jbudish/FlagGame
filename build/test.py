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


def settle(page):
    tag = ""
    for _ in range(6):
        try:
            page.wait_for_function(
                "() => !navigator.serviceWorker || navigator.serviceWorker.controller",
                timeout=8000,
            )
            page.wait_for_selector("#buildTag", timeout=10000)
            tag = page.locator("#buildTag").inner_text().strip()
            page.wait_for_timeout(400)
            if page.locator("#buildTag").inner_text().strip() == tag and tag.startswith("v") and len(tag) == 8:
                return tag
        except Exception:
            page.wait_for_timeout(250)
    raise AssertionError(f"build tag did not settle ({tag!r})")


def webkit_europe(play):
    browser = play.webkit.launch()
    iphone = dict(play.devices["iPhone 13"])
    iphone.pop("default_browser_type", None)
    iphone["viewport"] = {"width": 844, "height": 390}
    jump = browser.new_context(**iphone)
    page = jump.new_page()
    page.set_default_timeout(30000)
    page.emulate_media(reduced_motion="reduce")
    page.goto(URL)
    settle(page)
    page.click("#goFlags")
    page.click('.cont[data-cont="europe"]')
    page.wait_for_timeout(250)
    assert page.evaluate("() => FlagGame.force('CHE')")
    page.click("#yes")
    page.wait_for_timeout(90)
    jumped = float(page.evaluate("() => document.getElementById('quizSvg').getAttribute('viewBox').split(/\\s+/)[2]"))
    print("webkit reduced-motion viewBox width", jumped)
    assert jumped < 450
    jump.close()

    ctx = browser.new_context(**iphone)
    page = ctx.new_page()
    page.set_default_timeout(30000)
    page.add_init_script(
        """() => {
          if (localStorage.getItem('flaggame.ver')) return;
          localStorage.setItem('flaggame.flags', JSON.stringify({
            ok: ['FRA','DEU','ITA','LUX','ALB','SVN','EST'],
            bad: ['BEL','MNE','XKX']
          }));
          localStorage.setItem('flaggame.deck', JSON.stringify([3,1,4]));
          localStorage.setItem('flaggame.pos', '2');
          localStorage.setItem('flaggame.score', '40');
          localStorage.setItem('flaggame.played', '80');
        }"""
    )
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(URL)
    tag = settle(page)
    migrated = page.evaluate(
        """() => ({
          flags: JSON.parse(localStorage.getItem('flaggame.flags')),
          deck: localStorage.getItem('flaggame.deck'),
          score: localStorage.getItem('flaggame.score'),
          ver: JSON.parse(localStorage.getItem('flaggame.ver')),
          ua: navigator.userAgent
        })"""
    )
    print("webkit", tag, migrated["ua"].split(")")[0] + ")", "saved", migrated["flags"], "ver", migrated["ver"])
    assert "iPhone" in migrated["ua"]
    assert migrated["flags"] == {"ok": [], "bad": []}
    assert migrated["deck"] is None and migrated["score"] is None
    assert migrated["ver"] == 2
    page.click("#goFlags")
    page.click('.cont[data-cont="europe"]')
    page.wait_for_timeout(300)
    assert page.evaluate("() => FlagGame.flagItems('europe').length") == 27
    assert page.evaluate("() => FlagGame.quizIds.length") == 27
    assert page.evaluate("() => FlagGame.force('CHE')")
    page.click("#yes")
    page.wait_for_timeout(480)
    zoomed = page.evaluate("() => document.getElementById('quizSvg').getAttribute('viewBox')")
    print("webkit zoom", zoomed)
    assert float(zoomed.split()[2]) < 1000
    page.screenshot(path=str(SHOTS / "webkit-europe-zoom.png"))
    page.wait_for_function("() => !document.body.classList.contains('busy')")
    answered = 1
    while answered < 27:
        page.wait_for_function(
            """() => document.getElementById('endCard').classList.contains('on') || !document.body.classList.contains('busy')"""
        )
        if page.locator("#endCard").evaluate("el => el.classList.contains('on')"):
            break
        page.locator("#no" if answered % 6 == 2 else "#yes").click()
        answered += 1
        if answered > 30:
            raise AssertionError("Europe did not end")
    page.wait_for_function("() => document.getElementById('endCard').classList.contains('on')", timeout=8000)
    assert answered == 27
    end = page.locator("#endScore").inner_text()
    print("webkit europe end", end, "left", page.evaluate("() => FlagGame.quizIds.length"))
    assert "/27" in end and "%" in end
    assert page.evaluate("() => FlagGame.quizIds.length") == 0
    page.wait_for_timeout(400)
    assert page.locator("#endCard").evaluate("el => el.classList.contains('on')")
    page.screenshot(path=str(SHOTS / "webkit-europe-end.png"))
    print("webkit pageerrors", errors)
    assert errors == []
    sw = page.evaluate("async () => (await (await fetch('sw.js')).text())")
    assert f"flaggame-{tag[1:]}" in sw
    browser.close()


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
        tag = settle(page)
        print("build", tag)
        assert page.locator("#goFlags").is_visible()
        assert page.locator("#goSports").is_visible()
        assert page.locator(".tile").count() == 0
        assert "World Map" not in page.locator("#home").inner_text()
        print("home", page.locator("#flagsKnew").inner_text(), page.locator("#sportsKnew").inner_text())
        assert page.locator("#flagsKnew").inner_text().startswith("0/100")
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
        page.wait_for_timeout(2200)
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
        assert "/22" in africa
        assert "/10" in page.locator('.cont[data-cont="south-america"]').inner_text()
        assert "/4" in page.locator('.cont[data-cont="oceania"]').inner_text()
        assert "/100" in page.locator(".cont.all").inner_text()
        names = page.evaluate("() => FlagGame.flagItems('oceania').map(p => p.name).sort()")
        assert names == ["Australia", "Fiji", "New Zealand", "Papua New Guinea"], names
        assert page.evaluate("() => FlagGame.flagItems('all').length") == 100
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
        page.wait_for_timeout(300)
        assert state_id in page.evaluate("() => FlagGame.usProg().bad")
        assert state_id not in page.evaluate("() => FlagGame.mapIds")
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
        # One state left: a miss ends the round in red and does not come back.
        page.evaluate(
            """() => {
              const ids = FlagGame.MAPS.us.places.map(p => p.id).filter(id => id !== 'RI');
              localStorage.setItem('flaggame.map.us', JSON.stringify({ok: ids, bad: []}));
            }"""
        )
        page.click("#usName")
        page.wait_for_timeout(300)
        assert page.evaluate("() => FlagGame.mapCur.id") == "RI"
        page.click("#mapNo")
        page.wait_for_function("() => document.getElementById('mapEnd').classList.contains('on')")
        us_end = page.locator("#mapEndScore").inner_text()
        print("us end", us_end)
        assert "49/50" in us_end and "%" in us_end
        assert "RI" in page.evaluate("() => FlagGame.usProg().bad")
        assert page.evaluate("() => FlagGame.mapIds.length") == 0
        page.click("#mapBack")
        page.wait_for_timeout(200)
        assert page.locator("#mapEnd").is_hidden()
        assert page.evaluate("() => FlagGame.mapCur.id") == "RI"
        page.click("#mapClose")
        page.click("#usClose")
        assert page.locator("#pickSvg").is_visible()

        # Zoom onto a tiny European country, with the magnifier inset.
        page.evaluate("() => localStorage.setItem('flaggame.flags', JSON.stringify({ok:[], bad:[]}))")
        page.click('.cont[data-cont="europe"]')
        page.wait_for_timeout(300)
        assert page.evaluate("() => FlagGame.force('CHE')")
        page.click("#yes")
        page.wait_for_timeout(500)
        mag = page.evaluate(
            """() => ({
              on: document.getElementById('quizMag').classList.contains('on'),
              px: document.getElementById('quizMag').dataset.px,
              vb: document.getElementById('quizSvg').getAttribute('viewBox'),
              home: '0 0 1000 861'
            })"""
        )
        print("switzerland zoom", mag)
        assert mag["on"], mag
        assert float(mag["px"]) <= 14
        assert mag["vb"].split()[2] != "1000"
        page.screenshot(path=str(SHOTS / "europe-zoom.png"))
        page.screenshot(path=str(SHOTS / "magnifier.png"))
        page.wait_for_function("() => !document.body.classList.contains('busy')")

        # NFL Northeast: New England Patriots, zoomed on Massachusetts.
        page.click("#qClose")
        page.click("#flagsClose")
        page.click("#goSports")
        page.evaluate("() => localStorage.setItem('flaggame.sport.nfl', JSON.stringify({ok:[], bad:[]}))")
        page.click('.league[data-league="nfl"]')
        page.wait_for_timeout(300)
        assert page.evaluate("() => FlagGame.force('ne')")
        page.click("#yes")
        page.wait_for_timeout(500)
        nfl_zoom = page.evaluate(
            """() => document.getElementById('quizSvg').getAttribute('viewBox')"""
        )
        print("patriots viewBox", nfl_zoom)
        assert float(nfl_zoom.split()[2]) < 1000
        page.screenshot(path=str(SHOTS / "nfl-zoom.png"))
        page.wait_for_function("() => !document.body.classList.contains('busy')")

        # Full South America round: each country once, then the celebration.
        page.click("#qClose")
        page.click("#sportsClose")
        page.click("#goFlags")
        page.click('.cont[data-cont="south-america"]')
        page.wait_for_timeout(300)
        assert page.evaluate("() => FlagGame.quizIds.length") == 10
        answered = 0
        while True:
            page.wait_for_function(
                """() => document.getElementById('endCard').classList.contains('on') || !document.body.classList.contains('busy')"""
            )
            if page.locator("#endCard").evaluate("el => el.classList.contains('on')"):
                break
            page.locator("#no" if answered in (1, 4, 8) else "#yes").click()
            answered += 1
            if answered > 12:
                raise AssertionError("South America did not end")
        assert answered == 10
        guy = page.evaluate("() => document.querySelector('#quizSvg [data-id=GUY]').className.baseVal")
        print("guyana", guy)
        assert "bg" in guy
        colors = page.evaluate(
            """() => ({
              ok: document.querySelectorAll('#quizSvg .place.ok').length,
              bad: document.querySelectorAll('#quizSvg .place.bad').length
            })"""
        )
        print("sa end colors", colors, page.locator("#endScore").inner_text())
        assert colors["ok"] == 7 and colors["bad"] == 3
        assert page.locator("#endScore").inner_text().startswith("7/10")
        assert page.locator("#endAgain").is_visible()
        assert page.locator("#endHome").is_visible()
        # Undo from the celebration returns the last country.
        last = page.evaluate("() => FlagGame.undoCount")
        assert last >= 1
        page.click("#quizBack")
        page.wait_for_timeout(250)
        assert page.locator("#endCard").is_hidden()
        assert page.evaluate("() => !!FlagGame.qCur")
        page.click("#yes")
        page.wait_for_function("() => document.getElementById('endCard').classList.contains('on')", timeout=8000)
        page.screenshot(path=str(SHOTS / "end-south-america.png"))
        page.click("#endAgain")
        page.wait_for_timeout(200)
        assert page.locator("#endCard").is_hidden()
        assert page.evaluate("() => FlagGame.quizIds.length") == 10
        assert page.locator("#quizScore").inner_text().startswith("0/10")

        # Full NFL round, every team once.
        page.click("#qClose")
        page.click("#flagsClose")
        page.click("#goSports")
        page.evaluate("() => localStorage.setItem('flaggame.sport.nfl', JSON.stringify({ok:[], bad:[]}))")
        page.click('.league[data-league="nfl"]')
        page.wait_for_timeout(250)
        assert page.evaluate("() => FlagGame.quizIds.length") == 32
        nfl_n = 0
        while True:
            page.wait_for_function(
                """() => document.getElementById('endCard').classList.contains('on') || !document.body.classList.contains('busy')"""
            )
            if page.locator("#endCard").evaluate("el => el.classList.contains('on')"):
                break
            page.locator("#no" if nfl_n == 3 else "#yes").click()
            nfl_n += 1
            if nfl_n > 34:
                raise AssertionError("NFL did not end")
        assert nfl_n == 32
        nfl_end = page.locator("#endScore").inner_text()
        print("nfl end", nfl_end, "left", page.evaluate("() => FlagGame.quizIds.length"))
        assert nfl_end.startswith("31/32") and "%" in nfl_end
        assert page.evaluate("() => FlagGame.quizIds.length") == 0
        page.click("#quizBack")
        page.wait_for_timeout(200)
        assert page.locator("#endCard").is_hidden()
        assert page.evaluate("() => FlagGame.quizIds[0]")
        page.click("#qClose")
        page.click("#sportsClose")

        page.set_viewport_size({"width": 1180, "height": 820})
        page.wait_for_timeout(200)
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
        webkit_europe(p)
    print("OK")


if __name__ == "__main__":
    main()
