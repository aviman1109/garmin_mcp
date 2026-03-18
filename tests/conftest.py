"""Shared fixtures for functional tests.

Requires:
- config/accounts.yaml with at least one account
- Valid tokens at the configured token_path

Run inside the container:
    docker exec <container> pytest tests/ -v
Or directly if tokens are available locally:
    GARMIN_ACCOUNTS_FILE=config/accounts.yaml pytest tests/ -v
"""

from __future__ import annotations

import os
import pytest

from garmin_multi_mcp.config import load_accounts
from garmin_multi_mcp.garmin_api import GarminClientManager

ACCOUNTS_FILE = os.getenv("GARMIN_ACCOUNTS_FILE", "config/accounts.yaml")


@pytest.fixture(scope="session")
def manager() -> GarminClientManager:
    accounts, default_id, _ = load_accounts(ACCOUNTS_FILE)
    return GarminClientManager(accounts, default_id)


@pytest.fixture(scope="session")
def default_account_id(manager: GarminClientManager) -> str:
    accounts = manager.list_accounts()
    assert accounts, "No accounts configured in accounts.yaml"
    return accounts[0]["account_id"]


@pytest.fixture(scope="session")
def garmin_client(manager: GarminClientManager, default_account_id: str):
    return manager.get_client(default_account_id)


@pytest.fixture(scope="session")
def recent_activity_id(garmin_client) -> int:
    activities = garmin_client.get_activities(0, 1)
    assert activities, "No activities found for this account"
    return activities[0]["activityId"]


@pytest.fixture(scope="session")
def test_date() -> str:
    """Use a recent fixed date with known data."""
    import datetime
    return (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
