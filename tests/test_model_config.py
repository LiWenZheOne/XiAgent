from __future__ import annotations

from pathlib import Path


def test_load_settings_uses_model_config(monkeypatch, tmp_path: Path) -> None:
    from xiagent.infrastructure.config import load_settings
    from xiagent.models.config import DEFAULT_MODEL_CONFIG_PATH, load_model_config

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    config_path = tmp_path / "local_config.toml"
    config_path.write_text(
        """
[deepseek]
api_key = "settings-file-key"
base_url = "https://settings-file.deepseek.test"
model = "settings-file-model"
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "xiagent.infrastructure.config.load_model_config",
        lambda: load_model_config(config_path),
    )

    settings = load_settings()

    assert DEFAULT_MODEL_CONFIG_PATH.name == "local_config.toml"
    assert settings.deepseek_api_key == "settings-file-key"
    assert settings.deepseek_base_url == "https://settings-file.deepseek.test"
    assert settings.deepseek_model == "settings-file-model"


def test_load_model_config_reads_deepseek_local_config(tmp_path: Path, monkeypatch) -> None:
    from xiagent.models.config import load_model_config

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    config_path = tmp_path / "local_config.toml"
    config_path.write_text(
        """
[deepseek]
api_key = "test-key"
base_url = "https://api.deepseek.com"
model = "deepseek-test-model"
""".lstrip(),
        encoding="utf-8",
    )

    config = load_model_config(config_path)

    assert config.deepseek.api_key == "test-key"
    assert config.deepseek.base_url == "https://api.deepseek.com"
    assert config.deepseek.model == "deepseek-test-model"


def test_load_model_config_env_overrides_local_config(tmp_path: Path, monkeypatch) -> None:
    from xiagent.models.config import load_model_config

    config_path = tmp_path / "local_config.toml"
    config_path.write_text(
        """
[deepseek]
api_key = "local-test-key"
base_url = "https://local.deepseek.test"
model = "local-model"
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-test-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://env.deepseek.test")
    monkeypatch.setenv("DEEPSEEK_MODEL", "env-model")

    config = load_model_config(config_path)

    assert config.deepseek.api_key == "env-test-key"
    assert config.deepseek.base_url == "https://env.deepseek.test"
    assert config.deepseek.model == "env-model"


def test_load_model_config_uses_defaults_without_local_file(tmp_path: Path, monkeypatch) -> None:
    from xiagent.models.config import load_model_config

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)

    config = load_model_config(tmp_path / "missing-local_config.toml")

    assert config.deepseek.api_key is None
    assert config.deepseek.base_url == "https://api.deepseek.com"
    assert config.deepseek.model == "deepseek-v4-flash"
