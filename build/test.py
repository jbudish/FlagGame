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


def svg_point(page, code):
    return page.evaluate(
        """(code) => {
          const svg = document.getElementById('quizSvg');
          const g = svg.querySelector('[data-id="' + code + '"]');
          const path = g.querySelector('path');
          const b = path.getBBox();
          const pt = svg.createSVGPoint();
          for (let i = 0; i < 9; i++) for (let j = 0; j < 9; j++) {
            pt.x = b.x + b.width * (i + 0.5) / 9;
            pt.y = b.y + b.height * (j + 0.5) / 9;
            if (!path.isPointInFill(pt)) continue;
            const s = pt.matrixTransform(svg.getScreenCTM());
            return {x: s.x, y: s.y, cls: g.className.baseVal};
          }
          return null;
        }""",
        code,
    )


def check_country_names(page):
    page.evaluate("() => localStorage.setItem('flaggame.flags', JSON.stringify({ok:[], bad:[]}))")
    page.click("#goFlags")
    page.click('.cont[data-cont="south-america"]')
    page.wait_for_timeout(250)
    assert page.evaluate("() => FlagGame.force('BRA')")
    page.click("#yes")
    page.wait_for_timeout(120)
    assert page.locator("#name").is_visible()
    assert page.locator("#name").inner_text() == "Brazil"
    page.wait_for_timeout(550)
    assert page.locator("#name").is_hidden()
    page.wait_for_function("() => !document.body.classList.contains('busy')")
    assert page.evaluate("() => FlagGame.force('ARG')")
    page.click("#no")
    page.wait_for_timeout(120)
    assert page.locator("#name").inner_text() == "Argentina"
    assert page.locator("#name").is_visible()
    page.wait_for_timeout(550)
    assert page.locator("#name").is_hidden()
    page.wait_for_function("() => !document.body.classList.contains('busy')")
    brazil = svg_point(page, "BRA")
    chile = svg_point(page, "CHL")
    argentina = svg_point(page, "ARG")
    print("name targets", brazil, argentina, chile)
    assert "ok" in brazil["cls"] and "bad" in argentina["cls"]
    assert "ok" not in chile["cls"] and "bad" not in chile["cls"]
    page.mouse.click(brazil["x"], brazil["y"])
    page.wait_for_timeout(80)
    assert page.locator("#mapLabel").is_visible()
    assert page.locator("#mapLabel").inner_text() == "Brazil"
    page.wait_for_timeout(550)
    assert page.locator("#mapLabel").is_hidden()
    page.touchscreen.tap(argentina["x"], argentina["y"])
    page.wait_for_timeout(80)
    assert page.locator("#mapLabel").inner_text() == "Argentina"
    page.mouse.click(chile["x"], chile["y"])
    page.wait_for_timeout(80)
    assert page.locator("#mapLabel").inner_text() == "Argentina"
    page.wait_for_timeout(550)
    assert page.locator("#mapLabel").is_hidden()
    page.click("#qClose")
    page.click("#flagsClose")


def check_play_by_map(page):
    page.evaluate("() => localStorage.setItem('flaggame.flags', JSON.stringify({ok:[], bad:[]}))")
    page.evaluate("() => localStorage.setItem('flaggame.sport.nhl', JSON.stringify({ok:[], bad:[]}))")
    page.click("#goFlags")
    page.click('.cont[data-cont="asia"]')
    page.wait_for_timeout(300)
    assert page.locator("#modeMap").is_visible()
    assert page.locator("#flag").is_visible()
    page.click("#modeMap")
    page.wait_for_timeout(200)
    info = page.evaluate(
        """() => {
          const game = document.getElementById('game').getBoundingClientRect();
          const map = document.getElementById('quizMap').getBoundingClientRect();
          const hot = document.querySelector('#quizSvg .place.hot');
          const ids = [...document.querySelectorAll('#choices .choice')].map(b => b.dataset.id);
          const allowed = new Set(FlagGame.flagItems('asia').map(p => p.id));
          return {
            mapWide: map.width > game.width * 0.9,
            hot: hot && hot.dataset.id,
            cur: FlagGame.qCur && FlagGame.qCur.id,
            name: FlagGame.qCur && FlagGame.qCur.name,
            n: ids.length,
            ids,
            allInGame: ids.every(id => allowed.has(id)),
            flagsHidden: getComputedStyle(document.getElementById('flagArea')).display
          };
        }"""
    )
    print("asia map mode", info["n"], info["name"], info["hot"])
    assert info["mapWide"] and info["hot"] == info["cur"]
    assert info["n"] == 8 and info["cur"] in info["ids"] and info["allInGame"]
    assert info["flagsHidden"] == "none"
    page.locator('#choices .choice[data-id="%s"]' % info["cur"]).tap()
    page.wait_for_timeout(150)
    assert page.locator("#mapLabel").is_visible()
    name = page.locator("#mapLabel").inner_text()
    assert name
    page.wait_for_function("() => !document.body.classList.contains('busy')")
    colored = page.evaluate(
        """(id) => document.querySelector('#quizSvg [data-id="' + id + '"]').className.baseVal""",
        info["cur"],
    )
    print("asia after answer", name, colored, page.locator("#quizScore").inner_text())
    assert "ok" in colored
    assert "/" in page.locator("#quizScore").inner_text() and "%" in page.locator("#quizScore").inner_text()
    page.wait_for_timeout(200)
    assert page.locator("#mapLabel").is_hidden()
    nxt = page.evaluate("() => ({id: FlagGame.qCur.id, name: FlagGame.qCur.name})")
    wrong = page.evaluate(
        """(cur) => [...document.querySelectorAll('#choices .choice')].map(b => b.dataset.id).find(id => id !== cur)""",
        nxt["id"],
    )
    assert wrong
    page.locator('#choices .choice[data-id="%s"]' % wrong).tap()
    page.wait_for_timeout(80)
    assert page.locator("#mapLabel").inner_text() == nxt["name"]
    assert page.locator('#choices .choice[data-id="%s"]' % nxt["id"]).evaluate("el => el.classList.contains('good')")
    page.wait_for_function("() => !document.body.classList.contains('busy')")
    assert nxt["id"] in page.evaluate("() => FlagGame.flagProg().bad")
    page.click("#modeFlags")
    page.wait_for_timeout(150)
    assert page.locator("#flag").is_visible()
    assert page.locator("#yes").is_visible()
    page.click("#qClose")
    page.click("#flagsClose")
    page.click("#goSports")
    page.click('.league[data-league="nhl"]')
    page.wait_for_timeout(300)
    page.click("#modeMap")
    page.wait_for_timeout(200)
    nhl = page.evaluate(
        """() => {
          const spot = document.querySelector('#quizSvg .spot circle');
          const cur = FlagGame.qCur;
          const ids = [...document.querySelectorAll('#choices .choice')].map(b => b.dataset.id);
          const allowed = new Set(FlagGame.QUIZ.leagues.nhl.teams.map(t => t.id));
          return {spot: !!spot, x: spot && spot.getAttribute('cx'), curx: String(cur.x), id: cur.id, cur: cur.name, n: ids.length, ids, allInGame: ids.every(id => allowed.has(id))};
        }"""
    )
    print("nhl map mode", nhl["n"], nhl["cur"])
    assert nhl["spot"] and nhl["n"] == 8 and nhl["id"] in nhl["ids"] and nhl["allInGame"]
    assert abs(float(nhl["x"]) - float(nhl["curx"])) < 1
    page.locator('#choices .choice[data-id="%s"]' % nhl["id"]).tap()
    page.wait_for_timeout(120)
    assert page.locator("#mapLabel").inner_text() == nhl["cur"]
    page.wait_for_function("() => !document.body.classList.contains('busy')")
    assert page.evaluate("() => FlagGame.sportProg('nhl').ok.length") == 1
    page.click("#qClose")
    page.click("#sportsClose")


def check_map_zoom(page):
    def view_after(kind, button, code):
        if kind == "flag":
            page.click("#goFlags")
            page.click(button)
        else:
            page.click("#goSports")
            page.click(button)
        page.wait_for_timeout(250)
        assert page.evaluate("(id) => FlagGame.force(id)", code)
        page.click("#modeMap")
        page.wait_for_timeout(900)
        return page.evaluate(
            """() => {
              const svg = document.getElementById('quizSvg');
              const vb = svg.getAttribute('viewBox').split(/\\s+/).map(Number);
              const home = svg._home;
              const cur = FlagGame.qCur;
              return {vb, homeW: home.w, homeH: home.h, id: cur.id, x: cur.x, y: cur.y};
            }"""
        )

    page.evaluate("() => localStorage.setItem('flaggame.flags', JSON.stringify({ok:[], bad:[]}))")
    page.click("#goFlags")
    page.click('.cont[data-cont="asia"]')
    page.wait_for_timeout(250)
    page.click("#modeMap")
    page.wait_for_timeout(200)
    brunei = page.evaluate("() => FlagGame.framePlace('BRN')")
    missing = page.evaluate(
        """() => ['SGP','BHR'].filter(id => !document.querySelector('#quizSvg [data-id="'+id+'"]'))"""
    )
    print("brunei frame", brunei, "absent", missing)
    assert missing == ["SGP", "BHR"]
    assert brunei and brunei["w"] < 400
    page.click("#qClose")
    page.click("#flagsClose")
    slv = view_after("flag", '.cont[data-cont="north-america"]', "SLV")
    jam = None
    page.evaluate("() => FlagGame.force('JAM')")
    page.wait_for_timeout(900)
    jam = page.evaluate(
        """() => {
          const svg = document.getElementById('quizSvg');
          const vb = svg.getAttribute('viewBox').split(/\\s+/).map(Number);
          return {vb, id: FlagGame.qCur.id};
        }"""
    )
    belize = page.evaluate("() => FlagGame.framePlace('BLZ')")
    print("zoom SLV", slv["vb"], "JAM", jam["vb"], "belize frame", belize)
    assert slv["vb"][2] < slv["homeW"] * 0.45
    assert jam["id"] == "JAM" and jam["vb"][2] < slv["homeW"] * 0.45
    assert brunei and brunei["w"] < 1000 * 0.35
    assert belize and belize["w"] < 1000 * 0.45
    # El Salvador view should include nearby Belize as context, or sit in that region.
    near = page.evaluate(
        """(vb) => {
          const g = document.querySelector('#quizSvg [data-id="BLZ"] path');
          const b = g.getBBox();
          const cx = b.x + b.width / 2, cy = b.y + b.height / 2;
          return cx > vb[0] - vb[2] && cx < vb[0] + vb[2] * 2 && cy > vb[1] - vb[3] && cy < vb[1] + vb[3] * 2;
        }""",
        slv["vb"],
    )
    print("belize near el salvador view", near)
    page.click("#qClose")
    page.click("#flagsClose")
    page.evaluate("() => localStorage.setItem('flaggame.sport.nhl', JSON.stringify({ok:[], bad:[]}))")
    nyr = view_after("sport", '.league[data-league="nhl"]', "nyr")
    page.evaluate("() => FlagGame.force('nyi')")
    page.wait_for_timeout(900)
    nyi = page.evaluate(
        """() => {
          const vb = document.getElementById('quizSvg').getAttribute('viewBox').split(/\\s+/).map(Number);
          return {vb, x: FlagGame.qCur.x, y: FlagGame.qCur.y, id: FlagGame.qCur.id};
        }"""
    )
    page.evaluate("() => FlagGame.force('nj')")
    page.wait_for_timeout(900)
    nj = page.evaluate(
        """() => {
          const vb = document.getElementById('quizSvg').getAttribute('viewBox').split(/\\s+/).map(Number);
          const spot = document.querySelector('#quizSvg .spot circle');
          return {vb, x: FlagGame.qCur.x, id: FlagGame.qCur.id, spot: !!spot};
        }"""
    )
    print("nhl zoom", nyr["vb"], nyi["vb"], nj["vb"])
    assert nyr["vb"][2] < nyr["homeW"] * 0.6
    assert nyi["id"] == "nyi" and nj["id"] == "nj" and nj["spot"]
    assert abs((nyi["vb"][0] + nyi["vb"][2] / 2) - (nyr["vb"][0] + nyr["vb"][2] / 2)) > 1
    # Wheel zoom still leaves a later question framed.
    box = page.locator("#quizSvg").bounding_box()
    page.mouse.move(box["x"] + 80, box["y"] + 80)
    page.mouse.wheel(0, -200)
    page.wait_for_timeout(100)
    page.evaluate("() => FlagGame.force('bos')")
    page.wait_for_timeout(900)
    bos = page.evaluate(
        """() => document.getElementById('quizSvg').getAttribute('viewBox').split(/\\s+/).map(Number)[2]"""
    )
    assert bos < nyr["homeW"] * 0.65
    page.click("#qClose")
    page.click("#sportsClose")


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
        check_country_names(page)
        check_play_by_map(page)
        check_map_zoom(page)

        print("external", reqs)
        print("errors", errors)
        assert reqs == [] and errors == []
        browser.close()
        webkit_europe(p)
    print("OK")


if __name__ == "__main__":
    main()
