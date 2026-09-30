import threading
from pathlib import Path

from morgan_media_downloader.downloader import download_job
from morgan_media_downloader.models import DownloadJob, DownloadOptions, JobStatus, MediaItem


FORMATS = [
    {"format_id": "v", "url": "u", "height": 720, "tbr": 100, "ext": "mp4", "vcodec": "avc1", "acodec": "none"},
    {"format_id": "a", "url": "u", "abr": 100, "ext": "m4a", "vcodec": "none", "acodec": "aac"},
]


class FakeYDL:
    attempts = []
    fail_cookie_format = False
    require_login = False
    private_failure = False

    def __init__(self, options):
        self.params = options
        self.__class__.attempts.append(options.copy())
    def __enter__(self): return self
    def __exit__(self, *_args): return None
    def extract_info(self, _url, download=False):
        if self.require_login and "cookiesfrombrowser" not in self.params:
            raise RuntimeError("Sign in required")
        return {"title": "Readable title", "ext": "mp4", "formats": FORMATS}
    def process_ie_result(self, info, download=True):
        if self.private_failure:
            raise RuntimeError("Private video: Requested format is not available")
        if self.fail_cookie_format and "cookiesfrombrowser" in self.params:
            raise RuntimeError("Requested format is not available")
        output = Path(self.params["outtmpl"].replace("%(title)s", info["title"]).replace("%(ext)s", "mp4"))
        output.parent.mkdir(parents=True, exist_ok=True); output.write_bytes(b"media")
        for hook in self.params.get("post_hooks", []): hook(str(output))
        return {**info, "filepath": str(output)}
    def prepare_filename(self, info):
        return self.params["outtmpl"].replace("%(title)s", info["title"]).replace("%(ext)s", "mp4")


def _run(tmp_path, monkeypatch, mode="Auto", profile=""):
    FakeYDL.attempts = []; FakeYDL.fail_cookie_format = False; FakeYDL.require_login = False; FakeYDL.private_failure = False
    monkeypatch.setattr("morgan_media_downloader.downloader._ydl_class", lambda *_: FakeYDL)
    options = DownloadOptions(download_dir=str(tmp_path), authentication_mode=mode,
                              cookies_browser="Chrome", browser_profile=profile,
                              verify_postprocessing=False)
    job = DownloadJob(MediaItem("https://youtube.test/video", "Readable title"), options)
    return job, lambda: download_job(job, None, "provider", "", lambda _job: None, threading.Event())


def test_auto_download_starts_without_cookies_and_uses_readable_title(tmp_path, monkeypatch):
    job, run = _run(tmp_path, monkeypatch)
    result = run()
    assert "cookiesfrombrowser" not in FakeYDL.attempts[0]
    assert result.effective_authentication == "Auto -> None"
    assert Path(result.output_file).name == "Readable title.mp4"
    assert result.final_files == [str((tmp_path / "Readable title.mp4").resolve())]


def test_auto_login_failure_retries_with_real_chrome_profile(tmp_path, monkeypatch):
    job, run = _run(tmp_path, monkeypatch, profile="Profile 2")
    FakeYDL.require_login = True
    result = run()
    assert len(FakeYDL.attempts) == 2
    assert FakeYDL.attempts[1]["cookiesfrombrowser"] == ("chrome", "Profile 2", None, None)
    assert result.effective_authentication == "Auto -> Browser Cookies"


def test_public_cookie_format_failure_retries_once_without_authentication(tmp_path, monkeypatch):
    job, run = _run(tmp_path, monkeypatch, mode="Browser Cookies")
    FakeYDL.fail_cookie_format = True
    result = run()
    assert len(FakeYDL.attempts) == 2
    assert "cookiesfrombrowser" in FakeYDL.attempts[0] and "cookiesfrombrowser" not in FakeYDL.attempts[1]
    assert result.effective_authentication == "Browser Cookies -> None"


def test_quality_fallback_becomes_completed_with_warning(tmp_path, monkeypatch):
    job, run = _run(tmp_path, monkeypatch)
    job.options.quality = "1080p"
    result = run()
    assert result.status == JobStatus.COMPLETED_WARNINGS
    assert "1080p unavailable. Using 720p." in result.warnings


def test_private_authenticated_failure_does_not_retry_without_cookies(tmp_path, monkeypatch):
    job, run = _run(tmp_path, monkeypatch, mode="Browser Cookies")
    FakeYDL.private_failure = True
    result = run()
    assert len(FakeYDL.attempts) == 1
    assert result.status == JobStatus.FAILED
