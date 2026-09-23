from __future__ import annotations

import os
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError, sync_playwright

BACKEND = os.getenv("EPOCHDEPLOY_BROWSER_BASE", "http://127.0.0.1:18001").rstrip("/")
ORIGIN = os.getenv("EPOCHDEPLOY_BROWSER_ORIGIN", "http://epochdeploy.test").rstrip("/")
OUT = Path(os.getenv("EPOCHDEPLOY_BROWSER_OUT", "/tmp/epochdeploy-browser-e2e"))
OUT.mkdir(parents=True, exist_ok=True)


def expect_text(page, selector: str, text: str) -> None:
    page.locator(selector).filter(has_text=text).wait_for(state="visible", timeout=10_000)


def main() -> None:
    console_errors: list[str] = []
    page_errors: list[str] = []
    failed_requests: list[str] = []
    bad_responses: list[str] = []

    with sync_playwright() as p:
        chromium_path = os.getenv("EPOCHDEPLOY_CHROMIUM_PATH")
        if not chromium_path:
            bundled = Path(p.chromium.executable_path)
            chromium_path = str(bundled) if bundled.exists() else "/usr/bin/chromium"
        browser = p.chromium.launch(
            headless=True,
            executable_path=chromium_path,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = browser.new_page(viewport={"width": 1440, "height": 1100}, device_scale_factor=1)
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on("requestfailed", lambda req: failed_requests.append(f"{req.method} {req.url}: {req.failure}"))
        page.on("response", lambda res: bad_responses.append(f"{res.status} {res.url}") if res.status >= 400 else None)

        def proxy(route):
            request = route.request
            suffix = request.url[len(ORIGIN):] if request.url.startswith(ORIGIN) else request.url
            response = route.fetch(url=f"{BACKEND}{suffix}")
            route.fulfill(response=response)

        try:
            page.goto(BACKEND, wait_until="networkidle", timeout=10_000)
        except PlaywrightError as exc:
            if "ERR_BLOCKED_BY_ADMINISTRATOR" not in str(exc):
                raise
            # 일부 CI/샌드박스 환경의 관리형 Chromium은 localhost 최상위 탐색을 차단합니다.
            # 실제 UI 소스와 API는 그대로 사용하고, 문서만 메모리에 로드한 뒤
            # fetch/XHR 트래픽만 실제 FastAPI로 프록시합니다.
            console_errors.clear()
            page_errors.clear()
            failed_requests.clear()
            bad_responses.clear()
            page.close()
            page = browser.new_page(viewport={"width": 1440, "height": 1100}, device_scale_factor=1)
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda err: page_errors.append(str(err)))
            page.on("requestfailed", lambda req: failed_requests.append(f"{req.method} {req.url}: {req.failure}"))
            page.on("response", lambda res: bad_responses.append(f"{res.status} {res.url}") if res.status >= 400 else None)
            page.route(f"{ORIGIN}/**", proxy)
            root = Path(__file__).resolve().parents[1]
            html = (root / "orchestrator/app/static/index.html").read_text()
            css = (root / "orchestrator/app/static/styles.css").read_text()
            js = (root / "orchestrator/app/static/app.js").read_text()
            html = html.replace("<head>", f"<head><base href=\"{ORIGIN}/\">")
            html = html.replace('<link rel="icon" href="data:," />', "")
            html = html.replace('<link rel="stylesheet" href="/static/styles.css" />', f"<style>{css}</style>")
            html = html.replace('<script src="/static/app.js"></script>', f"<script>{js}</script>")
            page.set_content(html, wait_until="networkidle")
        expect_text(page, "h1", "승인만으로는 충분하지 않습니다")
        page.screenshot(path=OUT / "01-release-initial.png", full_page=True)

        # Policy dry-run은 실제 capability 발급을 제어하는 동일한 엔진을 사용합니다.
        page.locator('.nav[data-view="policy"]').click()
        expect_text(page, "h1", "실행 전 Agent 권한을 시뮬레이션합니다")
        policy_buttons = page.locator(".policy-run")
        policy_buttons.nth(0).click()
        expect_text(page, "#policy-scenarios", "ALLOW · allow-agent-nonprod-write")
        policy_buttons.nth(1).click()
        expect_text(page, "#policy-scenarios", "ASK · ask-agent-production-write")
        policy_buttons.nth(2).click()
        expect_text(page, "#policy-scenarios", "DENY · deny-destructive-action")
        page.screenshot(path=OUT / "02-policy-dry-run.png", full_page=True)
        page.locator('.nav[data-view="release"]').click()

        # 정상 실행 경로
        page.locator("#boot").click()
        expect_text(page, "#result", "생성 완료")
        page.locator("#approve").click()
        expect_text(page, "#metric-state", "APPROVED")
        page.locator("#capability").click()
        expect_text(page, "#result", "Capability 발급 완료: ai_agent:release-agent-01")
        page.locator("#execute").click()
        expect_text(page, "#result", "EXECUTED")
        expect_text(page, "#metric-match", "MATCH")
        page.screenshot(path=OUT / "03-release-happy.png", full_page=True)

        # Agent 거버넌스 패스포트에서 WHY/WHO를 승인·실행 기록과 연결합니다.
        page.locator('.nav[data-view="passport"]').click()
        expect_text(page, "h1", "변경이 왜 필요한지 추적합니다")
        expect_text(page, "#passport-summary", "ISSUE-184")
        expect_text(page, "#passport-summary", "release-agent-01")
        expect_text(page, "#passport-summary", "EXECUTED")
        expect_text(page, "#passport-summary", "release-agent-01")
        expect_text(page, "#passport-summary", "deploy")
        expect_text(page, "#passport-timeline", "CHANGE_REQUESTED")
        expect_text(page, "#passport-timeline", "CAPABILITY_ISSUED")
        expect_text(page, "#passport-timeline", "APPROVED")
        expect_text(page, "#passport-timeline", "EXECUTED")
        page.screenshot(path=OUT / "04-change-passport-happy.png", full_page=True)

        # Evidence 화면에서 실제 multipart 업로드 후 ledger를 확인합니다.
        page.locator('.nav[data-view="evidence"]').click()
        expect_text(page, "h1", "Epoch에 evidence를 연결합니다")
        page.locator("#evidence-kind").fill("provenance")
        page.locator("#evidence-file").set_input_files({
            "name": "build-provenance.txt",
            "mimeType": "text/plain",
            "buffer": b"builder=github-actions\ncommit=8f375e7\nattested=true\n",
        })
        page.locator("#evidence-upload").click()
        expect_text(page, "#evidence-result", "저장 완료: build-provenance.txt")
        expect_text(page, "#evidence-list", "build-provenance.txt")
        expect_text(page, "#evidence-list", "sha256")
        page.screenshot(path=OUT / "05-evidence-ledger.png", full_page=True)

        # 다른 화면에서도 저장된 receipt를 조회할 수 있는지 확인합니다.
        page.locator('.nav[data-view="receipts"]').click()
        expect_text(page, "h1", "배포 결정에는 재현 가능한 receipt가 필요합니다")
        expect_text(page, "#receipts-list", "EXECUTED")
        expect_text(page, "#receipts-list", "승인된 deployment identity와 live target이 일치합니다.")
        page.screenshot(path=OUT / "06-receipts-happy.png", full_page=True)

        # Integrations 화면이 production Compose의 실제 gRPC runtime을 그대로 표시하는지 확인합니다.
        page.locator('.nav[data-view="integrations"]').click()
        expect_text(page, "h1", "모든 신뢰 경계를 보이게 만듭니다")
        expect_text(page, "#integration-cards", "GitLab 파이프라인 훅")
        expect_text(page, "#integration-cards", "Go 실행기")
        expect_text(page, "#integration-cards", "데이터베이스")
        expect_text(page, "#integration-cards", "gRPC 런타임")
        expect_text(page, "#integration-cards", "활성")
        expect_text(page, "#integration-cards", "grpc")
        expected_executor = os.getenv("EPOCHDEPLOY_EXPECT_EXECUTOR_IMPLEMENTATION")
        if expected_executor:
            expect_text(page, "#integration-cards", expected_executor)
        page.screenshot(path=OUT / "07-integrations.png", full_page=True)

        # 새 epoch에서 stale approval이 차단되고 diff가 안전하게 렌더링되는지 확인합니다.
        page.locator('.nav[data-view="release"]').click()
        page.locator("#boot").click()
        expect_text(page, "#result", "생성 완료")
        page.locator("#approve").click()
        expect_text(page, "#metric-state", "APPROVED")
        page.locator("#capability").click()
        expect_text(page, "#result", "Capability 발급 완료: ai_agent:release-agent-01")
        page.locator("#drift").click()
        expect_text(page, "#metric-match", "DRIFTED")
        page.locator("#execute").click()
        expect_text(page, "#result", "DENIED_STALE")
        expect_text(page, "#metric-match", "BLOCKED")
        expect_text(page, "#diffs", "artifact_digest")
        page.screenshot(path=OUT / "08-release-drift-blocked.png", full_page=True)

        page.locator('.nav[data-view="receipts"]').click()
        expect_text(page, "#receipts-list", "DENIED_STALE")
        expect_text(page, "#receipts-list", "artifact_digest")
        page.screenshot(path=OUT / "09-receipts-blocked.png", full_page=True)

        page.locator('.nav[data-view="passport"]').click()
        expect_text(page, "#passport-summary", "DENIED_STALE")
        expect_text(page, "#passport-timeline", "DENIED_STALE")
        expect_text(page, "#passport-timeline", "artifact_digest")
        page.screenshot(path=OUT / "10-change-passport-blocked.png", full_page=True)

        browser.close()

    assert not console_errors, f"브라우저 콘솔 오류: {console_errors}"
    assert not page_errors, f"페이지 오류: {page_errors}"
    assert not failed_requests, f"실패한 요청: {failed_requests}"
    assert not bad_responses, f"HTTP 오류 응답: {bad_responses}"
    print("브라우저 E2E: PASS")
    print(f"스크린샷: {OUT}")


if __name__ == "__main__":
    main()
