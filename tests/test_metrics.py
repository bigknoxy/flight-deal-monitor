"""Tests for Prometheus metrics module."""

import pytest
from prometheus_client import CollectorRegistry, REGISTRY

from app.metrics import (
    api_calls_total,
    telegram_alerts_sent_total,
    telegram_alerts_failed_total,
    deals_detected_total,
    job_duration_seconds,
    errors_total,
    metrics_output,
    PROVIDER_AMADEUS,
    PROVIDER_DUFFEL,
    DEAL_TYPE_FLASH_SALE,
    DEAL_TYPE_MISTAKE_FARE,
    COMPONENT_AMADEUS,
    COMPONENT_DUFFEL,
    COMPONENT_TELEGRAM,
    COMPONENT_SCHEDULER,
    COMPONENT_DATABASE,
    COMPONENT_APP,
)


class TestMetricsConstants:
    """Test that metric label constants are defined correctly."""

    def test_provider_constants(self):
        assert PROVIDER_AMADEUS == "amadeus"
        assert PROVIDER_DUFFEL == "duffel"

    def test_deal_type_constants(self):
        assert DEAL_TYPE_FLASH_SALE == "flash_sale"
        assert DEAL_TYPE_MISTAKE_FARE == "mistake_fare"

    def test_component_constants(self):
        assert COMPONENT_AMADEUS == "amadeus"
        assert COMPONENT_DUFFEL == "duffel"
        assert COMPONENT_TELEGRAM == "telegram"
        assert COMPONENT_SCHEDULER == "scheduler"
        assert COMPONENT_DATABASE == "database"
        assert COMPONENT_APP == "app"


class TestApiCallsTotal:
    """Test api_calls_total counter."""

    def test_increment_amadeus(self):
        before = api_calls_total.labels(provider=PROVIDER_AMADEUS)._value.get()
        api_calls_total.labels(provider=PROVIDER_AMADEUS).inc()
        after = api_calls_total.labels(provider=PROVIDER_AMADEUS)._value.get()
        assert after == before + 1

    def test_increment_duffel(self):
        before = api_calls_total.labels(provider=PROVIDER_DUFFEL)._value.get()
        api_calls_total.labels(provider=PROVIDER_DUFFEL).inc()
        after = api_calls_total.labels(provider=PROVIDER_DUFFEL)._value.get()
        assert after == before + 1

    def test_providers_tracked_separately(self):
        amadeus_before = api_calls_total.labels(provider=PROVIDER_AMADEUS)._value.get()
        api_calls_total.labels(provider=PROVIDER_DUFFEL).inc()
        amadeus_after = api_calls_total.labels(provider=PROVIDER_AMADEUS)._value.get()
        assert amadeus_after == amadeus_before


class TestTelegramAlerts:
    """Test telegram alert counters."""

    def test_alerts_sent_increment(self):
        before = telegram_alerts_sent_total._value.get()
        telegram_alerts_sent_total.inc()
        after = telegram_alerts_sent_total._value.get()
        assert after == before + 1

    def test_alerts_failed_increment(self):
        before = telegram_alerts_failed_total._value.get()
        telegram_alerts_failed_total.inc()
        after = telegram_alerts_failed_total._value.get()
        assert after == before + 1


class TestDealsDetected:
    """Test deals_detected_total counter."""

    def test_flash_sale_increment(self):
        before = deals_detected_total.labels(deal_type=DEAL_TYPE_FLASH_SALE)._value.get()
        deals_detected_total.labels(deal_type=DEAL_TYPE_FLASH_SALE).inc()
        after = deals_detected_total.labels(deal_type=DEAL_TYPE_FLASH_SALE)._value.get()
        assert after == before + 1

    def test_mistake_fare_increment(self):
        before = deals_detected_total.labels(deal_type=DEAL_TYPE_MISTAKE_FARE)._value.get()
        deals_detected_total.labels(deal_type=DEAL_TYPE_MISTAKE_FARE).inc()
        after = deals_detected_total.labels(deal_type=DEAL_TYPE_MISTAKE_FARE)._value.get()
        assert after == before + 1

    def test_deal_types_tracked_separately(self):
        flash_before = deals_detected_total.labels(deal_type=DEAL_TYPE_FLASH_SALE)._value.get()
        deals_detected_total.labels(deal_type=DEAL_TYPE_MISTAKE_FARE).inc()
        flash_after = deals_detected_total.labels(deal_type=DEAL_TYPE_FLASH_SALE)._value.get()
        assert flash_after == flash_before


class TestJobDuration:
    """Test job_duration_seconds histogram."""

    def test_observe_duration(self):
        job_id = "regular_sweep"
        # Observe a sample duration
        job_duration_seconds.labels(job_id=job_id).observe(42.5)
        # Just verify no exception is raised and the metric is functional
        # Histogram observations are cumulative; we check it's accessible
        assert job_duration_seconds.labels(job_id=job_id)._sum.get() > 0

    def test_multiple_job_ids(self):
        job_duration_seconds.labels(job_id="regular_sweep").observe(10.0)
        job_duration_seconds.labels(job_id="mistake_sweep").observe(5.0)
        # Both job IDs should have observations
        assert job_duration_seconds.labels(job_id="regular_sweep")._sum.get() > 0
        assert job_duration_seconds.labels(job_id="mistake_sweep")._sum.get() > 0


class TestErrorsTotal:
    """Test errors_total counter."""

    def test_increment_by_component(self):
        for component in [COMPONENT_AMADEUS, COMPONENT_DUFFEL, COMPONENT_TELEGRAM,
                          COMPONENT_SCHEDULER, COMPONENT_DATABASE, COMPONENT_APP]:
            before = errors_total.labels(component=component)._value.get()
            errors_total.labels(component=component).inc()
            after = errors_total.labels(component=component)._value.get()
            assert after == before + 1

    def test_components_tracked_separately(self):
        amadeus_before = errors_total.labels(component=COMPONENT_AMADEUS)._value.get()
        errors_total.labels(component=COMPONENT_DUFFEL).inc()
        amadeus_after = errors_total.labels(component=COMPONENT_AMADEUS)._value.get()
        assert amadeus_after == amadeus_before


class TestMetricsOutput:
    """Test the metrics_output function."""

    def test_returns_tuple(self):
        result = metrics_output()
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_returns_bytes_and_content_type(self):
        data, content_type = metrics_output()
        assert isinstance(data, bytes)
        assert isinstance(content_type, str)
        assert content_type == "text/plain; version=0.0.4; charset=utf-8"

    def test_output_contains_metric_names(self):
        data, _ = metrics_output()
        output = data.decode("utf-8")
        # Verify our metric names appear in the output
        assert "api_calls_total" in output
        assert "telegram_alerts_sent_total" in output
        assert "telegram_alerts_failed_total" in output
        assert "deals_detected_total" in output
        assert "job_duration_seconds" in output
        assert "errors_total" in output

    def test_output_is_prometheus_format(self):
        data, _ = metrics_output()
        output = data.decode("utf-8")
        # Prometheus format includes HELP and TYPE lines
        assert "# HELP" in output
        assert "# TYPE" in output
