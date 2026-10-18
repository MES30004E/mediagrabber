from pathlib import Path

from morgan_media_downloader.yt_runtime import RuntimeSnapshot


def test_analysis_explicitly_enables_discovered_node_for_ytdlp(monkeypatch):
    from morgan_media_downloader.downloader import analyse_target
    captured = []
    monkeypatch.setattr("morgan_media_downloader.provider.find_runtime", lambda **kw: Path("/synthetic/node"))
    class YDL:
        def __init__(self, options): captured.append(options)
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def extract_info(self, *args, **kwargs): return {"title": "Synthetic"}
    analyse_target("query", runtime=RuntimeSnapshot("synthetic", "Bundled", YDL))
    assert captured[0]["js_runtimes"] == {"node": {"path": "/synthetic/node"}}


def test_deno_version_is_detected_without_treating_its_name_as_a_number(tmp_path, monkeypatch):
    import subprocess
    from morgan_media_downloader.provider import find_runtime
    deno = tmp_path / "deno"; deno.touch()
    monkeypatch.setattr("morgan_media_downloader.provider.shutil.which", lambda name: str(deno) if name == "deno" else None)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr("morgan_media_downloader.provider.subprocess.run", lambda *a, **kw: subprocess.CompletedProcess(a, 0, "deno 2.5.6 (stable, release, aarch64-apple-darwin)\nv8 14\n", ""))
    assert find_runtime() == deno


def test_provider_node20_does_not_hide_valid_player_deno(tmp_path, monkeypatch):
    import subprocess
    from morgan_media_downloader.provider import find_runtime, yt_dlp_javascript_options
    node = tmp_path / "node"; deno = tmp_path / "deno"
    node.touch(); deno.touch()
    monkeypatch.setattr("morgan_media_downloader.provider.shutil.which", lambda name: str(tmp_path / name))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    def version(argv, **kw):
        return subprocess.CompletedProcess(argv, 0, "v20.19.0\n" if argv[0] == str(node) else "deno 2.5.6 (stable)\n", "")
    monkeypatch.setattr("morgan_media_downloader.provider.subprocess.run", version)
    assert find_runtime() == node, "Provider's Node20 support must stay intact"
    assert yt_dlp_javascript_options() == {"js_runtimes": {"deno": {"path": str(deno)}}}
