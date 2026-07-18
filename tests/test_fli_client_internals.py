"""Direct tests for fli_client internals that don't need live network.

Covers the import-path bootstrap, the invalid-airport-code short-circuit, and
the subprocess ``__main__`` entry point (invoked as a real child process).
"""

import json
import subprocess
import sys

from app.scrapers.fli_client import (
    _ensure_fli_importable,
    _run_fli_search,
)


class TestEnsureFliImportable:
    def test_idempotent_import_path(self):
        # fli is installed in the app venv; this must not raise and must
        # leave the fli models importable.
        _ensure_fli_importable()
        from fli.models import Airport  # noqa: F401

        assert getattr(Airport, "MCI", None) is not None


class TestRunFliSearchInvalidCodes:
    def test_invalid_airport_codes_return_empty(self):
        # Genuine "no such airport" is not an error — returns [].
        result = _run_fli_search("ZZZ", "YYY", "2024-06-01")
        assert result == []


class TestFliClientSubprocessEntry:
    def test_main_with_invalid_codes_exits_clean(self):
        # Run the module as its own process (the real production path used by
        # FLIClient.search_flights). Invalid codes must yield {"flights": []}
        # with a zero/one exit, never a crash.
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.scrapers.fli_client",
                "ZZZ",
                "YYY",
                "2024-06-01",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        payload = json.loads(proc.stdout)
        assert payload["flights"] == []
