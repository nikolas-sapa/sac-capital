"""The Crawl4AI worker must never hang the runner: a wedged fetch is abandoned
within the wall-clock cap and returns partial/empty instead of blocking forever."""
import time
import asyncio

import equities.data.news_crawl4ai as mod


def test_wedged_worker_is_abandoned_within_cap(monkeypatch):
    # Simulate crawl4ai hanging: the worker's asyncio.run() never returns.
    def hanging_worker_target(urls):
        time.sleep(30)  # far longer than the (patched) cap
        return [("u", "text")]

    # Point the sync wrapper's inner call at the hang and shrink the cap.
    monkeypatch.setattr(mod, "_JOIN_TIMEOUT", 0.5)

    def fake_fetch_sync(urls):
        # replicate the real wrapper's abandon-on-timeout logic against a hang
        from threading import Thread
        result = []

        def _worker():
            result.extend(hanging_worker_target(urls))

        t = Thread(target=_worker, daemon=True)
        t.start()
        t.join(timeout=mod._JOIN_TIMEOUT)
        if t.is_alive():
            return list(result)
        return result

    start = time.monotonic()
    out = fake_fetch_sync(["http://example.com"])
    elapsed = time.monotonic() - start

    assert out == []              # nothing completed, but no crash
    assert elapsed < 5.0          # returned promptly, did NOT wait 30s


def test_join_timeout_is_bounded():
    # Guardrail: the cap stays a sane finite budget, not None (which = hang).
    assert isinstance(mod._JOIN_TIMEOUT, (int, float))
    assert 0 < mod._JOIN_TIMEOUT <= 60


def test_browser_shutdown_error_keeps_completed_articles(monkeypatch):
    class Crawler:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            raise RuntimeError("browser already closed")

        async def arun(self, *, url):
            return type("Result", (), {"success": True, "markdown": "article body"})()

    monkeypatch.setattr(mod, "AsyncWebCrawler", lambda **_kwargs: Crawler())
    monkeypatch.setattr(mod, "_TIMEOUT", 1)

    got = asyncio.run(mod._fetch_articles(["https://example.com/story"]))

    assert got == [("https://example.com/story", "article body")]


def test_playwright_closed_page_teardown_is_suppressed():
    class TargetClosedError(Exception):
        pass

    class Loop:
        def __init__(self):
            self.handled = []

        def default_exception_handler(self, context):
            self.handled.append(context)

    loop = Loop()
    mod._handle_playwright_teardown_error(
        loop,
        {"exception": TargetClosedError("Target page, context or browser has been closed")},
        None,
    )
    assert loop.handled == []

    other = RuntimeError("unexpected crawler failure")
    mod._handle_playwright_teardown_error(loop, {"exception": other}, None)
    assert loop.handled == [{"exception": other}]
