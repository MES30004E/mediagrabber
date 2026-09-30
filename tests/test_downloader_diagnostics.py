import threading
from pathlib import Path

from morgan_media_downloader.downloader import download_job
from morgan_media_downloader.models import DownloadJob, DownloadOptions, JobStatus, MediaItem


FORMATS = [{"format_id": "direct", "url": "https://cdn.test/media", "protocol": "https",
            "ext": "mp4", "vcodec": "h264", "acodec": "aac", "height": 720}]


class DiagnosticYDL:
    process_attempts = 0
    seen_headers = None
    subtitle_mode = "ok"

    def __init__(self, params): self.params = params
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def extract_info(self, _url, download=False):
        if self.params.get("skip_download"):
            if self.subtitle_mode == "403": raise RuntimeError("HTTP Error 403 while downloading subtitle")
            if self.subtitle_mode == "missing": return {"requested_subtitles": {}}
            sidecar = Path(self.params["outtmpl"].replace("%(title)s", "Example").replace("%(ext)s", "en.vtt"))
            sidecar.parent.mkdir(parents=True, exist_ok=True); sidecar.write_text("WEBVTT\n", encoding="utf-8")
            return {"requested_subtitles": {"en": {"filepath": str(sidecar), "ext": "vtt", "name": "English"}}}
        return {"title": "Example", "extractor_key": "Generic", "extractor": "generic",
                "http_headers": {"Referer": "https://page.test", "Origin": "https://page.test",
                                 "User-Agent": "QA"}, "formats": FORMATS}
    def process_ie_result(self, info, download=True):
        type(self).process_attempts += 1; type(self).seen_headers = info.get("http_headers")
        if type(self).process_attempts == 1 and getattr(type(self), "first_403", False):
            raise RuntimeError("HTTP Error 403: Forbidden")
        output = Path(self.params["outtmpl"].replace("%(title)s", "Example").replace("%(ext)s", "mp4"))
        output.parent.mkdir(parents=True, exist_ok=True); output.write_bytes(b"valid-media")
        for hook in self.params.get("post_hooks", []): hook(str(output))
        return {"title": "Example", "filepath": str(output), "requested_downloads": [{"filepath": str(output)}]}
    def prepare_filename(self, info): return info.get("filepath", "")


def _job(tmp_path, **options):
    options.setdefault("compatibility", "Original / Best Available")
    return DownloadJob(MediaItem("https://page.test/video", "Example", source="Generic"),
                       DownloadOptions(download_dir=str(tmp_path), **options),
                       effective_connection="Direct / Normal Network")


def test_generic_headers_are_preserved_and_format_diagnostics_persist(tmp_path, monkeypatch):
    DiagnosticYDL.process_attempts = 0; DiagnosticYDL.first_403 = False
    monkeypatch.setattr("morgan_media_downloader.downloader._ydl_class", lambda *_: DiagnosticYDL)
    monkeypatch.setattr("morgan_media_downloader.downloader.verify_requested_postprocessing",
                        lambda *_args, **_kwargs: ({"video": True, "audio": True, "subtitle_count": 0,
                                                   "subtitles": [], "thumbnail": False, "metadata": False}, []))
    result = download_job(_job(tmp_path), None, "", "", lambda _job: None, threading.Event())
    assert result.status == JobStatus.COMPLETED
    assert DiagnosticYDL.seen_headers["Referer"] == "https://page.test"
    assert result.metadata_success and result.extractor_key == "Generic"
    assert result.formats_total == result.formats_playable == 1
    assert "url" not in result.playable_format_summary[0]


def test_media_403_performs_one_fresh_extraction_retry(tmp_path, monkeypatch):
    DiagnosticYDL.process_attempts = 0; DiagnosticYDL.first_403 = True
    monkeypatch.setattr("morgan_media_downloader.downloader._ydl_class", lambda *_: DiagnosticYDL)
    monkeypatch.setattr("morgan_media_downloader.downloader.verify_requested_postprocessing",
                        lambda *_args, **_kwargs: ({"video": True, "audio": True, "subtitle_count": 0,
                                                   "subtitles": [], "thumbnail": False, "metadata": False}, []))
    result = download_job(_job(tmp_path), None, "", "", lambda _job: None, threading.Event())
    assert result.status == JobStatus.COMPLETED and result.retry_count == 1
    assert DiagnosticYDL.process_attempts == 2


def test_subtitle_403_is_warning_and_preserves_completed_media(tmp_path, monkeypatch):
    DiagnosticYDL.process_attempts = 0; DiagnosticYDL.first_403 = False; DiagnosticYDL.subtitle_mode = "403"
    monkeypatch.setattr("morgan_media_downloader.downloader._ydl_class", lambda *_: DiagnosticYDL)
    monkeypatch.setattr("morgan_media_downloader.downloader.verify_requested_postprocessing",
                        lambda *_args, **_kwargs: ({"video": True, "audio": True, "subtitle_count": 0,
                                                   "subtitles": [], "thumbnail": False, "metadata": False}, []))
    result = download_job(_job(tmp_path, embed_subtitles=True), None, "", "", lambda _job: None, threading.Event())
    assert result.status == JobStatus.COMPLETED_WARNINGS and Path(result.output_file).read_bytes() == b"valid-media"
    assert any("subtitle download failed: HTTP 403" in warning for warning in result.warnings)
    DiagnosticYDL.subtitle_mode = "ok"


def test_subtitle_mux_success_records_conversion_and_deletes_external_sidecar(tmp_path, monkeypatch):
    DiagnosticYDL.process_attempts = 0; DiagnosticYDL.first_403 = False; DiagnosticYDL.subtitle_mode = "ok"
    monkeypatch.setattr("morgan_media_downloader.downloader._ydl_class", lambda *_: DiagnosticYDL)
    monkeypatch.setattr("morgan_media_downloader.downloader.mux_subtitles_atomically",
                        lambda media, tracks: {"embedded": True, "verified": True, "codec": "mov_text", "count": 1,
                                               "languages": ["en"], "conversion": ["VTT -> mov_text"]})
    monkeypatch.setattr("morgan_media_downloader.downloader.verify_requested_postprocessing",
                        lambda *_args, **_kwargs: ({"video": True, "audio": True, "subtitle_count": 1,
                                                   "subtitles": ["eng • mov_text"], "thumbnail": False, "metadata": False}, []))
    result = download_job(_job(tmp_path, embed_subtitles=True, write_subtitles=False), None, "", "", lambda _job: None, threading.Event())
    assert result.status == JobStatus.COMPLETED and result.subtitle_details["verified"]
    assert result.subtitle_details["conversion"] == ["VTT -> mov_text"]
    assert not any(Path(path).exists() for path in result.subtitle_files)


def test_keep_external_subtitle_preserves_sidecar_after_embedding(tmp_path, monkeypatch):
    DiagnosticYDL.process_attempts = 0; DiagnosticYDL.first_403 = False; DiagnosticYDL.subtitle_mode = "ok"
    monkeypatch.setattr("morgan_media_downloader.downloader._ydl_class", lambda *_: DiagnosticYDL)
    monkeypatch.setattr("morgan_media_downloader.downloader.mux_subtitles_atomically",
                        lambda *_args: {"embedded": True, "verified": True, "codec": "mov_text", "count": 1,
                                       "languages": ["en"], "conversion": ["VTT -> mov_text"]})
    monkeypatch.setattr("morgan_media_downloader.downloader.verify_requested_postprocessing",
                        lambda *_args, **_kwargs: ({"video": True, "audio": True, "subtitle_count": 1,
                                                   "subtitles": ["eng • mov_text"], "thumbnail": False, "metadata": False}, []))
    result = download_job(_job(tmp_path, embed_subtitles=True, write_subtitles=True), None, "", "", lambda _job: None, threading.Event())
    assert any(Path(path).exists() for path in result.subtitle_files)
