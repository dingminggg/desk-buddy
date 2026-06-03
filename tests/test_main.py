from desk_buddy.config import Config
from desk_buddy.main import needs_setup


def test_needs_setup_when_not_configured():
    assert needs_setup(Config()) is True


def test_no_setup_when_configured():
    cfg = Config(base_url="https://x/v1", model="m", api_key="sk-1")
    assert needs_setup(cfg) is False
