"""Configuration helpers for the multi-account Garmin MCP server."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

AuthMode = Literal["disabled", "mixed", "oauth_required"]


@dataclass(frozen=True)
class GarminAccount:
    """Static account configuration loaded from YAML."""

    account_id: str
    label: str
    token_path: str
    token_base64_path: str
    is_cn: bool = False
    email: str | None = None
    email_file: str | None = None
    email_env: str | None = None
    password: str | None = None
    password_file: str | None = None
    password_env: str | None = None

    @property
    def expanded_token_path(self) -> str:
        return os.path.expanduser(self.token_path)

    @property
    def expanded_token_base64_path(self) -> str:
        return os.path.expanduser(self.token_base64_path)


@dataclass(frozen=True)
class AccountAccessRule:
    """Map an authenticated OIDC principal to allowed Garmin account IDs."""

    subjects: list[str]
    emails: list[str]
    groups: list[str]
    account_ids: list[str]
    default_account_id: str | None = None


@dataclass(frozen=True)
class OIDCConfig:
    """OIDC/OAuth configuration for protecting the Garmin MCP resource server."""

    mode: AuthMode
    issuer: str | None
    discovery_url: str | None
    jwks_url: str | None
    project_id: str | None
    project_secret: str | None
    audience: str | None
    resource_url: str | None
    authorization_url: str | None
    accounts_read_scope: str
    fitness_read_scope: str
    access_rules: list[AccountAccessRule]

    @property
    def enabled(self) -> bool:
        return self.mode != "disabled"

    @property
    def scopes_supported(self) -> list[str]:
        scopes = [
            self.accounts_read_scope,
            self.fitness_read_scope,
        ]
        return [scope for scope in dict.fromkeys(scope for scope in scopes if scope)]

    @property
    def connector_auth_scopes(self) -> list[str]:
        scopes = ["openid", "profile", "email", "offline_access", *self.scopes_supported]
        return [scope for scope in dict.fromkeys(scope for scope in scopes if scope)]

    @property
    def resource_metadata_url(self) -> str | None:
        if not self.resource_url:
            return None
        return f"{self.resource_url.rstrip('/')}/.well-known/oauth-protected-resource"


@dataclass(frozen=True)
class AppConfig:
    """Application configuration."""

    accounts_file: str
    default_account_id: str | None
    transport: str
    host: str
    port: int
    path: str
    allowed_hosts: list[str]
    allowed_origins: list[str]
    oidc: OIDCConfig


def _parse_csv_env(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    raise ValueError(f"Expected string or list value, got: {type(value)!r}")


def _normalize_account(raw: dict[str, Any], token_root: str) -> GarminAccount:
    account_id = str(raw["account_id"]).strip()
    if not account_id:
        raise ValueError("Account configuration contains an empty account_id")

    label = str(raw.get("label") or account_id).strip()
    token_path = raw.get("token_path") or f"{token_root.rstrip('/')}/{account_id}"
    token_base64_path = raw.get("token_base64_path") or f"{token_root.rstrip('/')}/{account_id}.b64"

    return GarminAccount(
        account_id=account_id,
        label=label,
        token_path=str(token_path),
        token_base64_path=str(token_base64_path),
        is_cn=bool(raw.get("is_cn", False)),
        email=raw.get("email"),
        email_file=raw.get("email_file"),
        email_env=raw.get("email_env"),
        password=raw.get("password"),
        password_file=raw.get("password_file"),
        password_env=raw.get("password_env"),
    )


def _normalize_access_rule(raw: dict[str, Any]) -> AccountAccessRule:
    account_ids = _parse_list(raw.get("account_ids"))
    if not account_ids:
        raise ValueError("Auth access rule must define at least one account_id")

    return AccountAccessRule(
        subjects=_parse_list(raw.get("subjects") or raw.get("subject")),
        emails=_parse_list(raw.get("emails") or raw.get("email")),
        groups=_parse_list(raw.get("groups") or raw.get("group")),
        account_ids=account_ids,
        default_account_id=str(raw["default_account_id"])
        if raw.get("default_account_id") is not None
        else None,
    )


def _load_oidc_config(data: dict[str, Any]) -> OIDCConfig:
    raw_auth = data.get("auth") or {}

    mode = str(os.getenv("GARMIN_AUTH_MODE") or raw_auth.get("mode") or "disabled").lower()
    if mode not in {"disabled", "mixed", "oauth_required"}:
        raise ValueError(
            f"Unsupported GARMIN_AUTH_MODE '{mode}'. "
            "Use disabled, mixed, or oauth_required."
        )

    issuer = os.getenv("GARMIN_OIDC_ISSUER") or raw_auth.get("issuer")
    discovery_url = os.getenv("GARMIN_OIDC_DISCOVERY_URL") or raw_auth.get("discovery_url")
    jwks_url = os.getenv("GARMIN_OIDC_JWKS_URL") or raw_auth.get("jwks_url")
    project_id = (
        os.getenv("GARMIN_OIDC_PROJECT_ID")
        or raw_auth.get("project_id")
        or os.getenv("GARMIN_OIDC_AUDIENCE")
        or raw_auth.get("audience")
    )
    project_secret = os.getenv("GARMIN_OIDC_PROJECT_SECRET") or raw_auth.get("project_secret")
    audience = os.getenv("GARMIN_OIDC_AUDIENCE") or raw_auth.get("audience")
    resource_url = os.getenv("GARMIN_RESOURCE_URL") or raw_auth.get("resource_url")
    authorization_url = (
        os.getenv("GARMIN_OIDC_AUTHORIZATION_URL")
        or raw_auth.get("authorization_url")
        or None
    )
    accounts_read_scope = (
        os.getenv("GARMIN_OIDC_ACCOUNTS_READ_SCOPE")
        or raw_auth.get("accounts_read_scope")
        or "accounts.read"
    )
    fitness_read_scope = (
        os.getenv("GARMIN_OIDC_FITNESS_READ_SCOPE")
        or raw_auth.get("fitness_read_scope")
        or "fitness.read"
    )
    access_rules = [
        _normalize_access_rule(rule)
        for rule in (raw_auth.get("access_rules") or [])
    ]

    oidc = OIDCConfig(
        mode=mode,  # type: ignore[arg-type]
        issuer=str(issuer) if issuer else None,
        discovery_url=str(discovery_url) if discovery_url else None,
        jwks_url=str(jwks_url) if jwks_url else None,
        project_id=str(project_id) if project_id else None,
        project_secret=str(project_secret) if project_secret else None,
        audience=str(audience) if audience else None,
        resource_url=str(resource_url).rstrip("/") if resource_url else None,
        authorization_url=str(authorization_url).rstrip("/") if authorization_url else None,
        accounts_read_scope=str(accounts_read_scope),
        fitness_read_scope=str(fitness_read_scope),
        access_rules=access_rules,
    )

    if oidc.enabled and not oidc.resource_url:
        raise ValueError("OAuth mode requires GARMIN_RESOURCE_URL or auth.resource_url")
    if oidc.enabled and not oidc.issuer and not oidc.discovery_url:
        raise ValueError("OAuth mode requires GARMIN_OIDC_ISSUER or discovery_url")

    return oidc


def load_accounts(accounts_file: str) -> tuple[dict[str, GarminAccount], str | None, OIDCConfig]:
    """Load multi-account registry from YAML."""

    config_path = Path(os.path.expanduser(accounts_file))
    if not config_path.exists():
        raise FileNotFoundError(
            f"Accounts configuration not found: {config_path}. "
            "Create it from config/accounts.example.yaml."
        )

    data = yaml.safe_load(config_path.read_text()) or {}
    token_root = str(data.get("token_root") or os.getenv("TOKEN_ROOT") or "/data/tokens")
    raw_accounts = data.get("accounts") or []
    if not raw_accounts:
        raise ValueError(f"No accounts configured in {config_path}")

    accounts: dict[str, GarminAccount] = {}
    for raw in raw_accounts:
        account = _normalize_account(raw, token_root)
        if account.account_id in accounts:
            raise ValueError(f"Duplicate account_id '{account.account_id}' in {config_path}")
        accounts[account.account_id] = account

    default_account_id = data.get("default_account_id")
    if default_account_id and default_account_id not in accounts:
        raise ValueError(
            f"default_account_id '{default_account_id}' is not present in accounts list"
        )

    oidc = _load_oidc_config(data)
    for rule in oidc.access_rules:
        for account_id in rule.account_ids:
            if account_id != "*" and account_id not in accounts:
                raise ValueError(f"Auth rule references unknown account_id '{account_id}'")
        if rule.default_account_id and rule.default_account_id not in accounts:
            raise ValueError(
                f"Auth rule default_account_id '{rule.default_account_id}' is not in accounts list"
            )

    return accounts, default_account_id, oidc


def load_app_config() -> AppConfig:
    """Load runtime configuration from environment."""

    default_allowed_hosts = [
        "127.0.0.1:*",
        "localhost:*",
        "[::1]:*",
    ]
    default_allowed_origins = [
        "http://127.0.0.1:*",
        "http://localhost:*",
        "http://[::1]:*",
    ]

    return AppConfig(
        accounts_file=os.getenv("GARMIN_ACCOUNTS_FILE", "config/accounts.yaml"),
        default_account_id=os.getenv("GARMIN_DEFAULT_ACCOUNT_ID") or None,
        transport=os.getenv("MCP_TRANSPORT", "http"),
        host=os.getenv("MCP_HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8080")),
        path=os.getenv("MCP_PATH", "/mcp"),
        allowed_hosts=default_allowed_hosts + _parse_csv_env(os.getenv("MCP_ALLOWED_HOSTS")),
        allowed_origins=default_allowed_origins + _parse_csv_env(
            os.getenv("MCP_ALLOWED_ORIGINS")
        ),
        oidc=OIDCConfig(
            mode="disabled",
            issuer=None,
            discovery_url=None,
            jwks_url=None,
            project_id=None,
            project_secret=None,
            audience=None,
            resource_url=None,
            authorization_url=None,
            accounts_read_scope="accounts.read",
            fitness_read_scope="fitness.read",
            access_rules=[],
        ),
    )
