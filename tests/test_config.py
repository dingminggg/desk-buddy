from desk_buddy.config import Config, load_config, save_config


def test_config_defaults():
    c = Config()
    assert c.provider == "openai_compatible"
    assert c.roam_enabled is True
    assert c.sound_enabled is True
    assert c.is_configured is False


def test_is_configured_requires_all_three():
    c = Config(base_url="https://x/v1", model="m", api_key="sk-1")
    assert c.is_configured is True
    assert Config(base_url="https://x/v1", model="m").is_configured is False


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    c = Config(base_url="https://x/v1", model="m", api_key="sk-1", roam_enabled=False)
    save_config(c, path)
    loaded = load_config(path)
    assert loaded.base_url == "https://x/v1"
    assert loaded.api_key == "sk-1"
    assert loaded.roam_enabled is False


def test_load_missing_returns_defaults(tmp_path):
    loaded = load_config(tmp_path / "nope.json")
    assert loaded == Config()
