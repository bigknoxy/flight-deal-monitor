"""Test configuration module — YAML loading, env validation, edge cases."""

import os
import tempfile

import pytest
import yaml

from app.config import AppConfig, Config, EnvConfig


class TestEnvConfigValidation:
    """Test EnvConfig field validators (pure logic)."""

    def test_valid_amadeus_env(self):
        config = EnvConfig(amadeus_env="test")
        assert config.amadeus_env == "test"

        config = EnvConfig(amadeus_env="production")
        assert config.amadeus_env == "production"

    def test_invalid_amadeus_env_raises(self):
        with pytest.raises(ValueError, match="amadeus_env must be 'test' or 'production'"):
            EnvConfig(amadeus_env="staging")

    def test_valid_log_level_case_insensitive(self):
        config = EnvConfig(log_level="debug")
        assert config.log_level == "DEBUG"

        config = EnvConfig(log_level="INFO")
        assert config.log_level == "INFO"

    def test_invalid_log_level_raises(self):
        with pytest.raises(ValueError, match="log_level must be one of"):
            EnvConfig(log_level="TRACE")

    def test_default_log_level_when_not_overridden(self):
        """When no env file and no explicit value, default is INFO."""
        config = EnvConfig(_env_file=None)
        assert config.log_level == "INFO"

    def test_custom_database_url(self):
        config = EnvConfig(database_url="sqlite:///./custom.db", _env_file=None)
        assert config.database_url == "sqlite:///./custom.db"

    def test_empty_secrets_default_to_empty_string(self):
        """API keys should default to empty string, not None."""
        config = EnvConfig(_env_file=None)
        assert config.amadeus_client_id == ""
        assert config.telegram_bot_token == ""
        assert config.searchapi_api_key == ""


class TestAppConfigFromYAML:

    def test_yaml_not_found_returns_defaults(self):
        """When YAML file doesn't exist, return default AppConfig."""
        config = AppConfig.from_yaml("/tmp/nonexistent_file.yaml")
        assert config.name == "flight-deal-monitor"
        assert config.version == "1.0.0"
        assert "MCI" in config.home_airports
        assert config.regular_sweep_interval == 1800
        assert config.mistake_sweep_interval == 900

    def test_yaml_empty_file_returns_defaults(self):
        """Empty YAML file should not crash."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")
            path = f.name
        try:
            config = AppConfig.from_yaml(path)
            assert config.name == "flight-deal-monitor"
        finally:
            os.unlink(path)

    def test_yaml_with_partial_overrides(self):
        """Partial YAML should merge with defaults."""
        data = {"app": {"name": "my-monitor", "max_results_per_route": 5}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            path = f.name
        try:
            config = AppConfig.from_yaml(path)
            assert config.name == "my-monitor"
            assert config.max_results_per_route == 5
            # Defaults should still apply
            assert config.version == "1.0.0"
            assert "MCI" in config.home_airports
        finally:
            os.unlink(path)

    def test_yaml_with_deal_thresholds(self):
        """YAML can override nested DealThresholds."""
        data = {"app": {"deal_thresholds": {"mistake_fare_percent": 0.80}}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            path = f.name
        try:
            config = AppConfig.from_yaml(path)
            assert config.deal_thresholds.mistake_fare_percent == 0.80
            # Other thresholds remain default
            assert config.deal_thresholds.flash_sale_percent == 0.50
        finally:
            os.unlink(path)

    def test_yaml_with_route_multipliers(self):
        data = {"app": {"route_multipliers": {"domestic": 1.5}}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            path = f.name
        try:
            config = AppConfig.from_yaml(path)
            assert config.route_multipliers.domestic == 1.5
            assert config.route_multipliers.transatlantic == 0.8
        finally:
            os.unlink(path)

    def test_yaml_with_airport_lists(self):
        """YAML can override home_airports and destinations."""
        data = {"app": {"home_airports": ["JFK", "LGA"], "destinations": ["LAX", "SFO"]}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            path = f.name
        try:
            config = AppConfig.from_yaml(path)
            assert config.home_airports == ["JFK", "LGA"]
            assert config.destinations == ["LAX", "SFO"]
        finally:
            os.unlink(path)

    def test_yaml_custom_app_yaml_exists(self):
        """Check config/app.yaml exists and loads correctly."""
        assert os.path.exists("config/app.yaml")
        config = AppConfig.from_yaml("config/app.yaml")
        assert config.name is not None


class TestGlobalConfig:

    def test_config_combines_app_and_env(self):
        """Global Config should have both app and env sections."""
        cfg = Config(app_config_path="/tmp/nonexistent_app.yaml")
        assert cfg.app.name == "flight-deal-monitor"
        # Env is loaded from .env file, but we can check it exists
        assert cfg.env is not None

    def test_default_route_multipliers(self):
        cfg = Config(app_config_path="/tmp/nonexistent_app.yaml")
        multipliers = cfg.app.route_multipliers
        assert multipliers.domestic == 1.0
        assert multipliers.transatlantic == 0.8
        assert multipliers.transpacific == 0.7
        assert multipliers.latin_america == 1.2
        assert multipliers.europe == 0.85

    def test_initial_thresholds_defaults(self):
        cfg = Config(app_config_path="/tmp/nonexistent_app.yaml")
        thresholds = cfg.app.deal_thresholds
        assert thresholds.mistake_fare_percent == 0.70
        assert thresholds.flash_sale_percent == 0.50
        assert thresholds.deep_flash_percent == 0.65


class TestNotifierStatus:
    """Test notifier_status helper."""

    def test_notifier_status_no_notifiers_configured(self):
        """When no notifiers are set, all flags are False and any_configured is False."""
        cfg = Config(app_config_path="/tmp/nonexistent_app.yaml")
        # Reset env to ensure no values from .env file
        cfg.env = EnvConfig(_env_file=None)
        status = cfg.notifier_status()
        assert status["telegram"] is False
        assert status["email"] is False
        assert status["slack"] is False
        assert status["discord"] is False
        assert status["any_configured"] is False

    def test_notifier_status_telegram_configured(self):
        """Telegram is configured when both token and chat_id are set."""
        cfg = Config(app_config_path="/tmp/nonexistent_app.yaml")
        cfg.env = EnvConfig(_env_file=None)
        cfg.env.telegram_bot_token = "test_token"
        cfg.env.telegram_chat_id = "test_chat_id"
        status = cfg.notifier_status()
        assert status["telegram"] is True
        assert status["email"] is False
        assert status["slack"] is False
        assert status["discord"] is False
        assert status["any_configured"] is True

    def test_notifier_status_email_configured(self):
        """Email is configured when smtp_host and smtp_user are set."""
        cfg = Config(app_config_path="/tmp/nonexistent_app.yaml")
        cfg.env = EnvConfig(_env_file=None)
        cfg.env.smtp_host = "smtp.example.com"
        cfg.env.smtp_user = "user@example.com"
        status = cfg.notifier_status()
        assert status["telegram"] is False
        assert status["email"] is True
        assert status["slack"] is False
        assert status["discord"] is False
        assert status["any_configured"] is True

    def test_notifier_status_slack_configured(self):
        """Slack is configured when webhook_url is set."""
        cfg = Config(app_config_path="/tmp/nonexistent_app.yaml")
        cfg.env = EnvConfig(_env_file=None)
        cfg.env.slack_webhook_url = "https://hooks.slack.com/test"
        status = cfg.notifier_status()
        assert status["slack"] is True
        assert status["any_configured"] is True

    def test_notifier_status_discord_configured(self):
        """Discord is configured when webhook_url is set."""
        cfg = Config(app_config_path="/tmp/nonexistent_app.yaml")
        cfg.env = EnvConfig(_env_file=None)
        cfg.env.discord_webhook_url = "https://discord.com/api/webhooks/test"
        status = cfg.notifier_status()
        assert status["discord"] is True
        assert status["any_configured"] is True

    def test_notifier_status_multiple_configured(self):
        """any_configured is True when any notifier is set."""
        cfg = Config(app_config_path="/tmp/nonexistent_app.yaml")
        cfg.env = EnvConfig(_env_file=None)
        cfg.env.telegram_bot_token = "token"
        cfg.env.telegram_chat_id = "chat"
        cfg.env.slack_webhook_url = "https://hooks.slack.com/test"
        status = cfg.notifier_status()
        assert status["telegram"] is True
        assert status["slack"] is True
        assert status["any_configured"] is True
