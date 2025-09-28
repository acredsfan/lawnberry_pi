import os
import os.path
import pytest

# Skip placeholder WebSocket topic tests by default until implemented
RUN_PLACEHOLDER = os.getenv("RUN_PLACEHOLDER_CONTRACT", "0") == "1"

PLACEHOLDER_BASENAMES = {
    "test_websocket_topics.py",
}


def pytest_collection_modifyitems(config, items):
    if RUN_PLACEHOLDER:
        return

    skip_placeholder = pytest.mark.skip(
        reason=(
            "Placeholder contract test skipped by default. "
            "Set RUN_PLACEHOLDER_CONTRACT=1 to run."
        )
    )

    for item in items:
        basename = os.path.basename(str(item.fspath))
        if basename in PLACEHOLDER_BASENAMES:
            item.add_marker(skip_placeholder)
