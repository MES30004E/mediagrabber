class Process:
    def poll(self): return None


class Tor:
    available = True
    process = Process()
    state = "Connected"
    port = 19150
    proxy_url = "socks5h://127.0.0.1:19150"


def test_managed_tor_health_distinguishes_process_bootstrap_socks_and_internet(monkeypatch):
    from morgan_media_downloader.network import managed_tor_health
    tor = Tor()
    tor.available = False
    assert managed_tor_health(tor)[0] == "process_unavailable"
    tor.available = True; tor.state = "Bootstrapping 50%"
    assert managed_tor_health(tor)[0] == "bootstrapping"
    tor.state = "Connected"; monkeypatch.setattr("morgan_media_downloader.network.tcp_reachable", lambda *_: False)
    assert managed_tor_health(tor)[0] == "socks_unavailable"
    monkeypatch.setattr("morgan_media_downloader.network.tcp_reachable", lambda *_: True)
    monkeypatch.setattr("morgan_media_downloader.network.test_tor_proxy", lambda *_: ("available", "Tor OK"))
    assert managed_tor_health(tor) == ("internet_working", "Tor OK")


def test_managed_health_propagates_actual_runtime_socks_endpoint(monkeypatch):
    from morgan_media_downloader.network import managed_tor_health
    tor = Tor(); reached = []; proxies = []
    monkeypatch.setattr("morgan_media_downloader.network.tcp_reachable", lambda host, port: reached.append((host, port)) or True)
    monkeypatch.setattr("morgan_media_downloader.network.test_tor_proxy", lambda proxy, runtime=None: proxies.append(proxy) or ("available", "Tor OK"))
    assert managed_tor_health(tor)[0] == "internet_working"
    assert reached == [("127.0.0.1", 19150)]
    assert proxies == ["socks5h://127.0.0.1:19150"]


def test_target_403_only_becomes_tor_rejection_after_internet_is_confirmed():
    from morgan_media_downloader.network import classify_tor_target
    assert classify_tor_target("internet_working", "HTTP 403")[0] == "target_rejected"
    assert classify_tor_target("internet_failed", "HTTP 403")[0] == "internet_failed"
    assert classify_tor_target("internet_working", "Cloudflare Error 1034 Edge IP Restricted")[0] == "cloudflare_edge_restriction"
