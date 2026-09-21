from __future__ import annotations

import os
import tempfile
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = os.getenv("EPOCHDEPLOY_BROWSER_BASE", "http://127.0.0.1:8000").rstrip("/")
CDP_URL = os.getenv("EPOCHDEPLOY_CDP_URL")
OUT = Path(os.getenv("EPOCHDEPLOY_BROWSER_ARTIFACT_DIR", "artifacts/browser-e2e"))
OUT.mkdir(parents=True, exist_ok=True)


def run() -> None:
    with sync_playwright() as p:
        if CDP_URL:
            browser = p.chromium.connect_over_cdp(CDP_URL)
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()
        else:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            page = context.new_page()

        console_errors: list[str] = []
        page_errors: list[str] = []
        failed_requests: list[str] = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on("requestfailed", lambda req: failed_requests.append(f"{req.method} {req.url}: {req.failure}"))

        page.set_viewport_size({"width": 1440, "height": 1000})
        page.goto(f"{BASE}/", wait_until="networkidle")
        expect(page.locator('[data-view-panel="release"] h1')).to_contain_text("Approval is not enough")
        expect(page.locator("#metric-state")).to_have_text("READY")
        page.screenshot(path=str(OUT / "01-initial.png"), full_page=True)

        page.locator("#boot").click()
        expect(page.locator("#metric-state")).to_have_text("DRAFT")
        expect(page.locator("#metric-pipeline")).to_have_text("PENDING")
        expect(page.locator("#approve")).to_be_disabled()
        page.locator("#verify-pipeline").click()
        expect(page.locator("#metric-pipeline")).to_have_text("SUCCESS")
        page.locator("#approve").click()
        expect(page.locator("#metric-state")).to_have_text("APPROVED")

        page.locator('.nav[data-view="evidence"]').click()
        expect(page.locator('[data-view-panel="evidence"]')).to_be_visible()
        with tempfile.NamedTemporaryFile("w", suffix="-provenance.txt", delete=False) as handle:
            handle.write("builder=browser-e2e\ncommit=8f375e7b64f6d20a3c1a1b2a6f9a1d9e2f7c1234\n")
            evidence_path = handle.name
        page.locator("#evidence-file").set_input_files(evidence_path)
        page.locator("#upload-evidence").click()
        expect(page.locator("#evidence-result")).to_contain_text("Attached")
        expect(page.locator("#evidence-list .record")).to_have_count(1)
        expect(page.locator("#evidence-list")).to_contain_text("SHA-256")
        page.screenshot(path=str(OUT / "02-evidence-ledger.png"), full_page=True)
        Path(evidence_path).unlink(missing_ok=True)

        page.locator('.nav[data-view="integrations"]').click()
        expect(page.locator("#integration-gitlab")).to_contain_text("configured")
        expect(page.locator("#integration-gitlab")).to_contain_text("Pipeline Hook")
        expect(page.locator("#integration-executor")).to_contain_text("signed-http")
        expect(page.locator("#integration-executor")).to_contain_text("timestamped HMAC-SHA256")
        page.screenshot(path=str(OUT / "03-integrations.png"), full_page=True)

        page.locator('.nav[data-view="release"]').click()
        page.locator("#execute").click()
        expect(page.locator("#metric-state")).to_have_text("EXECUTED")
        expect(page.locator("#metric-match")).to_have_text("MATCH")
        page.locator('.nav[data-view="receipts"]').click()
        expect(page.locator("#receipt-list")).to_contain_text("EXECUTED")
        page.screenshot(path=str(OUT / "04-happy-receipt.png"), full_page=True)

        page.locator('.nav[data-view="release"]').click()
        page.locator("#boot").click()
        expect(page.locator("#metric-pipeline")).to_have_text("PENDING")
        page.locator("#verify-pipeline").click()
        expect(page.locator("#metric-pipeline")).to_have_text("SUCCESS")
        page.locator("#approve").click()
        page.locator("#drift").click()
        expect(page.locator("#metric-match")).to_have_text("DRIFTED")
        page.locator("#execute").click()
        expect(page.locator("#metric-state")).to_have_text("DENIED_STALE")
        expect(page.locator("#metric-match")).to_have_text("BLOCKED")
        diff = page.locator("#diffs .diff")
        expect(diff).to_have_count(1)
        expect(diff.locator("b")).to_have_text("artifact_digest")
        page.screenshot(path=str(OUT / "05-drift-blocked.png"), full_page=True)

        page.locator('.nav[data-view="receipts"]').click()
        expect(page.locator("#receipt-list")).to_contain_text("DENIED_STALE")
        page.screenshot(path=str(OUT / "06-stale-receipt.png"), full_page=True)

        if console_errors or page_errors or failed_requests:
            raise AssertionError(
                f"browser errors: console={console_errors}, page={page_errors}, requests={failed_requests}"
            )
        print("browser e2e: PASS")
        browser.close()


if __name__ == "__main__":
    run()
