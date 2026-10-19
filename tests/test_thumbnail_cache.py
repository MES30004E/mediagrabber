import io
from pathlib import Path
import threading
from concurrent.futures import ThreadPoolExecutor
import pytest

from morgan_media_downloader.thumbnail_cache import fetch_thumbnail


class Response:
    def __init__(self, payload: bytes): self.payload = io.BytesIO(payload); self.headers = {"Content-Length": str(len(payload))}
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def read(self, size): return self.payload.read(size)


def test_thumbnail_fetch_uses_safe_headers_cache_and_progress(tmp_path, monkeypatch):
    monkeypatch.setattr("morgan_media_downloader.thumbnail_cache.thumbnail_cache_dir", lambda: tmp_path)
    captured = []
    def open_request(request, timeout):
        captured.append(dict(request.header_items())); return Response(b"image-bytes")
    monkeypatch.setattr("urllib.request.urlopen", open_request)
    progress = []
    url = "https://images.test/thumb.jpg?signature=secret"
    path = fetch_thumbnail(url, {"Referer": "https://page.test", "Cookie": "never", "Authorization": "never"}, progress.append)
    assert Path(path).read_bytes() == b"image-bytes"
    assert progress[-1] == 100 and "Referer" in captured[0]
    assert "Cookie" not in captured[0] and "Authorization" not in captured[0]
    assert fetch_thumbnail(url) == path and len(captured) == 1


def test_thumbnail_fetch_uses_runtime_proxy(tmp_path, monkeypatch):
    monkeypatch.setattr("morgan_media_downloader.thumbnail_cache.thumbnail_cache_dir", lambda: tmp_path)
    captured = {}
    class YDL:
        def __init__(self, options): captured["options"] = options
        def urlopen(self, request): captured["url"] = request.full_url; return Response(b"proxy-image")
        def close(self): captured["closed"] = True
    runtime = type("Runtime", (), {"youtube_dl": YDL})()
    path = fetch_thumbnail("https://images.test/proxy.jpg", proxy="socks5h://127.0.0.1:49172", runtime=runtime)
    assert Path(path).read_bytes() == b"proxy-image"
    assert captured["options"]["proxy"] == "socks5h://127.0.0.1:49172"
    assert captured["closed"] is True


def test_cancelled_thumbnail_stops_before_io_and_between_chunks(tmp_path, monkeypatch):
    monkeypatch.setattr("morgan_media_downloader.thumbnail_cache.thumbnail_cache_dir", lambda: tmp_path)
    cancel = threading.Event(); cancel.set()
    def forbidden(*args, **kwargs): raise AssertionError("Cancelled request reached the network")
    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    with pytest.raises(InterruptedError): fetch_thumbnail("https://images.test/cancel.jpg", cancel_event=cancel)
    cancel.clear()
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: Response(b"large-image-chunk"))
    def progress(value):
        if value and value > 0: cancel.set()
    with pytest.raises(InterruptedError): fetch_thumbnail("https://images.test/cancel.jpg", progress=progress, cancel_event=cancel)
    assert list(tmp_path.iterdir()) == [], "Cancelled content must not become a cached thumbnail or leave partial data"


def test_concurrent_same_url_uses_independent_atomic_partial_files(tmp_path, monkeypatch):
    monkeypatch.setattr("morgan_media_downloader.thumbnail_cache.thumbnail_cache_dir", lambda: tmp_path)
    barrier = threading.Barrier(2)
    class ConcurrentResponse(Response):
        def read(self, size):
            if self.payload.tell() == 0: barrier.wait(timeout=5)
            return super().read(size)
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: ConcurrentResponse(b"same-synthetic-image"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: fetch_thumbnail("https://images.test/shared.jpg"), range(2)))
    assert results[0] == results[1]
    assert Path(results[0]).read_bytes() == b"same-synthetic-image"
    assert list(tmp_path.iterdir()) == [Path(results[0])]
