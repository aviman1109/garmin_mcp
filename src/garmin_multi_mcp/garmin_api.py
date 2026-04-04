"""Garmin account registry and client helpers."""

from __future__ import annotations

import io
import os
import sys
from dataclasses import asdict
from pathlib import Path

import requests
from garminconnect import Garmin, GarminConnectAuthenticationError
from garth.exc import GarthHTTPError

from garmin_multi_mcp.config import GarminAccount


def resolve_value(raw: str | None, file_path: str | None, env_var: str | None = None) -> str | None:
    """Resolve a value directly, from a file path, or from an environment variable."""

    sources = sum(1 for s in (raw, file_path, env_var) if s)
    if sources > 1:
        raise ValueError("Only one of direct value, file path, and env var may be provided")
    if env_var:
        return os.environ.get(env_var) or None
    if file_path:
        return Path(os.path.expanduser(file_path)).read_text().rstrip()
    return raw


def token_exists(account: GarminAccount) -> bool:
    return Path(account.expanded_token_path).exists()


def validate_tokens(account: GarminAccount) -> tuple[bool, str]:
    """Check whether stored tokens are usable."""

    if not token_exists(account):
        return False, f"Token directory not found: {account.expanded_token_path}"

    old_stderr = sys.stderr
    sys.stderr = io.StringIO()
    try:
        client = Garmin(is_cn=account.is_cn)
        client.login(account.expanded_token_path)
        client.get_full_name()
        return True, ""
    except FileNotFoundError:
        return False, f"Token files missing in {account.expanded_token_path}"
    except GarthHTTPError as err:
        return False, f"Token authentication failed: {str(err).split(':')[0]}"
    except Exception as err:  # pragma: no cover - defensive path
        return False, f"Token validation failed: {str(err).split(':')[0]}"
    finally:
        sys.stderr = old_stderr


class GarminClientManager:
    """Small in-memory cache of authenticated Garmin clients."""

    def __init__(self, accounts: dict[str, GarminAccount], default_account_id: str | None = None):
        self._accounts = accounts
        self._default_account_id = default_account_id
        self._clients: dict[str, Garmin] = {}

    def list_accounts(self) -> list[dict[str, object]]:
        return [
            {
                "account_id": account.account_id,
                "label": account.label,
                "is_cn": account.is_cn,
                "token_path": account.expanded_token_path,
            }
            for account in self._accounts.values()
        ]

    def get_account(self, account_id: str | None = None) -> GarminAccount:
        resolved_id = account_id or self._default_account_id
        if not resolved_id:
            raise ValueError("account_id is required because no default account is configured")
        try:
            return self._accounts[resolved_id]
        except KeyError as err:
            available = ", ".join(sorted(self._accounts))
            raise ValueError(f"Unknown account_id '{resolved_id}'. Available: {available}") from err

    def get_client(self, account_id: str | None = None, refresh: bool = False) -> Garmin:
        account = self.get_account(account_id)
        if refresh:
            self._clients.pop(account.account_id, None)
        if account.account_id not in self._clients:
            self._clients[account.account_id] = self._login_with_tokens(account)
        return self._clients[account.account_id]

    def account_status(self, account_id: str | None = None) -> dict[str, object]:
        account = self.get_account(account_id)
        valid, error = validate_tokens(account)
        return {
            **asdict(account),
            "token_path": account.expanded_token_path,
            "token_base64_path": account.expanded_token_base64_path,
            "tokens_exist": token_exists(account),
            "tokens_valid": valid,
            "token_error": error,
        }

    def _login_with_tokens(self, account: GarminAccount) -> Garmin:
        client = Garmin(is_cn=account.is_cn)
        try:
            client.login(account.expanded_token_path)
            return client
        except (FileNotFoundError, GarthHTTPError, GarminConnectAuthenticationError) as err:
            raise RuntimeError(
                f"Unable to authenticate account '{account.account_id}' from token path "
                f"{account.expanded_token_path}. Run garmin-multi-mcp-auth --account-id "
                f"{account.account_id} to refresh tokens. Root cause: {err}"
            ) from err


def prompt_mfa() -> str:
    print("\nGarmin Connect MFA required. Please check your email/phone for the code.")
    return input("Enter MFA code: ")


def authenticate_account(
    account: GarminAccount,
    force_reauth: bool = False,
) -> tuple[bool, str]:
    """Authenticate one account and persist tokens to its configured paths."""

    if not force_reauth:
        valid, error = validate_tokens(account)
        if valid:
            return True, "Existing tokens are valid."
        if token_exists(account):
            print(f"Existing tokens are invalid for {account.account_id}: {error}")

    email = resolve_value(account.email, account.email_file, account.email_env) or os.getenv("GARMIN_EMAIL")
    password = resolve_value(account.password, account.password_file, account.password_env) or os.getenv("GARMIN_PASSWORD")

    if not email:
        email = input("Email: ").strip()
    if not password:
        import getpass

        password = getpass.getpass("Password: ")

    if not email or not password:
        return False, "Email and password are required for authentication"

    try:
        client = Garmin(
            email=email,
            password=password,
            is_cn=account.is_cn,
            prompt_mfa=prompt_mfa,
        )
        client.login()
        Path(account.expanded_token_path).parent.mkdir(parents=True, exist_ok=True)
        client.garth.dump(account.expanded_token_path)
        Path(account.expanded_token_base64_path).write_text(client.garth.dumps())
        return True, f"Tokens saved for account '{account.account_id}'"
    except (
        FileNotFoundError,
        GarthHTTPError,
        GarminConnectAuthenticationError,
        requests.exceptions.HTTPError,
    ) as err:
        return False, str(err)
