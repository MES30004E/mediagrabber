import threading
from pathlib import Path

from morgan_media_downloader.downloader import download_job
from morgan_media_downloader.models import DownloadJob, DownloadOptions, JobStatus, MediaItem


class RetryYDL:
    analyses = 0
    reject_count = 3
    def __init__(self, params): self.params = params
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def extract_info(self, _url, download=False):
        type(self).analyses += 1
        if type(self).analyses <= type(self).reject_count: raise RuntimeError("HTTP Error 403: Forbidden")
        return {"title": "Fixture", "extractor_key": "Generic", "formats": [
            {"format_id": "direct", "url": "https://fresh.test/media", "ext": "mp4", "vcodec": "h264", "acodec": "aac"}]}
    def process_ie_result(self, info, download=True):
        output = Path(self.params["outtmpl"].replace("%(title)s", "Fixture").replace("%(ext)s", "mp4")); output.write_bytes(b"fixture")
        for hook in self.params.get("post_hooks", []): hook(str(output))
        return {"filepath": str(output), "requested_downloads": [{"filepath": str(output)}]}
    def prepare_filename(self, info): return info.get("filepath", "")


def _run(tmp_path, monkeypatch, reject_count):
    RetryYDL.analyses = 0; RetryYDL.reject_count = reject_count
    monkeypatch.setattr("morgan_media_downloader.downloader._ydl_class", lambda *_: RetryYDL)
    monkeypatch.setattr("morgan_media_downloader.downloader.verify_requested_postprocessing",
                        lambda *_a, **_k: ({"video": True, "audio": True, "subtitle_count": 0, "subtitles": [], "thumbnail": False, "metadata": False}, []))
    rotations = []
    job = DownloadJob(MediaItem("https://original.test/page", "Fixture", source="Generic"),
                      DownloadOptions(download_dir=str(tmp_path), compatibility="Original / Best Available"),
                      effective_connection="Managed Tor")
    result = download_job(job, "socks5h://127.0.0.1:9150", "", "", lambda _j: None,
                          threading.Event(), tor_circuit=lambda _job, attempt: rotations.append(attempt) or
                          {"previous_exit_ip": "1.1.1.1", "current_exit_ip": f"2.2.2.{attempt}", "changed": True})
    return result, rotations


def test_tor_denial_rotates_at_most_three_times_and_freshly_extracts(tmp_path, monkeypatch):
    result, rotations = _run(tmp_path, monkeypatch, 3)
    assert result.status == JobStatus.COMPLETED and rotations == [1, 2, 3]
    assert RetryYDL.analyses == 4 and result.tor_circuit_retry == 3


def test_persistent_tor_denial_stops_after_three(tmp_path, monkeypatch):
    result, rotations = _run(tmp_path, monkeypatch, 99)
    assert result.status == JobStatus.FAILED and rotations == [1, 2, 3]
    assert RetryYDL.analyses == 4 and "continues to reject" in result.error
