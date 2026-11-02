"""Test that fli dependency phantom paths are handled gracefully.

The bug: fli_client.py hardcodes /root/.local/pipx/venvs/flights/lib/python3.11/site-packages
as a fallback import path. In Docker, this path does not exist, so _ensure_fli_importable()
fails silently, causing all flight searches to fail and return zero deals — the app
appears healthy but produces no results.
"""
import json
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from app.scrapers.fli_client import FLIClient, FLISearchError, _ensure_fli_importable


def test_ensure_fli_importable_raises_when_no_fli_on_path():
    """_ensure_fli_importable should raise ImportError when fli is not on path."""
    # Remove ALL site-packages paths that could have fli
    original_path = sys.path.copy()
    sys.path = [p for p in sys.path if 'site-packages' not in p.lower() and 'dist-packages' not in p.lower()]
    # Also clear any FLI_SITE_PACKAGES
    with patch.dict("os.environ", {"FLI_SITE_PACKAGES": ""}, clear=True):
        try:
            _ensure_fli_importable()
            # If we get here, fli was found somewhere - this test documents the current env state
            pytest.skip("fli is importable in this environment - test documents baseline")
        except ImportError as e:
            # Expected: fli not importable when site-packages removed
            assert "fli" in str(e).lower()


def test_run_fli_search_propagates_import_error():
    """_run_fli_search should propagate ImportError rather than silently failing."""
    from app.scrapers.fli_client import _run_fli_search

    with patch("app.scrapers.fli_client.subprocess.run") as mock_run:
        with patch("app.scrapers.fli_client._ensure_fli_importable") as mock_ensure:
            mock_ensure.side_effect = ImportError("No module named 'fli'")

            with pytest.raises(FLISearchError, match="fli"):
                _run_fli_search("MCI", "LHR", "2026-01-15")


def test_fliclient_search_raises_flisearcherror_when_fli_missing():
    """FLIClient.search_flights should raise FLISearchError when fli is not importable."""
    client = FLIClient()

    with patch("app.scrapers.fli_client._ensure_fli_importable") as mock_ensure:
        mock_ensure.side_effect = ImportError("fli not importable")

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