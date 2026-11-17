"""Small helpers shared by the standalone analytics examples."""

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Directly executing a file puts this examples directory, not the repository
# root, on sys.path. Add the root so ``src.server`` imports work without
# requiring callers to set PYTHONPATH.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.server.validation import AnalyticsError


def add_range_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the common inclusive, timezone-aware time range arguments."""
    parser.add_argument(
        "--start", required=True, help="Inclusive ISO-8601 timestamp with offset"
    )
    parser.add_argument(
        "--end", required=True, help="Inclusive ISO-8601 timestamp with offset"
    )


def print_result(call: Callable[[], Any]) -> None:
    """Print a result or the stable public analytics error schema as JSON."""
    try:
        result = call()
    except AnalyticsError as exc:
        print(json.dumps(exc.as_dict(), indent=2))
        raise SystemExit(2) from exc
    print(json.dumps(result, indent=2, default=str))
