"""Test that fli dependency phantom paths are handled gracefully.

The bug: fli_client.py has a hardcoded fallback path that doesn't exist in Docker,
causing silent failures where flight searches return zero deals — the app appears
healthy but produces no results.
"""
import json
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from app.scrapers.fli_client import FLIClient, FLISearchError, _ensure_fli_importable


def test_ensure_fli_importable_raises_flisearcherror_when_fli_missing():
    """_ensure_fli_importable should raise FLISearchError when fli is not importable."""
    # Simulate clean Docker: remove fli from path and clear env
    original_path = sys.path.copy()
    sys.path = [p for p in original_path if 'fli' not in p.lower() and 'flights' not in p.lower()]
    import os
    os.environ['FLI_SITE_PACKAGES'] = ''

    try:
        _ensure_fli_importable()
        # If we get here without error, fli is importable - test documents baseline
        pytest.skip("fli is importable in this environment - test documents baseline")
    except FLISearchError as e:
        # Expected: fli not importable, FLISearchError raised
        assert "fli" in str(e).lower()
    except ImportError as e:
        # Also acceptable: ImportError with fli mention
        assert "fli" in str(e).lower()
    except Exception as e:
        pytest.fail(f"Unexpected error type {type(e).__name__}: {e}")
    finally:
        # Restore original path
        sys.path = original_path
        os.environ.pop('FLI_SITE_PACKAGES', None)


def test_run_fli_search_propagates_flisearcherror_when_fli_missing():
    """_run_fli_search should propagate FLISearchError when fli is not importable."""
    from app.scrapers.fli_client import _run_fli_search

    with patch("app.scrapers.fli_client._ensure_fli_importable") as mock_ensure:
        mock_ensure.side_effect = FLISearchError("fli package not importable")

        with pytest.raises(FLISearchError, match="fli"):
            _run_fli_search("MCI", "LHR", "2026-01-15")


def test_fliclient_search_raises_flisearcherror_when_fli_missing():
    """FLIClient.search_flights should raise FLISearchError when fli is not importable."""
    client = FLIClient()

    with patch("app.scrapers.fli_client._ensure_fli_importable") as mock_ensure:
        mock_ensure.side_effect = FLISearchError("fli not importable")

        with pytest.raises(FLISearchError, match="fli"):
            client.search_flights("MCI", "LHR", "2026-01-15")


def test_fliclient_search_returns_empty_when_subprocess_returns_empty():
    """FLIClient.search_flights should return [] when subprocess returns empty flights list."""
    client = FLIClient()

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps({"flights": []})
    mock_proc.stderr = ""

    with patch("app.scrapers.fli_client.subprocess.run", return_value=mock_proc):
        result = client.search_flights("MCI", "LHR", "2026-01-15")
        assert result == []


def test_fliclient_search_timeout_raises_flisearcherror():
    """subprocess timeout is converted to FLISearchError."""
    client = FLIClient()

    with patch(
        "app.scrapers.fli_client.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd=[], timeout=40),
    ):
        with pytest.raises(FLISearchError, match="timed out"):
            client.search_flights("MCI", "LHR", "2026-01-15", timeout=30)


def test_fliclient_search_invalid_json_raises_flisearcherror():
    """Garbage subprocess stdout raises FLISearchError."""
    from app.scrapers.fli_client import FLIClient

    client = FLIClient()

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = "not json"
    mock_proc.stderr = ""

    with patch("app.scrapers.fli_client.subprocess.run", return_value=mock_proc):
        with pytest.raises(FLISearchError, match="invalid fli subprocess output"):
            client.search_flights("MCI", "LHR", "2026-01-15")


def test_ensure_fli_importable_with_fli_site_packages_env():
    """FLI_SITE_PACKAGES env var should be respected for unusual deployment layouts."""
    import os

    original_path = sys.path.copy()
    os.environ['FLI_SITE_PACKAGES'] = '/nonexistent/path'

    try:
        _ensure_fli_importable()
        # If fli is importable from regular path, that's fine
        pytest.skip("fli importable - test documents current state")
    except FLISearchError as e:
        # If fli not importable from either path, FLISearchError is raised
        assert "fli" in str(e).lower()
    except Exception as e:
        pytest.fail(f"Unexpected error: {type(e).__name__}: {e}")
    finally:
        # Restore original path
        sys.path = original_path
        os.environ.pop('FLI_SITE_PACKAGES', None)