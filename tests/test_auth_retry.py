"""Tests for with_auth_retry — re-login on 401 then retry once."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from garth.exc import GarthHTTPError
from garminconnect import GarminConnectAuthenticationError

from garmin_multi_mcp.garmin_api import _is_auth_failure, with_auth_retry


def _garth_err(status: int, msg: str) -> GarthHTTPError:
    resp = SimpleNamespace(status_code=status, text=msg)
    http_err = SimpleNamespace(response=resp)
    return GarthHTTPError(msg, http_err)


def _garth_401() -> GarthHTTPError:
    return _garth_err(401, "401 unauthorized")


def _garth_500() -> GarthHTTPError:
    return _garth_err(500, "500 boom")


def test_is_auth_failure_classifier():
    assert _is_auth_failure(_garth_401())
    assert _is_auth_failure(GarminConnectAuthenticationError("bad creds"))
    assert not _is_auth_failure(_garth_500())
    assert not _is_auth_failure(ValueError("random"))


def test_with_auth_retry_passthrough_on_success():
    manager = MagicMock()
    manager.get_client.return_value = "client-v1"
    fn = MagicMock(return_value="ok")

    assert with_auth_retry(manager, "acc", fn) == "ok"
    fn.assert_called_once_with("client-v1")
    manager.get_client.assert_called_once_with("acc")


def test_with_auth_retry_retries_once_on_401():
    manager = MagicMock()
    manager.get_client.side_effect = ["client-v1", "client-v2"]

    calls = {"n": 0}

    def fn(client):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _garth_401()
        return f"ok-from-{client}"

    assert with_auth_retry(manager, "acc", fn) == "ok-from-client-v2"
    assert calls["n"] == 2
    # second get_client must force refresh
    assert manager.get_client.call_args_list[1].kwargs == {"refresh": True}


def test_with_auth_retry_propagates_non_auth_errors():
    manager = MagicMock()
    manager.get_client.return_value = "client-v1"

    def fn(_):
        raise _garth_500()

    with pytest.raises(GarthHTTPError):
        with_auth_retry(manager, "acc", fn)
    # should NOT attempt a refresh on non-auth errors
    manager.get_client.assert_called_once_with("acc")


def test_with_auth_retry_fails_on_second_attempt():
    manager = MagicMock()
    manager.get_client.side_effect = ["c1", "c2"]

    def fn(_):
        raise _garth_401()

    with pytest.raises(GarthHTTPError):
        with_auth_retry(manager, "acc", fn)
    assert manager.get_client.call_count == 2
