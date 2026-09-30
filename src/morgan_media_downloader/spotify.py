from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Callable


@dataclass
class SpotifyMetadata:
    title: str
    artist: str = ""
    album: str = ""
    duration: float | None = None
    url: str = ""

    @property
    def search_query(self) -> str:
        return spotify_search_query(self.artist, self.title)


def spotify_search_query(artist: str, title: str) -> str:
    terms = " ".join(part.strip() for part in (artist, title) if part.strip())
    return re.sub(r"\s+", " ", terms).strip()


def fetch_public_metadata(url: str, timeout: float = 8,
                          opener: Callable[[urllib.request.Request], object] | None = None) -> list[SpotifyMetadata]:
    endpoint = "https://open.spotify.com/oembed?" + urllib.parse.urlencode({"url": url})
    request = urllib.request.Request(endpoint, headers={"User-Agent": "MorganMediaDownloader/0.1"})
    response_context = opener(request) if opener else urllib.request.urlopen(request, timeout=timeout)
    with response_context as response:
        payload = json.load(response)
    title = str(payload.get("title") or "Spotify item").strip()
    artist = str(payload.get("author_name") or "").strip()
    # Spotify's public oEmbed endpoint reliably describes a track; collection expansion
    # requires authenticated Web API access and is deliberately not bypassed here.
    return [SpotifyMetadata(title=title, artist=artist, url=url)]


def match_confidence(metadata: SpotifyMetadata, candidate: dict) -> float:
    expected = f"{metadata.artist} {metadata.title}".lower()
    actual = f"{candidate.get('uploader', '')} {candidate.get('title', '')}".lower()
    text_score = SequenceMatcher(None, expected, actual).ratio()
    duration_score = 1.0
    if metadata.duration and candidate.get("duration"):
        difference = abs(float(metadata.duration) - float(candidate["duration"]))
        duration_score = max(0.0, 1.0 - difference / max(float(metadata.duration), 1.0))
    return round((text_score * 0.8 + duration_score * 0.2) * 100, 1)
