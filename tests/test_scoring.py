"""Browser regressions for Century protection and standard Snooker fouls.

Run a static server from the repository, then:
    python3 -m unittest discover -s tests -p 'test_*.py' -v

Requires Python Playwright and Chromium; no application dependencies are needed.
Set CUESCORE_TEST_URL or CUESCORE_CHROMIUM when using another server or browser.
Every test uses an isolated browser context and never accesses a phone's data.
"""

import os
import unittest

from playwright.sync_api import sync_playwright


C_STATE = "centurySnooker.century.state.v4"
C_SETTINGS = "centurySnooker.century.settings.v4"
S_STATE = "centurySnooker.snooker.state.v4"
RESULTS = "centurySnooker.results.v4"


class ScoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(
            executable_path=os.environ.get("CUESCORE_CHROMIUM", "/usr/bin/chromium"),
            headless=True,
        )

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.context = self.browser.new_context(viewport={"width": 390, "height": 844})
        self.page = self.context.new_page()
        self.page_errors = []
        self.page.on("pageerror", lambda error: self.page_errors.append(str(error)))
        self.page.goto(os.environ.get("CUESCORE_TEST_URL", "http://127.0.0.1:8000/"))
        self.page.locator("#missRed").wait_for()

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.page_errors, [], "Unexpected browser runtime errors")

    def stored(self, key):
        return self.page.evaluate("key => JSON.parse(localStorage.getItem(key))", key)

    def seed_century(self, scores, target=100, protection="shooter", manual=True):
        self.page.evaluate(
            """({scores, target, protection, manual}) => {
                const settings = JSON.parse(localStorage.getItem('centurySnooker.century.settings.v4'));
                settings.playerCount = scores.length;
                settings.target = target;
                settings.protectMode = protection;
                settings.manualProtect = manual;
                const state = JSON.parse(localStorage.getItem('centurySnooker.century.state.v4'));
                state.players = scores.map(score => ({score, freeReds: 0, best: 0}));
                state.active = 0;
                state.visit = 0;
                state.log = [];
                state.winner = null;
                localStorage.setItem('centurySnooker.century.settings.v4', JSON.stringify(settings));
                localStorage.setItem('centurySnooker.century.state.v4', JSON.stringify(state));
                localStorage.setItem('centurySnooker.century.timeline.v4', JSON.stringify({past: [], future: []}));
            }""",
            {"scores": scores, "target": target, "protection": protection, "manual": manual},
        )
        self.page.reload()

    def seed_snooker(self, **changes):
        self.page.evaluate(
            """changes => {
                const state = JSON.parse(localStorage.getItem('centurySnooker.snooker.state.v4'));
                Object.assign(state, {
                    scores: [12, 20], best: [9, 11], active: 0, break: 8,
                    reds: 15, startingReds: 15, ballOn: 'red', clearance: false,
                    respotted: false, log: [], winner: null, endedAt: null, reason: null,
                }, changes);
                localStorage.setItem('centurySnooker.snooker.state.v4', JSON.stringify(state));
                localStorage.setItem('centurySnooker.snooker.timeline.v4', JSON.stringify({past: [], future: []}));
                localStorage.setItem('centurySnooker.mode.v4', JSON.stringify('snooker'));
            }""",
            changes,
        )
        self.page.reload()

    def foul(self, ball):
        self.page.locator("#sFoulToggle").click()
        self.page.locator(f'[data-spot="{ball}"]').click()

    def test_century_65_and_69_are_protected_but_70_is_not(self):
        for score, protected in [(65, True), (69, True), (70, False)]:
            with self.subTest(score=score):
                self.seed_century([score, 15, 25])
                self.assertIn("free passes" if protected else "−10", self.page.locator("#missRed").inner_text())
                self.page.locator("#missRed").click()
                state = self.stored(C_STATE)
                self.assertEqual([p["score"] for p in state["players"]], [score if protected else score - 10, 15, 25])
                self.assertEqual([p["freeReds"] for p in state["players"]], [0, 1, 1] if protected else [0, 0, 0])
                self.assertEqual((state["active"], state["visit"]), (1, 0))

    def test_century_custom_targets_use_exact_seventy_percent_boundary(self):
        for target, score, protected in [(200, 139, True), (200, 140, False), (300, 209, True), (300, 210, False)]:
            with self.subTest(target=target, score=score):
                self.seed_century([score, 0, 0], target=target)
                self.page.locator("#missRed").click()
                players = self.stored(C_STATE)["players"]
                self.assertEqual(players[0]["score"], score if protected else score - 10)
                self.assertEqual([p["freeReds"] for p in players], [0, 1, 1] if protected else [0, 0, 0])

    def test_century_leader_and_manual_protection(self):
        cases = [
            ([5, 69, 0], "leader", True, True),
            ([5, 70, 0], "leader", True, False),
            ([5, 70, 0], "shooter", True, True),
            ([90, 0, 0], "manual", True, True),
            ([0, 0, 0], "manual", False, False),
        ]
        for scores, protection, manual, protected in cases:
            with self.subTest(scores=scores, protection=protection, manual=manual):
                self.seed_century(scores, protection=protection, manual=manual)
                self.page.locator("#missRed").click()
                players = self.stored(C_STATE)["players"]
                self.assertEqual(players[0]["score"], scores[0] if protected else scores[0] - 10)
                self.assertEqual([p["freeReds"] for p in players], [0, 1, 1] if protected else [0, 0, 0])
        self.page.locator("#settingsBtn").click()
        self.assertEqual(self.page.locator('[data-protect="shooter"]').inner_text(), "Shooter <70%")
        self.assertEqual(self.page.locator('[data-protect="leader"]').inner_text(), "Leader <70%")

    def test_century_protected_miss_can_undo_redo_and_reload(self):
        self.seed_century([65, 15, 25])
        before = self.stored(C_STATE)
        self.page.locator("#missRed").click()
        after = self.stored(C_STATE)
        self.assertEqual([p["freeReds"] for p in after["players"]], [0, 1, 1])
        self.page.locator("#undoBtn").click()
        self.assertEqual(self.stored(C_STATE), before)
        self.page.locator("#redoBtn").click()
        self.assertEqual(self.stored(C_STATE), after)
        self.page.reload()
        self.assertEqual(self.stored(C_STATE), after)

    def test_century_foul_remains_shooter_deduction_with_no_free_passes(self):
        self.seed_century([65, 15, 25])
        self.page.locator("#foulToggle").click()
        self.assertEqual(self.page.locator('[data-cpot="10"] .cueBallValue').inner_text(), "−10")
        self.page.locator('[data-cpot="10"]').click()
        state = self.stored(C_STATE)
        self.assertEqual([p["score"] for p in state["players"]], [55, 15, 25])
        self.assertEqual([p["freeReds"] for p in state["players"]], [0, 0, 0])

    def test_snooker_fouls_award_opponent_four_to_seven(self):
        for ball, penalty in [("red", 4), ("yellow", 4), ("green", 4), ("brown", 4), ("blue", 5), ("pink", 6), ("black", 7)]:
            with self.subTest(ball=ball):
                self.seed_snooker()
                self.foul(ball)
                state = self.stored(S_STATE)
                self.assertEqual(state["scores"], [12, 20 + penalty])
                self.assertEqual((state["active"], state["break"], state["reds"], state["ballOn"]), (1, 0, 15, "red"))
                self.assertEqual(state["best"], [9, 11])
                self.assertIn(f"+{penalty}", state["log"][0]["text"])

    def test_snooker_second_shooter_awards_first_player(self):
        self.seed_snooker(active=1)
        self.foul("pink")
        state = self.stored(S_STATE)
        self.assertEqual(state["scores"], [18, 20])
        self.assertEqual(state["active"], 0)

    def test_snooker_concrete_ball_on_sets_minimum_penalty(self):
        for ball_on, selected, penalty in [("black", "red", 7), ("pink", "yellow", 6), ("yellow", "black", 7)]:
            with self.subTest(ball_on=ball_on, selected=selected):
                self.seed_snooker(reds=0, clearance=True, ballOn=ball_on)
                self.foul(selected)
                state = self.stored(S_STATE)
                self.assertEqual(state["scores"], [12, 20 + penalty])
                self.assertEqual((state["reds"], state["ballOn"], state["clearance"]), (0, ball_on, True))

    def test_snooker_last_red_colour_foul_enters_clearance(self):
        self.seed_snooker(reds=0, ballOn="colour")
        self.foul("black")
        state = self.stored(S_STATE)
        self.assertEqual(state["scores"], [12, 27])
        self.assertEqual((state["reds"], state["ballOn"], state["clearance"], state["break"]), (0, "yellow", True, 0))

    def test_snooker_foul_ui_shows_awards_and_normal_pots_stay_unchanged(self):
        self.seed_snooker()
        self.assertEqual(self.page.locator('[data-spot="red"] .cueBallValue').inner_text(), "1")
        self.page.locator("#sFoulToggle").click()
        self.assertEqual(self.page.locator("[data-spot] .cueBallValue").all_text_contents(), ["+4", "+4", "+4", "+4", "+5", "+6", "+7"])
        explanation = self.page.locator(".panelLabel").inner_text().lower()
        for phrase in ["opponent", "4", "7", "highest", "nominated"]:
            self.assertIn(phrase, explanation)
        self.page.locator("#sFoulToggle").click()
        self.page.locator('[data-spot="red"]').click()
        state = self.stored(S_STATE)
        self.assertEqual((state["scores"], state["reds"], state["ballOn"]), ([13, 20], 14, "colour"))

    def test_snooker_award_can_undo_redo_and_reload_without_losing_history(self):
        self.seed_snooker()
        historical = {"id": "completed-game", "mode": "century", "players": ["Past A", "Past B"], "scores": [100, 90], "best": [50, 40], "winner": 0, "endedAt": 123, "playerRefs": [{"kind": "guest", "id": None, "name": "Past A"}, {"kind": "guest", "id": None, "name": "Past B"}]}
        self.page.evaluate("r => localStorage.setItem('centurySnooker.results.v4', JSON.stringify([r]))", historical)
        self.page.reload()
        before = self.stored(S_STATE)
        self.foul("red")
        after = self.stored(S_STATE)
        self.assertEqual(after["scores"], [12, 24])
        self.page.locator("#undoBtn").click()
        self.assertEqual(self.stored(S_STATE), before)
        self.page.locator("#redoBtn").click()
        self.assertEqual(self.stored(S_STATE), after)
        self.page.reload()
        self.assertEqual(self.stored(S_STATE), after)
        self.assertEqual(self.stored(RESULTS), [historical])

    def test_scoring_lock_blocks_century_miss_and_snooker_foul(self):
        self.seed_century([65, 15, 25])
        before = self.stored(C_STATE)
        self.page.locator("#scoreLockBtn").click()
        self.page.locator("#missRed").click()
        self.assertEqual(self.stored(C_STATE), before)
        self.page.locator("#scoreLockBtn").focus()
        self.page.keyboard.down("Enter")
        self.page.wait_for_timeout(800)
        self.page.keyboard.up("Enter")
        self.seed_snooker()
        self.page.locator("#sFoulToggle").click()
        self.page.locator("#scoreLockBtn").click()
        before = self.stored(S_STATE)
        self.page.locator("#sFoulToggle").click()
        self.page.locator('[data-spot="red"]').click()
        self.assertEqual(self.stored(S_STATE), before)
        self.assertTrue(self.page.locator("#undoBtn").is_disabled())

    def test_final_black_foul_finishes_frame_for_opponent(self):
        self.seed_snooker(scores=[50, 50], reds=0, clearance=True, ballOn="black")
        self.foul("red")
        state = self.stored(S_STATE)
        self.assertEqual(state["scores"], [50, 57])
        self.assertEqual((state["winner"], state["active"], state["break"]), (1, 1, 0))
        self.assertEqual(self.stored(RESULTS)[0]["winner"], 1)

    def test_final_black_foul_finishes_frame_even_if_offender_still_leads(self):
        self.seed_snooker(scores=[80, 50], reds=0, clearance=True, ballOn="black")
        self.foul("red")
        state = self.stored(S_STATE)
        self.assertEqual(state["scores"], [80, 57])
        self.assertEqual((state["winner"], state["active"], state["break"]), (0, 1, 0))
        self.assertEqual(self.stored(RESULTS)[0]["winner"], 0)

    def test_final_black_foul_tie_respotted_black_and_subsequent_foul(self):
        self.seed_snooker(scores=[57, 50], reds=0, clearance=True, ballOn="black")
        self.foul("red")
        state = self.stored(S_STATE)
        self.assertEqual(state["scores"], [57, 57])
        self.assertEqual((state["winner"], state["active"], state["respotted"], state["ballOn"]), (None, 1, True, "black"))
        self.assertEqual(self.stored(RESULTS), [])
        self.foul("red")
        state = self.stored(S_STATE)
        self.assertEqual(state["scores"], [64, 57])
        self.assertEqual((state["winner"], state["reason"], state["break"]), (0, "respotted black", 0))
        self.assertEqual(self.stored(RESULTS)[0]["winner"], 0)

    def test_respotted_black_foul_awards_seven_and_ends_frame(self):
        self.seed_snooker(scores=[50, 50], reds=0, clearance=True, respotted=True, ballOn="black")
        self.foul("red")
        state = self.stored(S_STATE)
        self.assertEqual(state["scores"], [50, 57])
        self.assertEqual((state["winner"], state["reason"], state["break"]), (1, "respotted black", 0))
        self.assertEqual(state["best"], [9, 11])
        self.assertEqual(self.stored(RESULTS)[0]["scores"], [50, 57])
        self.page.locator("#undoBtn").click()
        self.assertEqual(self.stored(S_STATE)["winner"], None)
        self.assertEqual(self.stored(RESULTS), [])


if __name__ == "__main__":
    unittest.main()
