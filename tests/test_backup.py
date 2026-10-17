"""Browser integration tests. Run against python -m http.server 8000.

Requires the existing Python Playwright package and system Chromium; no app
dependencies or network services are used.
"""
import json
import os
import re
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright


BASE_URL = os.environ.get("CUESCORE_TEST_URL", "http://127.0.0.1:8000")
PREFIX = "centurySnooker."
LEGACY = {
    "century.settings.v1": PREFIX + "century.settings.v4",
    "century.state.v1": PREFIX + "century.state.v4",
    "snooker.settings.v1": PREFIX + "snooker.settings.v4",
    "snooker.state.v1": PREFIX + "snooker.state.v4",
    "app.mode.v1": PREFIX + "mode.v4",
    "scorekeeper.results.v1": PREFIX + "results.v4",
}


class BackupBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(
            executable_path="/usr/bin/chromium", args=["--no-sandbox"]
        )
        # Generate realistic game, undo/redo, profile and receipt records with
        # the production app, so roundtrips exercise its actual stored schema.
        context = cls.browser.new_context(viewport={"width": 390, "height": 844})
        page = context.new_page()
        page.goto(BASE_URL + "/")
        for _ in range(10):
            page.locator('[data-cpot="10"]').click()
        page.locator("#winnerNew").click()
        page.locator('[data-cpot="10"]').click()
        page.locator('[data-cpot="7"]').click()
        page.locator("#undoBtn").click()
        page.locator("#settingsBtn").click()
        page.locator("#addRegular").click()
        page.locator("#x").click()
        page.locator('[data-mode="snooker"]').click()
        page.locator('[data-spot="red"]').click()
        page.locator('[data-spot="black"]').click()
        page.locator("#undoBtn").click()
        page.locator("#clubTimerBtn").click()
        page.locator("#timerStart").click()
        page.locator("#timerEnd").click()
        page.locator("#yes").click()
        page.locator("#timerStart").click()
        page.locator("#timerPause").click()
        page.locator("#x").click()
        page.locator("#scoreLockBtn").click()
        page.locator("#tableBtn").click()
        cls.source = page.evaluate("() => Object.fromEntries(Object.entries(localStorage))")
        for legacy, current in LEGACY.items():
            cls.source[legacy] = " \n" + cls.source[current] + "\n "
        context.close()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.context = self.browser.new_context(
            viewport={"width": 390, "height": 844}, accept_downloads=True
        )
        self.page = self.context.new_page()
        response = self.page.goto(BASE_URL + "/backup.html")
        self.assertEqual(response.status, 200, "The phone backup page must exist")
        self.page.wait_for_selector("#exportBackup")

    def tearDown(self):
        self.context.close()

    def seed(self, data):
        self.page.evaluate("data => {localStorage.clear(); for (const [k,v] of Object.entries(data)) localStorage.setItem(k,v)}", data)

    def stored(self):
        return self.page.evaluate("() => Object.fromEntries(Object.entries(localStorage))")

    def archive(self, storage=None, **changes):
        value = {
            "format": "cuescore-phone-backup",
            "version": 1,
            "exportedAt": "2026-10-17T12:00:00.000Z",
            "sourceOrigin": "https://original.example",
            "storage": self.source.copy() if storage is None else storage,
        }
        value.update(changes)
        return value

    def upload(self, value):
        content = value if isinstance(value, str) else json.dumps(value)
        self.page.locator("#backupFile").set_input_files({
            "name": "phone-backup.json", "mimeType": "application/json",
            "buffer": content.encode("utf-8"),
        })

    def downloaded_json(self, action):
        with self.page.expect_download() as download_info:
            action()
        download = download_info.value
        self.assertRegex(download.suggested_filename, r"^cuescore-.*\.json$")
        return json.loads(Path(download.path()).read_text())

    def test_export_download_preserves_every_actual_and_legacy_raw_value(self):
        self.seed({**self.source, "unrelated.account": "keep"})
        archive = self.downloaded_json(lambda: self.page.locator("#exportBackup").click())
        self.assertEqual(archive["format"], "cuescore-phone-backup")
        self.assertEqual(archive["version"], 1)
        self.assertEqual(archive["storage"], self.source)
        self.assertEqual(archive["sourceOrigin"], BASE_URL)
        self.assertEqual(self.stored(), {**self.source, "unrelated.account": "keep"})
        # Check fixture/key coverage against the live application, including
        # keys intentionally declared outside its main K map.
        html = self.page.request.get(BASE_URL + "/").text()
        current_keys = set(re.findall(r'"(centurySnooker\.[^"\s]+)"', html))
        self.assertEqual(set(self.source), current_keys | set(LEGACY))

    def test_settings_in_both_modes_links_to_backup_page(self):
        self.page.goto(BASE_URL + "/")
        for mode in ("century", "snooker"):
            self.page.locator('[data-mode="' + mode + '"]').click()
            self.page.locator("#settingsBtn").click()
            link = self.page.get_by_role("link", name="Backup & transfer")
            self.assertEqual(link.get_attribute("href"), "backup.html")
            self.page.locator("#x").click()

    def test_preview_requires_explicit_restore_and_downloads_safety_backup(self):
        before = {PREFIX + "mode.v4": '"century"', "unrelated.account": "keep"}
        self.seed(before)
        self.upload(self.archive())
        self.page.locator("#restorePreview").wait_for(state="visible")
        summary = self.page.locator("#previewSummary").inner_text()
        for expected in ("1 saved result", "1 profile", "1 timer receipt", "snooker", "10", "1"):
            self.assertIn(expected, summary.lower())
        self.assertEqual(self.stored(), before)
        self.assertFalse(self.page.locator("#restoreBackup").is_enabled())
        self.page.locator("#confirmReplace").check()
        safety = self.downloaded_json(lambda: self.page.locator("#restoreBackup").click())
        self.assertEqual(safety["storage"], {PREFIX + "mode.v4": '"century"'})
        self.assertEqual(self.stored(), {**self.source, "unrelated.account": "keep"})
        self.assertIn("Restore complete", self.page.locator("#status").inner_text())

    def test_restore_removes_absent_owned_keys_and_keeps_other_sites_data(self):
        self.seed({**self.source, "unrelated.account": "keep", "centurySnooker.unknown.v8": "keep"})
        replacement = {PREFIX + "mode.v4": '  "century"\n'}
        self.upload(self.archive(storage=replacement))
        self.page.locator("#restorePreview").wait_for(state="visible")
        self.page.locator("#confirmReplace").check()
        self.downloaded_json(lambda: self.page.locator("#restoreBackup").click())
        self.assertEqual(self.stored(), {**replacement, "unrelated.account": "keep", "centurySnooker.unknown.v8": "keep"})

    def test_invalid_archives_and_values_never_mutate_storage(self):
        before = {**self.source, "unrelated.account": "keep"}
        self.seed(before)
        invalid = [
            "not json", self.archive(version=2), self.archive(format="unknown"),
            self.archive(storage={"unrelated.account": '"overwrite"'}),
            self.archive(storage={PREFIX + "unknown.v8": '"overwrite"'}),
            self.archive(storage={PREFIX + "mode.v4": '"invalid"'}),
            self.archive(storage={PREFIX + "results.v4": "[null]"}),
            self.archive(storage={PREFIX + "profiles.v1": "[{\"id\":3,\"name\":null}]"}),
            self.archive(storage={PREFIX + "century.state.v4": '{"players":"bad"}'}),
            self.archive(storage={PREFIX + "snooker.timeline.v4": '{"past":[null],"future":[]}'}),
            self.archive(storage={PREFIX + "clubTimer.v1": '{"history":"bad"}'}),
            self.archive(storage={PREFIX + "scoreLock.v1": "null"}),
            self.archive(storage={PREFIX + "mode.v4": "not json"}),
            self.archive(storage={PREFIX + "mode.v4": 1}),
            " " * (20 * 1024 * 1024 + 1),
        ]
        for value in invalid:
            with self.subTest(value=str(value)[:120]):
                self.upload(value)
                self.page.wait_for_function("document.querySelector('#status').dataset.kind === 'error'")
                self.assertTrue(self.page.locator("#restorePreview").is_hidden())
                self.assertEqual(self.stored(), before)

    def test_quota_failure_rolls_back_partial_writes_without_reloading(self):
        before = {**self.source, "unrelated.account": "keep"}
        self.seed(before)
        replacement = {PREFIX + "mode.v4": '"century"', PREFIX + "scoreLock.v1": "false"}
        self.upload(self.archive(storage=replacement))
        self.page.locator("#restorePreview").wait_for(state="visible")
        self.page.locator("#confirmReplace").check()
        # One storage write succeeds before a realistic quota exception. Only
        # this browser failure is simulated; the transaction uses real storage.
        self.page.evaluate("""() => {
            window.testDocument = 'still-open';
            const set = Storage.prototype.setItem;
            let writes = 0;
            Storage.prototype.setItem = function (k, v) {
                if (++writes === 2) throw new DOMException('Test quota exceeded', 'QuotaExceededError');
                return set.call(this, k, v);
            };
        }""")
        self.downloaded_json(lambda: self.page.locator("#restoreBackup").click())
        self.assertIn("rolled back", self.page.locator("#status").inner_text().lower())
        self.assertIn("quota", self.page.locator("#status").inner_text().lower())
        self.assertEqual(self.stored(), before)
        self.assertEqual(self.page.evaluate("window.testDocument"), "still-open")

    def test_incomplete_timer_receipt_is_rejected_without_silently_losing_history(self):
        before = {**self.source, "unrelated.account": "keep"}
        self.seed(before)
        bad_timer = json.loads(self.source[PREFIX + "clubTimer.v1"])
        bad_timer["history"].append({})
        self.upload(self.archive(storage={PREFIX + "clubTimer.v1": json.dumps(bad_timer)}))
        self.page.wait_for_timeout(100)
        self.assertEqual(self.page.locator("#status").get_attribute("data-kind"), "error")
        self.assertTrue(self.page.locator("#restorePreview").is_hidden())
        self.assertEqual(self.stored(), before)

    def test_timeline_snapshots_require_fields_used_directly_by_undo(self):
        self.seed(self.source)
        for game, removed in (("century", "visit"), ("century", "winner"),
                              ("snooker", "best"), ("snooker", "winner")):
            with self.subTest(game=game, removed=removed):
                timeline_key = PREFIX + game + ".timeline.v4"
                timeline = json.loads(self.source[timeline_key])
                del timeline["past"][0][removed]
                self.upload(self.archive(storage={timeline_key: json.dumps(timeline)}))
                self.page.wait_for_timeout(75)
                self.assertEqual(self.page.locator("#status").get_attribute("data-kind"), "error")
                self.assertTrue(self.page.locator("#restorePreview").is_hidden())
                self.assertEqual(self.stored(), self.source)

    def test_restore_fits_when_large_owned_data_moves_to_another_key(self):
        old = {PREFIX + "profiles.v1": json.dumps([
            {"id": "old", "name": "x" * 100000}
        ])}
        self.seed(old)
        replacement = {
            PREFIX + "results.v4": json.dumps([{
                "id": "history", "players": ["A", "B"], "scores": [100, 2],
                "reason": "y" * 100000,
            }]),
            PREFIX + "profiles.v1": "[]",
        }
        self.upload(self.archive(storage=replacement))
        self.page.locator("#restorePreview").wait_for(state="visible")
        self.page.locator("#confirmReplace").check()
        self.page.evaluate("""() => {
            const set = Storage.prototype.setItem;
            Storage.prototype.setItem = function(k, v) {
                const next = {...Object.fromEntries(Object.entries(this)), [k]: String(v)};
                const size = Object.entries(next).reduce((n,[key,value]) => n+key.length+value.length,0);
                if (size > 150000) throw new DOMException('Storage is full', 'QuotaExceededError');
                return set.call(this, k, v);
            };
        }""")
        self.downloaded_json(lambda: self.page.locator("#restoreBackup").click())
        self.assertIn("Restore complete", self.page.locator("#status").inner_text())
        self.assertEqual(self.stored(), replacement)

    def test_decimal_custom_target_saved_by_app_can_be_imported(self):
        self.page.goto(BASE_URL + "/")
        self.page.locator("#settingsBtn").click()
        self.page.locator("#ctarget").fill("100.5")
        self.page.locator("#ctarget").press("Tab")
        self.assertEqual(self.page.evaluate("JSON.parse(localStorage.getItem('centurySnooker.century.settings.v4')).target"), 100.5)
        self.page.goto(BASE_URL + "/backup.html")
        archive = self.downloaded_json(lambda: self.page.locator("#exportBackup").click())
        self.upload(archive)
        self.page.wait_for_timeout(100)
        self.assertEqual(self.page.locator("#status").get_attribute("data-kind"), "success")
        self.assertTrue(self.page.locator("#restorePreview").is_visible())

    def test_preview_is_text_only_and_stale_destination_is_not_overwritten(self):
        self.seed({PREFIX + "mode.v4": '"century"'})
        archive = self.archive(sourceOrigin='<img src=x onerror="window.injected=true">')
        self.upload(archive)
        self.page.locator("#restorePreview").wait_for(state="visible")
        self.assertFalse(self.page.evaluate("Boolean(window.injected)"))
        self.assertEqual(self.page.locator("#previewSummary img").count(), 0)
        self.page.evaluate("localStorage.setItem('centurySnooker.mode.v4', '\"snooker\"')")
        before = self.stored()
        self.page.locator("#confirmReplace").check()
        self.page.locator("#restoreBackup").click()
        self.assertIn("changed since", self.page.locator("#status").inner_text())
        self.assertEqual(self.stored(), before)


if __name__ == "__main__":
    unittest.main()
