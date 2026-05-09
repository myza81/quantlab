from pathlib import Path

import pytest

from backend.core.config import Settings


class TestSettingsDebugParsing:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("true", True),
            ("false", False),
            ("1", True),
            ("0", False),
            ("yes", True),
            ("no", False),
            ("release", False),
            ("DEBUG_MODE", False),
            ("", False),
        ],
    )
    def test_debug_env_values_parse_safely(
        self, monkeypatch: pytest.MonkeyPatch, raw: str, expected: bool
    ) -> None:
        monkeypatch.setenv("DEBUG", raw)
        settings = Settings()
        assert settings.debug is expected

    def test_debug_defaults_false_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DEBUG", raising=False)
        settings = Settings()
        assert settings.debug is False

    def test_storage_base_path_still_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("STORAGE_BASE_PATH", raising=False)
        settings = Settings()
        assert settings.storage_base_path == Path("datasets/normalized")
