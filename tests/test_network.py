import pytest

from morgan_media_downloader.network import ProxyConfig, detect_tor


def test_tor_uses_remote_dns():
    assert ProxyConfig(mode="Tor").url() == "socks5h://127.0.0.1:9150"


def test_custom_socks_uses_socks5h_and_encodes_credentials():
    value = ProxyConfig("Custom SOCKS Proxy", "proxy.test", 1080, "a@b", "p ss").url()
    assert value == "socks5h://a%40b:p%20ss@proxy.test:1080"


def test_managed_tor_requires_and_propagates_runtime_port():
    with pytest.raises(ValueError, match="runtime SOCKS port"):
        ProxyConfig(mode="Managed Tor").url()
    assert ProxyConfig(mode="Managed Tor", host="127.0.0.1", port=49172).url() == "socks5h://127.0.0.1:49172"


def test_visible_direct_and_system_modes_use_macos_routing_without_proxy():
    assert ProxyConfig("Direct / Normal Network").url() is None
    assert ProxyConfig("System / Proton VPN").url() is None


def test_visible_custom_socks5_mode_uses_remote_dns():
    assert ProxyConfig("Custom SOCKS5 Proxy", "proxy.test", 1080).url() == "socks5h://proxy.test:1080"


def test_custom_proxy_requires_endpoint():
    with pytest.raises(ValueError):
        ProxyConfig(mode="Custom HTTP Proxy").url()


def test_external_tor_detection_prefers_browser_port(monkeypatch):
    monkeypatch.setattr("morgan_media_downloader.network.tcp_reachable", lambda _host, port, _timeout=1.5: port == 9150)
    assert detect_tor() == (True, 9150)


def test_external_tor_detection_falls_back_to_system_port(monkeypatch):
    monkeypatch.setattr("morgan_media_downloader.network.tcp_reachable", lambda _host, port, _timeout=1.5: port == 9050)
    assert detect_tor() == (True, 9050)
