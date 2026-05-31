"""Shared fixtures for experiment tests.

Re-uses the storage reset from the main test conftest.
"""

from __future__ import annotations

import copy
import pytest

from services.mcp_server import storage

# Snapshot originals at import time
_ORIG_LOGS_DB = copy.deepcopy(storage.LOGS_DB)
_ORIG_ORDERS_DB = copy.deepcopy(storage.ORDERS_DB)
_ORIG_EISSD_DB = copy.deepcopy(storage.EISSD_DB)
_ORIG_OTRS_TICKETS = copy.deepcopy(storage.OTRS_TICKETS)
_ORIG_OTRS_COMMENTS = copy.deepcopy(storage.OTRS_COMMENTS)


@pytest.fixture(autouse=True)
def reset_storage():
    """Reset all in-memory mock databases before each test."""
    storage.LOGS_DB.clear()
    storage.LOGS_DB.update(copy.deepcopy(_ORIG_LOGS_DB))
    storage.ORDERS_DB.clear()
    storage.ORDERS_DB.update(copy.deepcopy(_ORIG_ORDERS_DB))
    storage.EISSD_DB.clear()
    storage.EISSD_DB.update(copy.deepcopy(_ORIG_EISSD_DB))
    storage.OTRS_TICKETS.clear()
    storage.OTRS_TICKETS.update(copy.deepcopy(_ORIG_OTRS_TICKETS))
    storage.OTRS_COMMENTS.clear()
    storage.OTRS_COMMENTS.extend(copy.deepcopy(_ORIG_OTRS_COMMENTS))
    yield
    storage.LOGS_DB.clear()
    storage.LOGS_DB.update(copy.deepcopy(_ORIG_LOGS_DB))
    storage.ORDERS_DB.clear()
    storage.ORDERS_DB.update(copy.deepcopy(_ORIG_ORDERS_DB))
    storage.EISSD_DB.clear()
    storage.EISSD_DB.update(copy.deepcopy(_ORIG_EISSD_DB))
    storage.OTRS_TICKETS.clear()
    storage.OTRS_TICKETS.update(copy.deepcopy(_ORIG_OTRS_TICKETS))
    storage.OTRS_COMMENTS.clear()
    storage.OTRS_COMMENTS.extend(copy.deepcopy(_ORIG_OTRS_COMMENTS))
