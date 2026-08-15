"""Tests for app.core.config.Settings.

Run with: pytest tests/test_config.py -v

Note: unlike test_events.py and test_permissions.py, this module requires
pydantic-settings to be installed (`pip install -r requirements.txt`),
since Settings is a BaseSettings subclass.
"""

from app.core.config import Settings, get_settings


def test_defaults_are_sane_for_local_development():
    settings = Settings(_env_file=None)  # ignore any real .env for this test

    assert settings.environment == "development"
    assert settings.ai_provider == "none"
    assert settings.database_url.startswith("sqlite:///")


def test_get_settings_returns_cached_singleton():
    assert get_settings() is get_settings()


def test_ensure_data_dir_creates_directory(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path / "data")

    result = settings.ensure_data_dir()

    assert result.exists()
    assert result.is_dir()
