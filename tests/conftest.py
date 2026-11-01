import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def offline_logos(tmp_path, monkeypatch):
    """Tests never touch the network: logo fetching returns nothing, cache goes to tmp."""
    import dtdz.brands as b
    monkeypatch.setattr(b, "_fetch", lambda url: None)
    monkeypatch.setattr(b, "_wiki_logo", lambda title: None)
    monkeypatch.setattr(b, "LOGO_CACHE", tmp_path / "logos")
    monkeypatch.setattr(b, "product_photo", lambda title: None)
    monkeypatch.setattr(b, "PHOTO_CACHE", tmp_path / "photos")
    monkeypatch.setattr(b, "commons_photo", lambda q: None)
    import dtdz.photos as ph
    monkeypatch.setattr(ph, "_get", lambda url, timeout=12: None)
    monkeypatch.setattr(ph, "commons_search", lambda q, limit=12: None)
    monkeypatch.setattr(ph, "CACHE", tmp_path / "post-photos")
