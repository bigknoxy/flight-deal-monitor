"""Tests for structured JSON logging configuration."""
import json
import logging
import os
import sys

import pytest
import structlog

# Ensure project root is on sys.path so `app` is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.logging_config import (
    configure_logging,
    correlation_id,
    request_id,
    new_correlation_id,
    new_request_id,
    clear_context,
    _add_context_vars,
    _rename_event_to_message,
    _rename_logger_to_name,
    CorrelationIDFilter,
)


class TestConfigureLogging:
    """Test configure_logging function."""

    def test_json_format_outputs_valid_json(self, capsys):
        """JSON format should produce parseable JSON lines."""
        configure_logging(log_level="INFO", log_format="json")
        logger = structlog.get_logger("test_json")
        logger.info("test_message", key="value")

        captured = capsys.readouterr()
        json_lines = [
            line for line in captured.out.strip().split("\n")
            if line.startswith("{")
        ]
        assert len(json_lines) >= 1
        parsed = json.loads(json_lines[0])
        assert parsed["message"] == "test_message"
        assert parsed["key"] == "value"
        assert "timestamp" in parsed
        assert parsed["level"] == "info"

    def test_console_format_human_readable(self, capsys):
        """Console format should produce human-readable output."""
        configure_logging(log_level="INFO", log_format="console")
        logger = structlog.get_logger("test_console")
        logger.info("console_msg", extra="data")

        captured = capsys.readouterr()
        assert "console_msg" in captured.out

    def test_log_level_respected(self, capsys):
        """Log level setting should filter messages."""
        configure_logging(log_level="WARNING", log_format="json")
        logger = structlog.get_logger("test_level")
        logger.debug("should_not_appear")
        logger.warning("should_appear")

        captured = capsys.readouterr()
        assert "should_not_appear" not in captured.out
        assert "should_appear" in captured.out


class TestContextVars:
    """Test correlation and request ID context variables."""

    def test_new_correlation_id(self):
        """new_correlation_id should set and return a correlation ID."""
        cid = new_correlation_id()
        assert cid is not None
        assert len(cid) == 16
        assert correlation_id.get() == cid
        clear_context()

    def test_new_request_id(self):
        """new_request_id should set and return a request ID."""
        rid = new_request_id()
        assert rid is not None
        assert len(rid) == 12
        assert request_id.get() == rid
        clear_context()

    def test_clear_context(self):
        """Clear context should reset both IDs."""
        new_correlation_id()
        new_request_id()
        clear_context()
        assert correlation_id.get() is None
        assert request_id.get() is None


class TestProcessors:
    """Test structlog processors."""

    def test_add_context_vars_injects_ids(self):
        """_add_context_vars should add correlation_id and request_id."""
        correlation_id.set("test-corr")
        request_id.set("test-req")
        event_dict = {"event": "test"}
        result = _add_context_vars(None, "info", event_dict)
        assert result["correlation_id"] == "test-corr"
        assert result["request_id"] == "test-req"
        clear_context()

    def test_add_context_vars_skips_none(self):
        """_add_context_vars should skip None context vars."""
        clear_context()
        event_dict = {"event": "test"}
        result = _add_context_vars(None, "info", event_dict)
        assert "correlation_id" not in result
        assert "request_id" not in result

    def test_rename_event_to_message(self):
        """_rename_event_to_message should rename 'event' to 'message'."""
        event_dict = {"event": "hello", "key": "val"}
        result = _rename_event_to_message(None, "info", event_dict)
        assert "message" in result
        assert result["message"] == "hello"
        assert "event" not in result

    def test_rename_event_to_message_no_event(self):
        """_rename_event_to_message should be a no-op when no 'event' key."""
        event_dict = {"message": "already", "key": "val"}
        result = _rename_event_to_message(None, "info", event_dict)
        assert result["message"] == "already"

    def test_rename_logger_to_name(self):
        """_rename_logger_to_name should add 'name' from LogRecord."""
        record = logging.LogRecord(
            "test.logger", logging.INFO, "", 0, "msg", (), None
        )
        event_dict = {"event": "hello", "_record": record}
        result = _rename_logger_to_name(None, "info", event_dict)
        assert result["name"] == "test.logger"


class TestCorrelationIDFilter:
    """Test stdlib CorrelationIDFilter."""

    def test_filter_injects_ids(self):
        """CorrelationIDFilter should inject IDs into LogRecord."""
        correlation_id.set("corr-abc")
        request_id.set("req-xyz")
        record = logging.LogRecord(
            "test", logging.INFO, "", 0, "msg", (), None
        )
        f = CorrelationIDFilter()
        assert f.filter(record) is True
        assert record.correlation_id == "corr-abc"  # type: ignore[attr-defined]
        assert record.request_id == "req-xyz"  # type: ignore[attr-defined]
        clear_context()

    def test_filter_defaults_empty(self):
        """CorrelationIDFilter should use empty strings when no IDs set."""
        clear_context()
        record = logging.LogRecord(
            "test", logging.INFO, "", 0, "msg", (), None
        )
        f = CorrelationIDFilter()
        f.filter(record)
        assert record.correlation_id == ""  # type: ignore[attr-defined]
        assert record.request_id == ""  # type: ignore[attr-defined]


class TestJsonLogFormat:
    """Test that JSON log entries have all required fields."""

    def test_json_entry_has_required_fields(self, capsys):
        """JSON log entry should have timestamp, level, message, and context."""
        configure_logging(log_level="INFO", log_format="json")
        new_request_id()
        new_correlation_id()
        logger = structlog.get_logger("test_fields")
        logger.info("structured_test", route="JFK-LHR", price=299)

        captured = capsys.readouterr()
        json_lines = [
            line for line in captured.out.strip().split("\n")
            if line.startswith("{")
        ]
        assert len(json_lines) >= 1
        parsed = json.loads(json_lines[0])

        # Required fields per task spec
        assert "timestamp" in parsed
        assert "level" in parsed
        assert "message" in parsed
        assert parsed["message"] == "structured_test"
        assert "event" not in parsed  # renamed to message
        assert parsed["request_id"] is not None
        assert parsed["correlation_id"] is not None
        # Context fields
        assert parsed["route"] == "JFK-LHR"
        assert parsed["price"] == 299
        # Ensure no b'...' wrapping artifacts
        for key, val in parsed.items():
            if isinstance(val, str):
                assert not val.startswith("b'"), f"Key '{key}' has bytes wrapping: {val}"

        clear_context()

    def test_json_no_bytes_wrapping(self, capsys):
        """JSON output should not contain b'...' string artifacts."""
        configure_logging(log_level="INFO", log_format="json")
        logger = structlog.get_logger("test_bytes")
        logger.info("no_bytes_check", data="hello")

        captured = capsys.readouterr()
        assert "b'" not in captured.out, f"Found bytes wrapping in output: {captured.out}"
