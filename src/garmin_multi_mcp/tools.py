"""MCP tool registration for the multi-account Garmin server."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import CallToolResult

from garmin_multi_mcp.auth.oidc import get_current_principal
from garmin_multi_mcp.auth.policy import AuthorizationPolicy
from garmin_multi_mcp.auth.protected_resource import service_error_result
from garmin_multi_mcp.auth.runtime import require_account_access, require_scope, tool_security_meta
from garmin_multi_mcp.garmin_api import GarminClientManager
from garmin_multi_mcp.config import OIDCConfig


def _clean(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value is not None}


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


def _read_annotations(title: str) -> dict[str, Any]:
    return {
        "title": title,
        "readOnlyHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
        "destructiveHint": False,
    }


def register_tools(
    app: FastMCP,
    manager: GarminClientManager,
    auth_config: OIDCConfig,
    authz_policy: AuthorizationPolicy,
) -> FastMCP:
    """Register the multi-account Garmin tools."""

    @app.tool(
        annotations=_read_annotations("List Garmin Accounts"),
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.accounts_read_scope]),
        structured_output=False,
    )
    async def list_accounts(ctx: Context | None = None) -> str | CallToolResult:
        """List account IDs available to this MCP server."""

        auth_error = require_scope(
            auth_config,
            authz_policy,
            [auth_config.accounts_read_scope],
            ctx=ctx,
        )
        if auth_error:
            return auth_error

        principal = get_current_principal(ctx)
        allowed = set(authz_policy.get_allowed_account_ids(principal))
        accounts = [
            account for account in manager.list_accounts() if account["account_id"] in allowed
        ]
        return _json({"accounts": accounts})

    @app.tool(
        annotations=_read_annotations("Check Garmin Account Status"),
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.accounts_read_scope]),
        structured_output=False,
    )
    async def get_account_status(
        account_id: str,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """Validate token availability for one configured Garmin account."""

        auth_error = require_scope(
            auth_config,
            authz_policy,
            [auth_config.accounts_read_scope],
            ctx=ctx,
        )
        if auth_error:
            return auth_error

        account_access_error = require_account_access(
            auth_config,
            authz_policy,
            account_id=account_id,
            required_scopes=[auth_config.accounts_read_scope],
            ctx=ctx,
        )
        if account_access_error:
            return account_access_error

        try:
            return _json(manager.account_status(account_id))
        except Exception as err:
            return service_error_result(str(err))

    @app.tool(
        annotations=_read_annotations("Get Garmin Full Name"),
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.fitness_read_scope]),
        structured_output=False,
    )
    async def get_full_name(account_id: str, ctx: Context | None = None) -> str | CallToolResult:
        """Get the Garmin profile full name for a configured account."""

        auth_error = require_account_access(
            auth_config,
            authz_policy,
            account_id=account_id,
            required_scopes=[auth_config.fitness_read_scope],
            ctx=ctx,
        )
        if auth_error:
            return auth_error

        try:
            client = manager.get_client(account_id)
            return _json({"account_id": account_id, "full_name": client.get_full_name()})
        except Exception as err:
            return service_error_result(str(err))

    @app.tool(
        annotations=_read_annotations("Get Garmin User Profile"),
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.fitness_read_scope]),
        structured_output=False,
    )
    async def get_user_profile(account_id: str, ctx: Context | None = None) -> str | CallToolResult:
        """Get the Garmin user profile for one configured account."""

        auth_error = require_account_access(
            auth_config,
            authz_policy,
            account_id=account_id,
            required_scopes=[auth_config.fitness_read_scope],
            ctx=ctx,
        )
        if auth_error:
            return auth_error

        try:
            client = manager.get_client(account_id)
            return _json({"account_id": account_id, "profile": client.get_user_profile()})
        except Exception as err:
            return service_error_result(str(err))

    @app.tool(
        annotations=_read_annotations("Get Garmin Daily Stats"),
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.fitness_read_scope]),
        structured_output=False,
    )
    async def get_stats(
        account_id: str,
        date: str,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """Get curated daily wellness and activity stats for one account."""

        auth_error = require_account_access(
            auth_config,
            authz_policy,
            account_id=account_id,
            required_scopes=[auth_config.fitness_read_scope],
            ctx=ctx,
        )
        if auth_error:
            return auth_error

        try:
            client = manager.get_client(account_id)
            stats = client.get_stats(date)
            if not stats:
                return _json({"account_id": account_id, "date": date, "message": "No stats found"})

            summary = _clean(
                {
                    "account_id": account_id,
                    "date": stats.get("calendarDate"),
                    "total_steps": stats.get("totalSteps"),
                    "daily_step_goal": stats.get("dailyStepGoal"),
                    "distance_meters": stats.get("totalDistanceMeters"),
                    "total_calories": stats.get("totalKilocalories"),
                    "active_calories": stats.get("activeKilocalories"),
                    "resting_heart_rate_bpm": stats.get("restingHeartRate"),
                    "min_heart_rate_bpm": stats.get("minHeartRate"),
                    "max_heart_rate_bpm": stats.get("maxHeartRate"),
                    "avg_stress_level": stats.get("averageStressLevel"),
                    "body_battery_current": stats.get("bodyBatteryMostRecentValue"),
                    "body_battery_highest": stats.get("bodyBatteryHighestValue"),
                    "body_battery_lowest": stats.get("bodyBatteryLowestValue"),
                    "highly_active_seconds": stats.get("highlyActiveSeconds"),
                    "active_seconds": stats.get("activeSeconds"),
                    "sedentary_seconds": stats.get("sedentarySeconds"),
                    "sleeping_seconds": stats.get("sleepingSeconds"),
                    "moderate_intensity_minutes": stats.get("moderateIntensityMinutes"),
                    "vigorous_intensity_minutes": stats.get("vigorousIntensityMinutes"),
                }
            )
            return _json(summary)
        except Exception as err:
            return service_error_result(str(err))

    @app.tool(
        annotations=_read_annotations("Get Garmin Steps Data"),
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.fitness_read_scope]),
        structured_output=False,
    )
    async def get_steps_data(
        account_id: str,
        date: str,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """Get detailed 15-minute step interval data for one account."""

        auth_error = require_account_access(
            auth_config,
            authz_policy,
            account_id=account_id,
            required_scopes=[auth_config.fitness_read_scope],
            ctx=ctx,
        )
        if auth_error:
            return auth_error

        try:
            client = manager.get_client(account_id)
            return _json(
                {
                    "account_id": account_id,
                    "date": date,
                    "steps_data": client.get_steps_data(date),
                }
            )
        except Exception as err:
            return service_error_result(str(err))

    @app.tool(
        annotations=_read_annotations("Get Garmin Training Readiness"),
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.fitness_read_scope]),
        structured_output=False,
    )
    async def get_training_readiness(
        account_id: str,
        date: str,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """Get curated training readiness entries for one account."""

        auth_error = require_account_access(
            auth_config,
            authz_policy,
            account_id=account_id,
            required_scopes=[auth_config.fitness_read_scope],
            ctx=ctx,
        )
        if auth_error:
            return auth_error

        try:
            client = manager.get_client(account_id)
            readiness_entries = client.get_training_readiness(date)
            curated = []
            for entry in readiness_entries or []:
                curated.append(
                    _clean(
                        {
                            "date": entry.get("calendarDate"),
                            "timestamp": entry.get("timestampLocal"),
                            "level": entry.get("level"),
                            "score": entry.get("score"),
                            "feedback": entry.get("feedbackShort"),
                            "sleep_score": entry.get("sleepScore"),
                            "recovery_time_hours": round(entry.get("recoveryTime", 0) / 60, 1)
                            if entry.get("recoveryTime")
                            else None,
                            "hrv_status": entry.get("hrvStatus"),
                            "acute_load": entry.get("acuteLoad"),
                        }
                    )
                )

            return _json(
                {
                    "account_id": account_id,
                    "date": date,
                    "count": len(curated),
                    "entries": curated,
                }
            )
        except Exception as err:
            return service_error_result(str(err))

    @app.tool(
        annotations=_read_annotations("Get Garmin Activities By Date"),
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.fitness_read_scope]),
        structured_output=False,
    )
    async def get_activities_by_date(
        account_id: str,
        start_date: str,
        end_date: str,
        activity_type: str = "",
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """List activities in a date range, optionally filtered by type."""

        auth_error = require_account_access(
            auth_config,
            authz_policy,
            account_id=account_id,
            required_scopes=[auth_config.fitness_read_scope],
            ctx=ctx,
        )
        if auth_error:
            return auth_error

        try:
            client = manager.get_client(account_id)
            activities = client.get_activities_by_date(start_date, end_date, activity_type)
            curated = []
            for activity in activities or []:
                curated.append(
                    _clean(
                        {
                            "id": activity.get("activityId"),
                            "name": activity.get("activityName"),
                            "type": activity.get("activityType", {}).get("typeKey"),
                            "start_time": activity.get("startTimeLocal"),
                            "distance_meters": activity.get("distance"),
                            "duration_seconds": activity.get("duration"),
                            "calories": activity.get("calories"),
                            "avg_hr_bpm": activity.get("averageHR"),
                            "max_hr_bpm": activity.get("maxHR"),
                            "steps": activity.get("steps"),
                        }
                    )
                )

            return _json(
                {
                    "account_id": account_id,
                    "date_range": {"start": start_date, "end": end_date},
                    "activity_type": activity_type or None,
                    "count": len(curated),
                    "activities": curated,
                }
            )
        except Exception as err:
            return service_error_result(str(err))

    @app.tool(
        annotations=_read_annotations("Get Garmin Activities For Date"),
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.fitness_read_scope]),
        structured_output=False,
    )
    async def get_activities_fordate(
        account_id: str,
        date: str,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """Get the day's activity list for one account."""

        auth_error = require_account_access(
            auth_config,
            authz_policy,
            account_id=account_id,
            required_scopes=[auth_config.fitness_read_scope],
            ctx=ctx,
        )
        if auth_error:
            return auth_error

        try:
            client = manager.get_client(account_id)
            data = client.get_activities_fordate(date)
            payload = (data or {}).get("ActivitiesForDay", {}).get("payload", [])
            curated = []
            for activity in payload:
                curated.append(
                    _clean(
                        {
                            "id": activity.get("activityId"),
                            "name": activity.get("activityName"),
                            "type": activity.get("activityType", {}).get("typeKey"),
                            "start_time": activity.get("startTimeLocal"),
                            "distance_meters": activity.get("distance"),
                            "duration_seconds": activity.get("duration"),
                            "calories": activity.get("calories"),
                            "avg_hr_bpm": activity.get("averageHR"),
                            "steps": activity.get("steps"),
                        }
                    )
                )
            return _json(
                {
                    "account_id": account_id,
                    "date": date,
                    "count": len(curated),
                    "activities": curated,
                }
            )
        except Exception as err:
            return service_error_result(str(err))

    @app.tool(
        annotations=_read_annotations("Get Garmin Activity"),
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.fitness_read_scope]),
        structured_output=False,
    )
    async def get_activity(
        account_id: str,
        activity_id: int,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """Get curated details for one Garmin activity."""

        auth_error = require_account_access(
            auth_config,
            authz_policy,
            account_id=account_id,
            required_scopes=[auth_config.fitness_read_scope],
            ctx=ctx,
        )
        if auth_error:
            return auth_error

        try:
            client = manager.get_client(account_id)
            activity = client.get_activity(activity_id)
            summary = (activity or {}).get("summaryDTO", {})
            activity_type = (activity or {}).get("activityTypeDTO", {})
            metadata = (activity or {}).get("metadataDTO", {})
            curated = _clean(
                {
                    "account_id": account_id,
                    "id": (activity or {}).get("activityId"),
                    "name": (activity or {}).get("activityName"),
                    "type": activity_type.get("typeKey"),
                    "start_time_local": summary.get("startTimeLocal"),
                    "duration_seconds": summary.get("duration"),
                    "moving_duration_seconds": summary.get("movingDuration"),
                    "distance_meters": summary.get("distance"),
                    "avg_speed_mps": summary.get("averageSpeed"),
                    "max_speed_mps": summary.get("maxSpeed"),
                    "avg_hr_bpm": summary.get("averageHR"),
                    "max_hr_bpm": summary.get("maxHR"),
                    "calories": summary.get("calories"),
                    "steps": summary.get("steps"),
                    "training_effect": summary.get("trainingEffect"),
                    "training_load": summary.get("activityTrainingLoad"),
                    "lap_count": metadata.get("lapCount"),
                    "device_manufacturer": metadata.get("manufacturer"),
                }
            )
            return _json(curated)
        except Exception as err:
            return service_error_result(str(err))

    @app.tool(
        annotations=_read_annotations("Get Garmin Activity Splits"),
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.fitness_read_scope]),
        structured_output=False,
    )
    async def get_activity_splits(
        account_id: str,
        activity_id: int,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """Get lap splits for one Garmin activity."""

        auth_error = require_account_access(
            auth_config,
            authz_policy,
            account_id=account_id,
            required_scopes=[auth_config.fitness_read_scope],
            ctx=ctx,
        )
        if auth_error:
            return auth_error

        try:
            client = manager.get_client(account_id)
            splits = client.get_activity_splits(activity_id)
            laps = (splits or {}).get("lapDTOs", [])
            curated_laps = []
            for lap in laps:
                summary = lap.get("summaryDTO", {})
                curated_laps.append(
                    _clean(
                        {
                            "lap": lap.get("lapIndex"),
                            "distance_meters": summary.get("distance"),
                            "duration_seconds": summary.get("elapsedDuration"),
                            "avg_speed_mps": summary.get("averageSpeed"),
                            "avg_hr_bpm": summary.get("averageHR"),
                            "max_hr_bpm": summary.get("maxHR"),
                            "calories": summary.get("calories"),
                        }
                    )
                )

            return _json(
                {
                    "account_id": account_id,
                    "activity_id": activity_id,
                    "lap_count": len(curated_laps),
                    "laps": curated_laps,
                }
            )
        except Exception as err:
            return service_error_result(str(err))

    return app
