"""CLI binary download robustness (cross-platform, esp. Windows): atomic writes,
friendly errors, and corrupt-cache recovery. No network — `urlopen` is stubbed.
"""
import urllib.error

import pytest

import agentspan.cli as cli


class _FakeResp:
    def __init__(self, chunks, total):
        self._chunks = list(chunks)
        self.headers = {"Content-Length": str(total)}

    def read(self, _n):
        return self._chunks.pop(0) if self._chunks else b""


def test_http_404_gives_friendly_error(monkeypatch, tmp_path):
    def boom(url, timeout=0):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    monkeypatch.setattr(cli.urllib.request, "urlopen", boom)
    dest = tmp_path / "bin" / "agentspan.exe"
    with pytest.raises(RuntimeError, match="No Agentspan CLI binary"):
        cli._download_with_progress("http://x/agentspan_windows_amd64.exe", str(dest))
    assert not dest.exists()


def test_network_error_gives_friendly_error(monkeypatch, tmp_path):
    def boom(url, timeout=0):
        raise urllib.error.URLError("proxy refused")

    monkeypatch.setattr(cli.urllib.request, "urlopen", boom)
    with pytest.raises(RuntimeError, match="Could not reach"):
        cli._download_with_progress("http://x/b", str(tmp_path / "bin" / "b"))


def test_successful_download_is_atomic_and_leaves_no_temp(monkeypatch, tmp_path):
    monkeypatch.setattr(
        cli.urllib.request, "urlopen", lambda url, timeout=0: _FakeResp([b"hello"], 5)
    )
    dest = tmp_path / "bin" / "agentspan"
    cli._download_with_progress("http://x/b", str(dest))
    assert dest.read_bytes() == b"hello"
    assert list((tmp_path / "bin").glob(".agentspan-dl-*")) == []  # temp cleaned up


def test_partial_download_is_cleaned_up(monkeypatch, tmp_path):
    class _Broken:
        headers = {"Content-Length": "100"}

        def read(self, _n):
            raise OSError("connection reset")

    monkeypatch.setattr(cli.urllib.request, "urlopen", lambda url, timeout=0: _Broken())
    dest = tmp_path / "bin" / "agentspan"
    with pytest.raises(OSError, match="connection reset"):
        cli._download_with_progress("http://x/b", str(dest))
    assert not dest.exists()  # no corrupt binary left at the final path
    assert list((tmp_path / "bin").glob(".agentspan-dl-*")) == []
