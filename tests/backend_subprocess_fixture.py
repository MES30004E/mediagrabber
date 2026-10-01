"""Test-only yt-dlp boundary; the real worker/parser/auth chain is unchanged."""
import sys
from morgan_media_downloader import downloader
from morgan_media_downloader.backend.worker import main


class FixtureYDL:
    def __init__(self, params): self.params = params
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def extract_info(self, target, download=False):
        assert target == ':ytwatchlater'
        assert download is False
        print('human output cookie=private-value')
        print('stderr cookie=private-value', file=sys.stderr)
        return {'title': 'Fixture token=private-value', 'webpage_url': 'https://youtube.test/watch?v=fixture',
                'thumbnail': 'https://image.test/?sig=private-value', 'http_headers': {'Cookie': 'private-value'}}


downloader._ydl_class = lambda *_: FixtureYDL
raise SystemExit(main())
