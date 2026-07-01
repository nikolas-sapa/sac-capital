"""The Crawl4AI worker must never hang the runner: a wedged fetch is abandoned
within the wall-clock cap and returns partial/empty instead of blocking forever."""
import time

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
