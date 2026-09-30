import io
from pathlib import Path

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
