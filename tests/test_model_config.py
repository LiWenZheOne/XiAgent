from __future__ import annotations

from pathlib import Path


def _clear_model_env(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    monkeypatch.delenv("RUNNINGHUB_API_KEY", raising=False)
    monkeypatch.delenv("RUNNINGHUB_BASE_URL", raising=False)
    monkeypatch.delenv("RUNNINGHUB_IMAGE_MODEL", raising=False)
    monkeypatch.delenv("RUNNINGHUB_IMAGE_ENDPOINT", raising=False)
    monkeypatch.delenv("RUNNINGHUB_TEXT_TO_IMAGE_MODEL", raising=False)
    monkeypatch.delenv("RUNNINGHUB_TEXT_TO_IMAGE_ENDPOINT", raising=False)
    monkeypatch.delenv("RUNNINGHUB_POLL_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv("RUNNINGHUB_POLL_TIMEOUT_SECONDS", raising=False)


def test_load_settings_uses_model_config(monkeypatch, tmp_path: Path) -> None:
    from xiagent.infrastructure.config import load_settings
    from xiagent.models.config import DEFAULT_MODEL_CONFIG_PATH, load_model_config

    _clear_model_env(monkeypatch)
    config_path = tmp_path / "local_config.toml"
    config_path.write_text(
        """
[deepseek]
api_key = "settings-file-key"
base_url = "https://settings-file.deepseek.test"
model = "settings-file-model"

[runninghub_image]
api_key = "settings-runninghub-key"
base_url = "https://settings.runninghub.test"
model = "settings-runninghub-model"
endpoint = "/settings/image-to-image"
poll_interval_seconds = 0.5
poll_timeout_seconds = 9.0

[runninghub_text_to_image]
base_url = "https://settings-text.runninghub.test"
model = "settings-runninghub-text-model"
endpoint = "/settings/text-to-image"
poll_interval_seconds = 0.75
poll_timeout_seconds = 11.0
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
    assert settings.runninghub_image_api_key == "settings-runninghub-key"
    assert settings.runninghub_image_base_url == "https://settings.runninghub.test"
    assert settings.runninghub_image_model == "settings-runninghub-model"
    assert settings.runninghub_image_endpoint == "/settings/image-to-image"
    assert settings.runninghub_image_poll_interval_seconds == 0.5
    assert settings.runninghub_image_poll_timeout_seconds == 9.0
    assert settings.runninghub_text_to_image_api_key == "settings-runninghub-key"
    assert (
        settings.runninghub_text_to_image_base_url
        == "https://settings-text.runninghub.test"
    )
    assert settings.runninghub_text_to_image_model == "settings-runninghub-text-model"
    assert settings.runninghub_text_to_image_endpoint == "/settings/text-to-image"
    assert settings.runninghub_text_to_image_poll_interval_seconds == 0.75
    assert settings.runninghub_text_to_image_poll_timeout_seconds == 11.0


def test_load_model_config_reads_deepseek_local_config(tmp_path: Path, monkeypatch) -> None:
    from xiagent.models.config import load_model_config

    _clear_model_env(monkeypatch)
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


def test_load_model_config_reads_runninghub_image_local_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from xiagent.models.config import load_model_config

    _clear_model_env(monkeypatch)
    config_path = tmp_path / "local_config.toml"
    config_path.write_text(
        """
[runninghub_image]
api_key = "runninghub-local-key"
base_url = "https://local.runninghub.test"
model = "local-runninghub-model"
endpoint = "/local/image-to-image"
poll_interval_seconds = 0.25
poll_timeout_seconds = 12.5
""".lstrip(),
        encoding="utf-8",
    )

    config = load_model_config(config_path)

    assert config.runninghub_image.api_key == "runninghub-local-key"
    assert config.runninghub_image.base_url == "https://local.runninghub.test"
    assert config.runninghub_image.model == "local-runninghub-model"
    assert config.runninghub_image.endpoint == "/local/image-to-image"
    assert config.runninghub_image.poll_interval_seconds == 0.25
    assert config.runninghub_image.poll_timeout_seconds == 12.5


def test_load_model_config_reads_runninghub_text_to_image_local_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from xiagent.models.config import load_model_config

    _clear_model_env(monkeypatch)
    config_path = tmp_path / "local_config.toml"
    config_path.write_text(
        """
[runninghub_image]
api_key = "runninghub-shared-key"

[runninghub_text_to_image]
base_url = "https://local-text.runninghub.test"
model = "local-runninghub-text-model"
endpoint = "/local/text-to-image"
poll_interval_seconds = 0.75
poll_timeout_seconds = 19.5
""".lstrip(),
        encoding="utf-8",
    )

    config = load_model_config(config_path)

    assert config.runninghub_text_to_image.api_key == "runninghub-shared-key"
    assert config.runninghub_text_to_image.base_url == "https://local-text.runninghub.test"
    assert config.runninghub_text_to_image.model == "local-runninghub-text-model"
    assert config.runninghub_text_to_image.endpoint == "/local/text-to-image"
    assert config.runninghub_text_to_image.poll_interval_seconds == 0.75
    assert config.runninghub_text_to_image.poll_timeout_seconds == 19.5


def test_load_model_config_env_overrides_local_config(tmp_path: Path, monkeypatch) -> None:
    from xiagent.models.config import load_model_config

    _clear_model_env(monkeypatch)
    config_path = tmp_path / "local_config.toml"
    config_path.write_text(
        """
[deepseek]
api_key = "local-test-key"
base_url = "https://local.deepseek.test"
model = "local-model"

[runninghub_image]
api_key = "local-runninghub-key"
base_url = "https://local.runninghub.test"
model = "local-runninghub-model"
endpoint = "/local/image-to-image"
poll_interval_seconds = 0.25
poll_timeout_seconds = 12.5

[runninghub_text_to_image]
model = "local-runninghub-text-model"
endpoint = "/local/text-to-image"
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-test-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://env.deepseek.test")
    monkeypatch.setenv("DEEPSEEK_MODEL", "env-model")
    monkeypatch.setenv("RUNNINGHUB_API_KEY", "env-runninghub-key")
    monkeypatch.setenv("RUNNINGHUB_BASE_URL", "https://env.runninghub.test")
    monkeypatch.setenv("RUNNINGHUB_IMAGE_MODEL", "env-runninghub-model")
    monkeypatch.setenv("RUNNINGHUB_IMAGE_ENDPOINT", "/env/image-to-image")
    monkeypatch.setenv("RUNNINGHUB_TEXT_TO_IMAGE_MODEL", "env-runninghub-text-model")
    monkeypatch.setenv("RUNNINGHUB_TEXT_TO_IMAGE_ENDPOINT", "/env/text-to-image")
    monkeypatch.setenv("RUNNINGHUB_POLL_INTERVAL_SECONDS", "1.5")
    monkeypatch.setenv("RUNNINGHUB_POLL_TIMEOUT_SECONDS", "22.5")

    config = load_model_config(config_path)

    assert config.deepseek.api_key == "env-test-key"
    assert config.deepseek.base_url == "https://env.deepseek.test"
    assert config.deepseek.model == "env-model"
    assert config.runninghub_image.api_key == "env-runninghub-key"
    assert config.runninghub_image.base_url == "https://env.runninghub.test"
    assert config.runninghub_image.model == "env-runninghub-model"
    assert config.runninghub_image.endpoint == "/env/image-to-image"
    assert config.runninghub_image.poll_interval_seconds == 1.5
    assert config.runninghub_image.poll_timeout_seconds == 22.5
    assert config.runninghub_text_to_image.api_key == "env-runninghub-key"
    assert config.runninghub_text_to_image.base_url == "https://env.runninghub.test"
    assert config.runninghub_text_to_image.model == "env-runninghub-text-model"
    assert config.runninghub_text_to_image.endpoint == "/env/text-to-image"
    assert config.runninghub_text_to_image.poll_interval_seconds == 1.5
    assert config.runninghub_text_to_image.poll_timeout_seconds == 22.5


def test_load_model_config_uses_defaults_without_local_file(tmp_path: Path, monkeypatch) -> None:
    from xiagent.models.config import load_model_config

    _clear_model_env(monkeypatch)

    config = load_model_config(tmp_path / "missing-local_config.toml")

    assert config.deepseek.api_key is None
    assert config.deepseek.base_url == "https://api.deepseek.com"
    assert config.deepseek.model == "deepseek-v4-flash"
    assert config.runninghub_image.api_key is None
    assert config.runninghub_image.base_url == "https://www.runninghub.ai"
    assert (
        config.runninghub_image.model
        == "nano-banana-pro/edit"
    )
    assert config.runninghub_image.endpoint == "/rhart-image-n-pro/edit"
    assert config.runninghub_image.poll_interval_seconds == 2.0
    assert config.runninghub_image.poll_timeout_seconds == 180.0
    assert config.runninghub_text_to_image.api_key is None
    assert config.runninghub_text_to_image.base_url == "https://www.runninghub.ai"
    assert (
        config.runninghub_text_to_image.model
        == "nano-banana-pro/text-to-image-channel-low-price"
    )
    assert config.runninghub_text_to_image.endpoint == "/rhart-image-n-pro/text-to-image"
    assert config.runninghub_text_to_image.poll_interval_seconds == 2.0
    assert config.runninghub_text_to_image.poll_timeout_seconds == 180.0
