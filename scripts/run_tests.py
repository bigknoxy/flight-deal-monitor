#!/usr/bin/env python3
"""Idempotent test runner — handles DB setup, PYTHONPATH, and test selection.

Usage:
    # Full suite (all tests)
    python3 scripts/run_tests.sh

    # Specific test files
    python3 scripts/run_tests.sh tests/test_scheduler_jobs.py tests/test_bot.py

    # Single test
    python3 scripts/run_tests.sh tests/test_bot.py::test_cmd_start

    # With coverage
    python3 scripts/run_tests.sh --cov=app

    # With verbose output
    python3 scripts/run_tests.sh -v

This script is idempotent: running it multiple times with the same arguments
produces the same result. It handles:
- DATABASE_URL setup (uses /dev/shm/ to avoid polluting the real DB)
- PYTHONPATH setup
- Clean DB between runs (deletes the temp DB file before each run)
"""
"""Idempotent test runner — handles DB setup, PYTHONPATH, and test selection.

Usage:
    # Full suite (all tests)
    python scripts/run_tests.sh

    # Specific test files
    python scripts/run_tests.sh tests/test_scheduler_jobs.py tests/test_bot.py

    # Single test
    python scripts/run_tests.sh tests/test_bot.py::test_cmd_start

    # With coverage
    python scripts/run_tests.sh --cov=app

    # With verbose output
    python scripts/run_tests.sh -v

This script is idempotent: running it multiple times with the same arguments
produces the same result. It handles:
- DATABASE_URL setup (uses /dev/shm/ to avoid polluting the real DB)
- PYTHONPATH setup
- Clean DB between runs (deletes the temp DB file before each run)
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(str(ROOT))

# Ensure PYTHONPATH includes the project root
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Set up a clean temp database for each run
db_path = f"/dev/shm/test_run_{os.getpid()}.db"
os.environ.setdefault("DATABASE_URL", f"sqlite:///{db_path}")

# Clean up any previous run's DB
if os.path.exists(db_path):
    os.remove(db_path)

# Remove coverage data from previous runs
cov_file = ROOT / ".coverage"
if cov_file.exists():
    cov_file.unlink()

import pytest

args = sys.argv[1:] if len(sys.argv) > 1 else ["tests/"]
sys.exit(pytest.main(args))
