# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Root test conftest — gates integration tests behind ``--integration``."""

from __future__ import annotations

import pathlib

import pytest

_INTEGRATION_DIR = pathlib.Path(__file__).parent / "integration"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="Run integration tests (requires a live Agentspan server).",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Auto-mark every test under ``tests/integration/`` and skip unless opted-in."""
    run_integration = config.getoption("--integration", default=False)
    skip_marker = pytest.mark.skip(reason="need --integration flag to run")

    for item in items:
        # Auto-apply the integration marker to anything inside tests/integration/
        if _INTEGRATION_DIR in pathlib.Path(item.fspath).parents:
            item.add_marker(pytest.mark.integration)
            if not run_integration:
                item.add_marker(skip_marker)
