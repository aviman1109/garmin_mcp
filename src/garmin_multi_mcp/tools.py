"""MCP tool registration for the multi-account Garmin server."""

from __future__ import annotations

import base64
import io
import json
from typing import Any

import matplotlib
matplotlib.use("Agg")  # headless — no display needed
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import CallToolResult, ImageContent

from garmin_multi_mcp.auth.oidc import get_current_principal
from garmin_multi_mcp.auth.policy import AuthorizationPolicy
from garmin_multi_mcp.auth.protected_resource import service_error_result
from garmin_multi_mcp.auth.runtime import require_account_access, require_scope, tool_security_meta
from garmin_multi_mcp.garmin_api import GarminClientManager, with_auth_retry
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
                curated_laps.append(
                    _clean(
                        {
                            "lap": lap.get("lapIndex"),
                            "start_time": lap.get("startTimeGMT"),
                            "distance_meters": lap.get("distance"),
                            "duration_seconds": lap.get("elapsedDuration"),
                            "moving_duration_seconds": lap.get("movingDuration"),
                            "avg_speed_mps": lap.get("averageSpeed"),
                            "max_speed_mps": lap.get("maxSpeed"),
                            "avg_hr_bpm": lap.get("averageHR"),
                            "max_hr_bpm": lap.get("maxHR"),
                            "avg_cadence_spm": lap.get("averageRunCadence"),
                            "max_cadence_spm": lap.get("maxRunCadence"),
                            "calories": lap.get("calories"),
                            "elevation_gain_m": lap.get("elevationGain"),
                            "avg_power_watts": lap.get("averagePower"),
                            "normalized_power_watts": lap.get("normalizedPower"),
                            "stride_length_m": lap.get("strideLength"),
                            "vertical_oscillation_mm": lap.get("verticalOscillation"),
                            "ground_contact_time_ms": lap.get("groundContactTime"),
                            "grade_adjusted_speed_mps": lap.get("avgGradeAdjustedSpeed"),
                            "intensity": lap.get("intensityType"),
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

    @app.tool(
        annotations=_read_annotations("Get Activity Typed Splits"),
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.fitness_read_scope]),
        structured_output=False,
    )
    async def get_activity_typed_splits(
        account_id: str,
        activity_id: int,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """Get typed splits for one activity (e.g. run vs walk intervals, active vs rest)."""

        auth_error = require_account_access(
            auth_config, authz_policy, account_id=account_id,
            required_scopes=[auth_config.fitness_read_scope], ctx=ctx,
        )
        if auth_error:
            return auth_error

        try:
            client = manager.get_client(account_id)
            raw = client.get_activity_typed_splits(activity_id)
            return _json({"account_id": account_id, "activity_id": activity_id, "typed_splits": raw})
        except Exception as err:
            return service_error_result(str(err))

    @app.tool(
        annotations=_read_annotations("Get Activity HR Zones"),
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.fitness_read_scope]),
        structured_output=False,
    )
    async def get_activity_hr_zones(
        account_id: str,
        activity_id: int,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """Get heart rate zone distribution for one activity (time spent in each HR zone)."""

        auth_error = require_account_access(
            auth_config, authz_policy, account_id=account_id,
            required_scopes=[auth_config.fitness_read_scope], ctx=ctx,
        )
        if auth_error:
            return auth_error

        try:
            client = manager.get_client(account_id)
            raw = client.get_activity_hr_in_timezones(activity_id)
            zones = []
            for zone in (raw or []):
                zones.append(_clean({
                    "zone": zone.get("zoneNumber"),
                    "zone_low_bpm": zone.get("zoneLowBoundary"),
                    "zone_high_bpm": zone.get("zoneHighBoundary"),
                    "seconds_in_zone": zone.get("secsInZone"),
                }))
            return _json({"account_id": account_id, "activity_id": activity_id, "hr_zones": zones})
        except Exception as err:
            return service_error_result(str(err))

    @app.tool(
        annotations=_read_annotations("Get Activity Power Zones"),
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.fitness_read_scope]),
        structured_output=False,
    )
    async def get_activity_power_zones(
        account_id: str,
        activity_id: int,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """Get power zone distribution for one activity (time in each power zone). Only available for activities with power data."""

        auth_error = require_account_access(
            auth_config, authz_policy, account_id=account_id,
            required_scopes=[auth_config.fitness_read_scope], ctx=ctx,
        )
        if auth_error:
            return auth_error

        try:
            client = manager.get_client(account_id)
            raw = client.get_activity_power_in_timezones(activity_id)
            zones = []
            for zone in (raw or []):
                zones.append(_clean({
                    "zone": zone.get("zoneNumber"),
                    "zone_low_watts": zone.get("zoneLowBoundary"),
                    "zone_high_watts": zone.get("zoneHighBoundary"),
                    "seconds_in_zone": zone.get("secsInZone"),
                }))
            return _json({"account_id": account_id, "activity_id": activity_id, "power_zones": zones})
        except Exception as err:
            return service_error_result(str(err))

    @app.tool(
        annotations=_read_annotations("Get Activity Weather"),
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.fitness_read_scope]),
        structured_output=False,
    )
    async def get_activity_weather(
        account_id: str,
        activity_id: int,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """Get weather conditions during one activity (temperature, humidity, wind, conditions)."""

        auth_error = require_account_access(
            auth_config, authz_policy, account_id=account_id,
            required_scopes=[auth_config.fitness_read_scope], ctx=ctx,
        )
        if auth_error:
            return auth_error

        try:
            client = manager.get_client(account_id)
            raw = client.get_activity_weather(activity_id)
            if not raw:
                return _json({"account_id": account_id, "activity_id": activity_id, "message": "No weather data available"})
            weather = _clean({
                "temperature_c": raw.get("temp"),
                "apparent_temperature_c": raw.get("apparentTemp"),
                "humidity_pct": raw.get("relativeHumidity"),
                "wind_direction_degrees": raw.get("windDirection"),
                "wind_speed_mps": raw.get("windSpeed"),
                "weather_type": raw.get("weatherTypeDTO", {}).get("desc") if raw.get("weatherTypeDTO") else None,
                "issue_date": raw.get("issueDate"),
            })
            return _json({"account_id": account_id, "activity_id": activity_id, "weather": weather})
        except Exception as err:
            return service_error_result(str(err))

    @app.tool(
        annotations=_read_annotations("Get Activity Exercise Sets"),
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.fitness_read_scope]),
        structured_output=False,
    )
    async def get_activity_exercise_sets(
        account_id: str,
        activity_id: int,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """Get exercise sets for a strength/cardio activity (sets, reps, weight, rest time)."""

        auth_error = require_account_access(
            auth_config, authz_policy, account_id=account_id,
            required_scopes=[auth_config.fitness_read_scope], ctx=ctx,
        )
        if auth_error:
            return auth_error

        try:
            client = manager.get_client(account_id)
            raw = client.get_activity_exercise_sets(activity_id)
            return _json({"account_id": account_id, "activity_id": activity_id, "exercise_sets": raw})
        except Exception as err:
            return service_error_result(str(err))

    # -----------------------------------------------------------------------
    # P1 Tools
    # -----------------------------------------------------------------------

    # Mapping from Garmin API metric keys to short field names used in responses.
    _METRIC_KEY_MAP = {
        "directTimestamp": "t",
        "sumElapsedDuration": "s",
        "sumDistance": "d",
        "directHeartRate": "hr",
        "directDoubleCadence": "cad",
        "directRunCadence": "cad",
        "directSpeed": "spd",
        "directGradeAdjustedSpeed": "spd_ga",
        "directElevation": "ele",
        "directPower": "pwr",
        "directStrideLength": "stride",
        "directVerticalOscillation": "vo_mm",
        "directGroundContactTime": "gct_ms",
        "directVerticalRatio": "vr_pct",
        "directPerformanceCondition": "pc",
        "directBodyBattery": "bb",
    }

    _METRIC_LEGEND = {
        "t": "timestamp_ms", "s": "elapsed_seconds", "d": "distance_meters",
        "hr": "heart_rate_bpm", "cad": "cadence_spm", "spd": "speed_mps",
        "spd_ga": "grade_adjusted_speed_mps", "ele": "elevation_m",
        "pwr": "power_watts", "stride": "stride_length_m",
        "vo_mm": "vertical_oscillation_mm", "gct_ms": "ground_contact_time_ms",
        "vr_pct": "vertical_ratio_pct", "pc": "performance_condition",
        "bb": "body_battery",
    }

    # Metrics that are always included as context (not filterable).
    _ALWAYS_INCLUDE = {"t", "s", "d"}

    @app.tool(
        annotations=_read_annotations("List Activity Metrics"),
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.fitness_read_scope]),
        structured_output=False,
    )
    async def list_activity_metrics(
        account_id: str,
        activity_id: int,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """List available time-series metrics for one activity.

        Call this first to discover which metrics an activity has,
        then use get_activity_details with a metrics filter to fetch specific ones.
        """

        auth_error = require_account_access(
            auth_config, authz_policy, account_id=account_id,
            required_scopes=[auth_config.fitness_read_scope], ctx=ctx,
        )
        if auth_error:
            return auth_error

        try:
            client = manager.get_client(account_id)
            raw = client.get_activity_details(activity_id, maxchart=1, maxpoly=0)
            if not raw:
                return _json({"account_id": account_id, "activity_id": activity_id, "message": "No detail data available"})

            descriptors = raw.get("metricDescriptors", [])
            available = []
            for d in descriptors:
                garmin_key = d["key"]
                short = _METRIC_KEY_MAP.get(garmin_key)
                if short:
                    available.append({
                        "key": short,
                        "description": _METRIC_LEGEND.get(short, garmin_key),
                        "filterable": short not in _ALWAYS_INCLUDE,
                    })

            return _json({
                "account_id": account_id,
                "activity_id": activity_id,
                "total_datapoints": raw.get("totalMetricsCount", 0),
                "available_metrics": available,
                "usage_hint": "Pass metric keys (e.g. metrics=['hr','spd','ele']) to get_activity_details to fetch specific metrics with higher resolution.",
            })
        except Exception as err:
            return service_error_result(str(err))

    @app.tool(
        annotations=_read_annotations("Get Activity Time-Series Details"),
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.fitness_read_scope]),
        structured_output=False,
    )
    async def get_activity_details(
        account_id: str,
        activity_id: int,
        max_datapoints: int = 200,
        metrics: list[str] | None = None,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """Get time-series for one activity: heart rate, cadence, pace, power, stride length, elevation.

        Returns sampled data points with named metric fields.
        max_datapoints controls sampling density (default 200, max ~2000).

        metrics: optional list of short metric keys to include (e.g. ["hr", "spd", "ele"]).
        When set, only those metrics (plus t/s/d context) are returned — this keeps
        the response small so you can request more datapoints per call.
        Use list_activity_metrics to discover available keys for an activity.
        """

        auth_error = require_account_access(
            auth_config, authz_policy, account_id=account_id,
            required_scopes=[auth_config.fitness_read_scope], ctx=ctx,
        )
        if auth_error:
            return auth_error

        # Build the set of short keys to include in the response.
        if metrics:
            include_keys = _ALWAYS_INCLUDE | set(metrics)
        else:
            include_keys = None  # include everything

        def _r(v, digits=1):
            """Round a float value; return None if falsy."""
            return round(v, digits) if v else None

        try:
            client = manager.get_client(account_id)
            raw = client.get_activity_details(activity_id, maxchart=max_datapoints, maxpoly=0)
            if not raw:
                return _json({"account_id": account_id, "activity_id": activity_id, "message": "No detail data available"})

            descriptors = raw.get("metricDescriptors", [])
            key_index = {d["key"]: i for i, d in enumerate(descriptors)}

            def _get(row: list, key: str):
                idx = key_index.get(key)
                return row[idx] if idx is not None else None

            points = []
            for item in raw.get("activityDetailMetrics", []):
                m = item["metrics"]
                ts_ms = _get(m, "directTimestamp")
                cadence = _get(m, "directDoubleCadence") or ((_get(m, "directRunCadence") or 0) * 2 or None)

                row = {
                    "t": int(ts_ms) if ts_ms else None,
                    "s": _r(_get(m, "sumElapsedDuration"), 0),
                    "d": _r(_get(m, "sumDistance"), 1),
                    "hr": _r(_get(m, "directHeartRate"), 0),
                    "cad": _r(cadence, 0),
                    "spd": _r(_get(m, "directSpeed"), 2),
                    "spd_ga": _r(_get(m, "directGradeAdjustedSpeed"), 2),
                    "ele": _r(_get(m, "directElevation"), 1),
                    "pwr": _r(_get(m, "directPower"), 0),
                    "stride": _r(_get(m, "directStrideLength"), 2),
                    "vo_mm": _r(_get(m, "directVerticalOscillation"), 1),
                    "gct_ms": _r(_get(m, "directGroundContactTime"), 0),
                    "vr_pct": _r(_get(m, "directVerticalRatio"), 1),
                    "pc": _r(_get(m, "directPerformanceCondition"), 0),
                    "bb": _r(_get(m, "directBodyBattery"), 0),
                }

                if include_keys:
                    row = {k: v for k, v in row.items() if k in include_keys}

                points.append(_clean(row))

            legend = {k: v for k, v in _METRIC_LEGEND.items()
                      if include_keys is None or k in include_keys}

            return _json({
                "account_id": account_id,
                "activity_id": activity_id,
                "total_datapoints": raw.get("totalMetricsCount", len(points)),
                "returned_datapoints": len(points),
                "filtered_metrics": metrics,
                "legend": legend,
                "timeseries": points,
            })
        except Exception as err:
            return service_error_result(str(err))

    @app.tool(
        annotations=_read_annotations("Get Training Status"),
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.fitness_read_scope]),
        structured_output=False,
    )
    async def get_training_status(
        account_id: str,
        date: str,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """Get training status for a date: VO2max, training load balance (aerobic low/high/anaerobic), and heat/altitude acclimatisation."""

        auth_error = require_account_access(
            auth_config, authz_policy, account_id=account_id,
            required_scopes=[auth_config.fitness_read_scope], ctx=ctx,
        )
        if auth_error:
            return auth_error

        try:
            client = manager.get_client(account_id)
            raw = client.get_training_status(date)
            if not raw:
                return _json({"account_id": account_id, "date": date, "message": "No training status data"})

            vo2_generic = (raw.get("mostRecentVO2Max") or {}).get("generic") or {}
            vo2_cycling = (raw.get("mostRecentVO2Max") or {}).get("cycling") or {}

            tlb_map = (raw.get("mostRecentTrainingLoadBalance") or {}).get("metricsTrainingLoadBalanceDTOMap") or {}
            load_entries = []
            for device_id, entry in tlb_map.items():
                load_entries.append(_clean({
                    "calendar_date": entry.get("calendarDate"),
                    "aerobic_low_load": entry.get("monthlyLoadAerobicLow"),
                    "aerobic_high_load": entry.get("monthlyLoadAerobicHigh"),
                    "anaerobic_load": entry.get("monthlyLoadAnaerobic"),
                    "training_load_balance_label": entry.get("trainingLoadBalanceDesc"),
                    "training_load_feedback": entry.get("trainingLoadBalanceFeedback"),
                    "load_7_day": entry.get("weeklyLoadAerobicLow", 0) + entry.get("weeklyLoadAerobicHigh", 0) + entry.get("weeklyLoadAnaerobic", 0),
                    "optimal_load_low": entry.get("optimalLoadRangeLow"),
                    "optimal_load_high": entry.get("optimalLoadRangeHigh"),
                    "recovery_time_seconds": entry.get("primaryActivityRecoveryTime"),
                }))

            return _json(_clean({
                "account_id": account_id,
                "date": date,
                "vo2max_running": vo2_generic.get("vo2MaxValue"),
                "vo2max_running_precise": vo2_generic.get("vo2MaxPreciseValue"),
                "vo2max_cycling": vo2_cycling.get("vo2MaxValue"),
                "vo2max_date": vo2_generic.get("calendarDate"),
                "training_load_balance": load_entries,
            }))
        except Exception as err:
            return service_error_result(str(err))

    @app.tool(
        annotations=_read_annotations("Get Max Metrics (VO2max)"),
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.fitness_read_scope]),
        structured_output=False,
    )
    async def get_max_metrics(
        account_id: str,
        date: str,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """Get VO2max and fitness age metrics for a date (running and cycling)."""

        auth_error = require_account_access(
            auth_config, authz_policy, account_id=account_id,
            required_scopes=[auth_config.fitness_read_scope], ctx=ctx,
        )
        if auth_error:
            return auth_error

        try:
            client = manager.get_client(account_id)
            raw = client.get_max_metrics(date)
            if not raw:
                return _json({"account_id": account_id, "date": date, "message": "No max metrics data"})

            results = []
            for entry in raw:
                generic = entry.get("generic") or {}
                cycling = entry.get("cycling") or {}
                results.append(_clean({
                    "vo2max_running": generic.get("vo2MaxValue"),
                    "vo2max_running_precise": generic.get("vo2MaxPreciseValue"),
                    "vo2max_date": generic.get("calendarDate"),
                    "fitness_age": generic.get("fitnessAge"),
                    "fitness_age_description": generic.get("fitnessAgeDescription"),
                    "vo2max_cycling": cycling.get("vo2MaxValue"),
                    "vo2max_cycling_precise": cycling.get("vo2MaxPreciseValue"),
                    "vo2max_cycling_date": cycling.get("calendarDate"),
                }))

            return _json({"account_id": account_id, "date": date, "metrics": results})
        except Exception as err:
            return service_error_result(str(err))

    @app.tool(
        annotations=_read_annotations("Get Endurance Score"),
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.fitness_read_scope]),
        structured_output=False,
    )
    async def get_endurance_score(
        account_id: str,
        start_date: str,
        end_date: str,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """Get endurance score trend over a date range (weekly groups).

        Returns average/max endurance score and weekly breakdown with contribution
        percentages by sport (running, cycling, etc.).
        Recommended range: 4–12 weeks.
        """

        auth_error = require_account_access(
            auth_config, authz_policy, account_id=account_id,
            required_scopes=[auth_config.fitness_read_scope], ctx=ctx,
        )
        if auth_error:
            return auth_error

        try:
            client = manager.get_client(account_id)
            raw = client.get_endurance_score(start_date, end_date)
            if not raw:
                return _json({"account_id": account_id, "message": "No endurance score data"})

            # Map Garmin group IDs to sport names
            group_names = {0: "running", 1: "cycling", 2: "swimming", 3: "other_cardio",
                           4: "walking", 5: "hiking", 6: "strength", 7: "other", 8: "rest"}

            weekly = []
            for week_start, group in sorted((raw.get("groupMap") or {}).items()):
                contributors = [
                    _clean({
                        "sport": group_names.get(c.get("group"), f"group_{c.get('group')}"),
                        "contribution_pct": round(c.get("contribution", 0), 1),
                    })
                    for c in (group.get("enduranceContributorDTOList") or [])
                ]
                weekly.append({
                    "week_start": week_start,
                    "avg_score": group.get("groupAverage"),
                    "max_score": group.get("groupMax"),
                    "contributors": contributors,
                })

            return _json({
                "account_id": account_id,
                "start_date": start_date,
                "end_date": end_date,
                "period_avg": raw.get("avg"),
                "period_max": raw.get("max"),
                "weeks": weekly,
            })
        except Exception as err:
            return service_error_result(str(err))

    @app.tool(
        annotations=_read_annotations("Get HRV Data"),
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.fitness_read_scope]),
        structured_output=False,
    )
    async def get_hrv_data(
        account_id: str,
        date: str,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """Get nightly HRV (Heart Rate Variability) data for a date.

        Returns summary stats (weekly avg, last night avg, 5-min high, status,
        baseline range) plus the full 5-minute reading timeseries.
        """

        auth_error = require_account_access(
            auth_config, authz_policy, account_id=account_id,
            required_scopes=[auth_config.fitness_read_scope], ctx=ctx,
        )
        if auth_error:
            return auth_error

        try:
            client = manager.get_client(account_id)
            raw = client.get_hrv_data(date)
            if not raw:
                return _json({"account_id": account_id, "date": date, "message": "No HRV data available for this date"})

            summary = raw.get("hrvSummary") or {}
            baseline = summary.get("baseline") or {}
            readings = [
                _clean({
                    "time_local": r.get("readingTimeLocal"),
                    "hrv_ms": r.get("hrvValue"),
                })
                for r in (raw.get("hrvReadings") or [])
            ]

            return _json(_clean({
                "account_id": account_id,
                "date": date,
                "status": summary.get("status"),
                "feedback": summary.get("feedbackPhrase"),
                "last_night_avg_ms": summary.get("lastNightAvg"),
                "last_night_5min_high_ms": summary.get("lastNight5MinHigh"),
                "weekly_avg_ms": summary.get("weeklyAvg"),
                "baseline_low_upper_ms": baseline.get("lowUpper"),
                "baseline_balanced_low_ms": baseline.get("balancedLow"),
                "baseline_balanced_upper_ms": baseline.get("balancedUpper"),
                "reading_count": len(readings),
                "readings": readings,
            }))
        except Exception as err:
            return service_error_result(str(err))

    # -----------------------------------------------------------------------
    # P2 Tools
    # -----------------------------------------------------------------------

    @app.tool(
        annotations=_read_annotations("Get Sleep Data"),
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.fitness_read_scope]),
        structured_output=False,
    )
    async def get_sleep_data(
        account_id: str,
        date: str,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """Get sleep data for a date: stages (deep/light/REM/awake), sleep score, and breath tracking.

        Returns daily sleep summary and per-stage duration breakdown.
        """

        auth_error = require_account_access(
            auth_config, authz_policy, account_id=account_id,
            required_scopes=[auth_config.fitness_read_scope], ctx=ctx,
        )
        if auth_error:
            return auth_error

        try:
            client = manager.get_client(account_id)
            raw = client.get_sleep_data(date)
            if not raw:
                return _json({"account_id": account_id, "date": date, "message": "No sleep data available"})

            dto = raw.get("dailySleepDTO") or {}
            scores = dto.get("sleepScores") or {}

            # Stage seconds
            stages = _clean({
                "deep_seconds": dto.get("deepSleepSeconds"),
                "light_seconds": dto.get("lightSleepSeconds"),
                "rem_seconds": dto.get("remSleepSeconds"),
                "awake_seconds": dto.get("awakeSleepSeconds"),
                "total_sleep_seconds": dto.get("sleepTimeSeconds"),
                "total_duration_seconds": dto.get("totalSleepSeconds") or dto.get("sleepTimeSeconds"),
            })

            # Score block (structure varies by firmware)
            score_summary = None
            if isinstance(scores, dict) and "overall" in scores:
                score_summary = _clean({
                    "overall": (scores.get("overall") or {}).get("value"),
                    "quality": (scores.get("qualityOfSleep") or {}).get("value"),
                    "recovery": (scores.get("recoveryIndex") or {}).get("value"),
                    "rem_percentage": (scores.get("remPercentage") or {}).get("value"),
                    "restlessness": (scores.get("restlessness") or {}).get("value"),
                })

            # Breathing disturbances summary
            breathing = _clean({
                "avg_waking_respiration": dto.get("avgWakingRespirationValue"),
                "avg_sleep_respiration": dto.get("avgSleepingRespirationValue"),
                "highest_respiration": dto.get("highestRespirationValue"),
                "lowest_respiration": dto.get("lowestRespirationValue"),
            })

            return _json(_clean({
                "account_id": account_id,
                "date": date,
                "sleep_start_local": dto.get("sleepStartTimestampLocal"),
                "sleep_end_local": dto.get("sleepEndTimestampLocal"),
                "stages": stages,
                "score": score_summary,
                "breathing": breathing if any(breathing.values()) else None,
                "avg_spo2": dto.get("averageSpO2Value"),
                "avg_heart_rate": dto.get("avgHeartRate"),
                "resting_heart_rate": raw.get("restingHeartRate"),
                "avg_overnight_hrv_ms": raw.get("avgOvernightHrv"),
                "hrv_status": raw.get("hrvStatus"),
                "avg_sleep_stress": dto.get("avgSleepStress"),
            }))
        except Exception as err:
            return service_error_result(str(err))

    @app.tool(
        annotations=_read_annotations("Get Full-Day Heart Rate Timeseries"),
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.fitness_read_scope]),
        structured_output=False,
    )
    async def get_heart_rates(
        account_id: str,
        date: str,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """Get full-day heart rate timeseries for a date (15-minute interval readings).

        Returns resting HR, max/min for the day, and the per-interval readings array.
        Each reading is [timestamp_ms, hr_bpm] or null if no data.
        """

        auth_error = require_account_access(
            auth_config, authz_policy, account_id=account_id,
            required_scopes=[auth_config.fitness_read_scope], ctx=ctx,
        )
        if auth_error:
            return auth_error

        try:
            client = manager.get_client(account_id)
            raw = client.get_heart_rates(date)
            if not raw:
                return _json({"account_id": account_id, "date": date, "message": "No heart rate data available"})

            values = raw.get("heartRateValues") or raw.get("heartRateReadings") or []
            # Filter out null readings for compactness
            valid = [v for v in values if v is not None and (isinstance(v, list) and v[1] is not None)]

            return _json(_clean({
                "account_id": account_id,
                "date": date,
                "resting_hr_bpm": raw.get("restingHeartRate"),
                "max_hr_bpm": raw.get("maxHeartRate"),
                "min_hr_bpm": raw.get("minHeartRate"),
                "total_readings": len(values),
                "valid_readings": len(valid),
                "readings": valid,
                "legend": {"readings": "[timestamp_ms, hr_bpm]"},
            }))
        except Exception as err:
            return service_error_result(str(err))

    @app.tool(
        annotations=_read_annotations("Get Stress Level Timeseries"),
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.fitness_read_scope]),
        structured_output=False,
    )
    async def get_stress_data(
        account_id: str,
        date: str,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """Get stress level timeseries for a date (3-minute interval readings).

        Returns average stress level for the day and the per-interval readings array.
        Each reading is [timestamp_ms, stress_level] where -1 = activity/no data,
        0–25 = rest, 26–50 = low stress, 51–75 = medium, 76–100 = high stress.
        """

        auth_error = require_account_access(
            auth_config, authz_policy, account_id=account_id,
            required_scopes=[auth_config.fitness_read_scope], ctx=ctx,
        )
        if auth_error:
            return auth_error

        try:
            client = manager.get_client(account_id)
            raw = client.get_stress_data(date)
            if not raw:
                return _json({"account_id": account_id, "date": date, "message": "No stress data available"})

            values = raw.get("stressValuesArray") or []
            # Keep only readings with non-negative stress (skip unmeasured/activity intervals)
            measured = [v for v in values if v is not None and isinstance(v, list) and len(v) >= 2 and v[1] >= 0]

            return _json(_clean({
                "account_id": account_id,
                "date": date,
                "avg_stress_level": raw.get("avgStressLevel"),
                "max_stress_level": raw.get("maxStressLevel"),
                "total_readings": len(values),
                "measured_readings": len(measured),
                "stress_qualifier": raw.get("stressQualifier"),
                "readings": measured,
                "legend": {
                    "readings": "[timestamp_ms, stress_level]",
                    "stress_level": "0-25=rest, 26-50=low, 51-75=medium, 76-100=high, -1=activity/no data",
                },
            }))
        except Exception as err:
            return service_error_result(str(err))

    @app.tool(
        annotations=_read_annotations("Get Respiration Rate Timeseries"),
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.fitness_read_scope]),
        structured_output=False,
    )
    async def get_respiration_data(
        account_id: str,
        date: str,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """Get respiration rate timeseries for a date (breaths per minute).

        Returns waking/sleeping averages and per-interval readings.
        Each reading is [timestamp_ms, breaths_per_minute].
        """

        auth_error = require_account_access(
            auth_config, authz_policy, account_id=account_id,
            required_scopes=[auth_config.fitness_read_scope], ctx=ctx,
        )
        if auth_error:
            return auth_error

        try:
            client = manager.get_client(account_id)
            raw = client.get_respiration_data(date)
            if not raw:
                return _json({"account_id": account_id, "date": date, "message": "No respiration data available"})

            values = (
                raw.get("respirationValues")
                or raw.get("respirationValuesArray")
                or raw.get("respirationReadings")
                or []
            )
            valid = [v for v in values if v is not None and isinstance(v, list) and len(v) >= 2 and v[1] is not None]

            return _json(_clean({
                "account_id": account_id,
                "date": date,
                "avg_waking_brpm": raw.get("avgWakingRespirationValue"),
                "avg_sleeping_brpm": raw.get("avgSleepingRespirationValue"),
                "highest_brpm": raw.get("highestRespirationValue"),
                "lowest_brpm": raw.get("lowestRespirationValue"),
                "valid_readings": len(valid),
                "readings": valid,
                "legend": {"readings": "[timestamp_ms, breaths_per_minute]"},
            }))
        except Exception as err:
            return service_error_result(str(err))

    @app.tool(
        annotations=_read_annotations("Get SpO2 (Blood Oxygen) Data"),
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.fitness_read_scope]),
        structured_output=False,
    )
    async def get_spo2_data(
        account_id: str,
        date: str,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """Get blood oxygen saturation (SpO2) data for a date.

        Returns sleep-period average SpO2 and hourly averages throughout the day.
        SpO2 is measured as a percentage (normal range: 95–100%).
        """

        auth_error = require_account_access(
            auth_config, authz_policy, account_id=account_id,
            required_scopes=[auth_config.fitness_read_scope], ctx=ctx,
        )
        if auth_error:
            return auth_error

        try:
            client = manager.get_client(account_id)
            raw = client.get_spo2_data(date)
            if not raw:
                return _json({"account_id": account_id, "date": date, "message": "No SpO2 data available"})

            sleep_summary = raw.get("SpO2SleepSummary") or {}
            hourly = raw.get("spO2HourlyAverages") or []
            # Filter nulls from hourly list
            valid_hourly = [v for v in hourly if v is not None]
            continuous = raw.get("continuousReadings") or []

            return _json(_clean({
                "account_id": account_id,
                "date": date,
                "avg_sleep_spo2_pct": sleep_summary.get("averageSpO2"),
                "lowest_sleep_spo2_pct": sleep_summary.get("lowestSpO2"),
                "hourly_readings": len(valid_hourly),
                "hourly_averages": valid_hourly,
                "continuous_reading_count": len(continuous),
                "legend": {
                    "hourly_averages": "[timestamp_ms, spo2_pct]",
                    "normal_range": "95-100%",
                },
            }))
        except Exception as err:
            return service_error_result(str(err))

    @app.tool(
        annotations=_read_annotations("Get Body Composition"),
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.fitness_read_scope]),
        structured_output=False,
    )
    async def get_body_composition(
        account_id: str,
        start_date: str,
        end_date: str | None = None,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """Get body composition measurements from a Garmin Index scale.

        Returns weight, body fat %, muscle mass, bone mass, body water %,
        BMI, and visceral fat for each weigh-in in the date range.

        start_date: YYYY-MM-DD (required)
        end_date:   YYYY-MM-DD (optional; defaults to start_date for a single day)
        """
        auth_error = require_account_access(
            auth_config, authz_policy, account_id=account_id,
            required_scopes=[auth_config.fitness_read_scope], ctx=ctx,
        )
        if auth_error:
            return auth_error

        if end_date is None:
            end_date = start_date

        try:
            client = manager.get_client(account_id)
            raw = client.get_body_composition(start_date, end_date)
            if not raw:
                return _json({"account_id": account_id, "start_date": start_date,
                               "end_date": end_date, "message": "No body composition data available"})

            entries = raw.get("dateWeightList") or []
            parsed = []
            for e in entries:
                parsed.append(_clean({
                    "date":            e.get("calendarDate"),
                    "weight_kg":       round(e["weight"] / 1000, 2) if e.get("weight") else None,
                    "bmi":             e.get("bmi"),
                    "body_fat_pct":    e.get("bodyFat"),
                    "body_water_pct":  e.get("bodyWater"),
                    "muscle_mass_kg":  round(e["muscleMass"] / 1000, 2) if e.get("muscleMass") else None,
                    "bone_mass_kg":    round(e["boneMass"] / 1000, 2) if e.get("boneMass") else None,
                    "visceral_fat":    e.get("visceralFat"),
                    "metabolic_age":   e.get("metabolicAge"),
                    "source":          e.get("sourceType"),
                }))

            avg = raw.get("totalAverage") or {}
            return _json(_clean({
                "account_id":  account_id,
                "start_date":  start_date,
                "end_date":    end_date,
                "entries":     parsed,
                "average": _clean({
                    "weight_kg":      round(avg["weight"] / 1000, 2) if avg.get("weight") else None,
                    "bmi":            avg.get("bmi"),
                    "body_fat_pct":   avg.get("bodyFat"),
                    "body_water_pct": avg.get("bodyWater"),
                    "muscle_mass_kg": round(avg["muscleMass"] / 1000, 2) if avg.get("muscleMass") else None,
                    "bone_mass_kg":   round(avg["boneMass"] / 1000, 2) if avg.get("boneMass") else None,
                }),
            }))
        except Exception as err:
            return service_error_result(str(err))

    # -----------------------------------------------------------------------
    # Chart Tools
    # -----------------------------------------------------------------------

    @app.tool(
        annotations={
            "title": "Generate Activity Performance Chart",
            "readOnlyHint": True,
            "idempotentHint": True,
            "openWorldHint": False,
            "destructiveHint": False,
        },
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.fitness_read_scope]),
        structured_output=False,
    )
    async def generate_activity_chart(
        account_id: str,
        activity_id: int,
        max_datapoints: int = 500,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """Generate a 6-panel performance chart for one activity and return it as a PNG image.

        Panels (all plotted over distance):
          1. Heart Rate (bpm) with zone reference lines
          2. Pace (min/km, inverted axis)
          3. Cadence (spm) with 180 spm reference
          4. Running Power (W)
          5. Stride Length (cm)
          6. Ground Contact Time (ms) + Vertical Oscillation (cm)

        Returns an inline PNG image. If a required metric is absent the panel is omitted.
        """

        auth_error = require_account_access(
            auth_config, authz_policy, account_id=account_id,
            required_scopes=[auth_config.fitness_read_scope], ctx=ctx,
        )
        if auth_error:
            return auth_error

        try:
            client = manager.get_client(account_id)

            # ── fetch timeseries ──────────────────────────────────────────
            raw = client.get_activity_details(activity_id, maxchart=max_datapoints, maxpoly=0)
            if not raw:
                return _json({"account_id": account_id, "activity_id": activity_id,
                              "message": "No detail data available"})

            descriptors = raw.get("metricDescriptors", [])
            key_index = {d["key"]: i for i, d in enumerate(descriptors)}

            def _get(row: list, key: str):
                idx = key_index.get(key)
                return row[idx] if idx is not None else None

            def _r(v, digits=1):
                return round(v, digits) if v else None

            ts = []
            for item in raw.get("activityDetailMetrics", []):
                m = item["metrics"]
                cadence = _get(m, "directDoubleCadence") or ((_get(m, "directRunCadence") or 0) * 2 or None)
                ts.append({
                    "d": _get(m, "sumDistance"),
                    "hr": _get(m, "directHeartRate"),
                    "spd": _get(m, "directSpeed"),
                    "cad": cadence,
                    "pwr": _get(m, "directPower"),
                    "stride": _get(m, "directStrideLength"),
                    "gct": _get(m, "directGroundContactTime"),
                    "vo": _get(m, "directVerticalOscillation"),
                })

            def col(xkey: str, ykey: str, yfn=None):
                """Return (x_km_list, y_list) for non-null pairs."""
                pairs = [
                    (p[xkey] / 1000, yfn(p[ykey]) if yfn else p[ykey])
                    for p in ts
                    if p.get(xkey) is not None and p.get(ykey) is not None
                ]
                return [x for x, y in pairs], [y for x, y in pairs]

            # ── fetch activity summary for title ──────────────────────────
            act = client.get_activity(activity_id) or {}
            summary = act.get("summaryDTO", {})
            name = act.get("activityName", f"Activity {activity_id}")
            dist_km = (summary.get("distance") or 0) / 1000
            dur_min = int((summary.get("duration") or 0) / 60)
            date_str = (summary.get("startTimeLocal") or "")[:10]
            title = f"{name}  |  {date_str}  |  {dist_km:.1f} km  |  {dur_min} min"

            # ── build figure ──────────────────────────────────────────────
            fig = plt.figure(figsize=(14, 20))
            fig.suptitle(title, fontsize=13, fontweight="bold", y=0.99)
            gs = gridspec.GridSpec(6, 1, figure=fig, hspace=0.5)

            def _stat(yd):
                if not yd:
                    return "no data"
                return f"avg {sum(yd)/len(yd):.1f}  max {max(yd):.1f}  min {min(yd):.1f}"

            def plot_panel(ax, xd, yd, label, unit, color, fill=False, hlines=None, ylim=None, invert=False):
                if not xd:
                    ax.text(0.5, 0.5, f"{label}: no data", ha="center", va="center",
                            transform=ax.transAxes, color="gray")
                    return
                ax.plot(xd, yd, color=color, linewidth=1.3, alpha=0.9)
                if fill:
                    ax.fill_between(xd, yd, alpha=0.18, color=color)
                if hlines:
                    for v, ls in hlines:
                        ax.axhline(v, color="gray", linestyle=ls, linewidth=0.8, alpha=0.5)
                if ylim:
                    ax.set_ylim(*ylim)
                if invert:
                    ax.invert_yaxis()
                ax.set_ylabel(f"{label} ({unit})", fontsize=9)
                ax.grid(True, alpha=0.3)
                ax.tick_params(labelsize=8)
                ax.set_title(_stat(yd), fontsize=8, loc="right", color="#555")

            # 1. Heart Rate
            ax1 = fig.add_subplot(gs[0])
            xd, yd = col("d", "hr")
            plot_panel(ax1, xd, yd, "Heart Rate", "bpm", "#e74c3c", fill=True,
                       hlines=[(115, "--"), (148, "--"), (162, "--")], ylim=(50, 185))
            if xd:
                for val, label in [(115, "Z2"), (148, "Z4"), (162, "Z5")]:
                    ax1.annotate(label, xy=(0.01, val), xycoords=("axes fraction", "data"),
                                 fontsize=7, color="gray", va="bottom")

            # 2. Pace
            ax2 = fig.add_subplot(gs[1])
            xd2, yd2 = col("d", "spd")
            pace_pairs = [(x, 16.667 / v) for x, v in zip(xd2, yd2) if v > 0.5 and 16.667 / v < 12]
            xp, yp = [x for x, y in pace_pairs], [y for x, y in pace_pairs]
            plot_panel(ax2, xp, yp, "Pace", "min/km", "#2980b9", fill=True, invert=True)

            # 3. Cadence
            ax3 = fig.add_subplot(gs[2])
            xd, yd = col("d", "cad")
            plot_panel(ax3, xd, yd, "Cadence", "spm", "#27ae60",
                       hlines=[(180, "--")], ylim=(80, 210))

            # 4. Running Power
            ax4 = fig.add_subplot(gs[3])
            xd, yd = col("d", "pwr")
            plot_panel(ax4, xd, yd, "Running Power", "W", "#8e44ad", fill=True)

            # 5. Stride Length
            ax5 = fig.add_subplot(gs[4])
            xd, yd = col("d", "stride")
            plot_panel(ax5, xd, yd, "Stride Length", "cm", "#e67e22")

            # 6. GCT + Vertical Oscillation (dual axis)
            ax6 = fig.add_subplot(gs[5])
            xd_gct, yd_gct = col("d", "gct")
            xd_vo, yd_vo = col("d", "vo")
            if xd_gct:
                ax6.plot(xd_gct, yd_gct, color="#16a085", linewidth=1.3, label="GCT (ms)")
                ax6.set_ylabel("Ground Contact (ms)", fontsize=9, color="#16a085")
                ax6.tick_params(axis="y", labelcolor="#16a085", labelsize=8)
                ax6.set_title(f"GCT {_stat(yd_gct)}", fontsize=8, loc="right", color="#555")
            if xd_vo:
                ax6b = ax6.twinx()
                ax6b.plot(xd_vo, yd_vo, color="#c0392b", linewidth=1.3,
                          linestyle="--", label="Vert. Osc. (cm)", alpha=0.85)
                ax6b.set_ylabel("Vertical Oscillation (cm)", fontsize=9, color="#c0392b")
                ax6b.tick_params(axis="y", labelcolor="#c0392b", labelsize=8)
            ax6.grid(True, alpha=0.3)
            ax6.tick_params(axis="x", labelsize=8)
            ax6.set_xlabel("Distance (km)", fontsize=9)

            # hide x-tick labels on all but last panel
            for ax in [ax1, ax2, ax3, ax4, ax5]:
                ax.set_xticklabels([])

            # ── render to PNG bytes ───────────────────────────────────────
            buf = io.BytesIO()
            plt.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
            plt.close(fig)
            buf.seek(0)
            png_b64 = base64.b64encode(buf.read()).decode()

            return CallToolResult(content=[
                ImageContent(type="image", data=png_b64, mimeType="image/png")
            ])

        except Exception as err:
            return service_error_result(str(err))

    @app.tool(
        annotations=_read_annotations("Get Body Battery Data"),
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.fitness_read_scope]),
        structured_output=False,
    )
    async def get_body_battery(
        account_id: str,
        date: str,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """Get Body Battery timeseries and events for a date.

        Returns charged/drained totals, the full BB value array
        ([timestamp_ms, bb_value]), and activity/sleep events that
        caused significant changes.
        """

        auth_error = require_account_access(
            auth_config, authz_policy, account_id=account_id,
            required_scopes=[auth_config.fitness_read_scope], ctx=ctx,
        )
        if auth_error:
            return auth_error

        try:
            client = manager.get_client(account_id)
            raw = client.get_body_battery(date)
            if not raw:
                return _json({"account_id": account_id, "date": date,
                              "message": "No Body Battery data available"})

            day = raw[0]
            bb_arr = day.get("bodyBatteryValuesArray") or []
            # Each entry: [timestamp_ms, "MEASURED"/"PROJECTED", bb_value, stress_float]
            readings = [
                {"t": v[0], "bb": v[2]}
                for v in bb_arr
                if len(v) >= 3 and v[2] is not None
            ]

            events = [
                _clean({
                    "type": e.get("eventType"),
                    "start_gmt": e.get("eventStartTimeGmt"),
                    "duration_min": round(e.get("durationInMilliseconds", 0) / 60000, 1),
                    "bb_impact": e.get("bodyBatteryImpact"),
                    "feedback": e.get("shortFeedback"),
                })
                for e in (day.get("bodyBatteryActivityEvent") or [])
            ]

            return _json(_clean({
                "account_id": account_id,
                "date": date,
                "charged": day.get("charged"),
                "drained": day.get("drained"),
                "reading_count": len(readings),
                "readings": readings,
                "events": events,
                "legend": {"readings": "[{t: timestamp_ms, bb: body_battery_0-100}]"},
            }))
        except Exception as err:
            return service_error_result(str(err))

    @app.tool(
        annotations={
            "title": "Generate Daily Wellness Chart",
            "readOnlyHint": True,
            "idempotentHint": True,
            "openWorldHint": False,
            "destructiveHint": False,
        },
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.fitness_read_scope]),
        structured_output=False,
    )
    async def generate_daily_wellness_chart(
        account_id: str,
        date: str,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """Generate a daily wellness chart as a PNG image.

        Two panels (x-axis = local time):
          1. Body Battery — line chart with fill; green = charging, red = draining
          2. Stress — bar chart; blue = rest, orange = medium/high stress, grey = activity

        Activity and sleep event markers are shown as vertical dashed lines.
        """

        auth_error = require_account_access(
            auth_config, authz_policy, account_id=account_id,
            required_scopes=[auth_config.fitness_read_scope], ctx=ctx,
        )
        if auth_error:
            return auth_error

        try:
            import datetime as dt

            client = manager.get_client(account_id)

            # get_all_day_stress returns both BB and stress in one call
            raw = client.get_all_day_stress(date)
            bb_raw = client.get_body_battery(date)

            if not raw:
                return _json({"account_id": account_id, "date": date,
                              "message": "No wellness data available"})

            # ── parse timestamps to local datetime ────────────────────────
            def ts_to_local(ts_ms: int):
                return dt.datetime.fromtimestamp(ts_ms / 1000)

            bb_arr = raw.get("bodyBatteryValuesArray") or []
            st_arr = raw.get("stressValuesArray") or []

            bb_times = [ts_to_local(v[0]) for v in bb_arr if len(v) >= 3 and v[2] is not None]
            bb_vals  = [v[2] for v in bb_arr if len(v) >= 3 and v[2] is not None]

            st_times = [ts_to_local(v[0]) for v in st_arr if len(v) >= 2 and v[1] >= 0]
            st_vals  = [v[1] for v in st_arr if len(v) >= 2 and v[1] >= 0]

            # activity/sleep events for vertical markers
            events = []
            if bb_raw:
                for e in (bb_raw[0].get("bodyBatteryActivityEvent") or []):
                    gmt_str = e.get("eventStartTimeGmt", "").replace(".0", "")
                    try:
                        offset_ms = e.get("timezoneOffset", 0)
                        gmt_dt = dt.datetime.strptime(gmt_str, "%Y-%m-%dT%H:%M:%S")
                        local_dt = gmt_dt + dt.timedelta(milliseconds=offset_ms)
                        events.append({
                            "time": local_dt,
                            "type": e.get("eventType", ""),
                            "impact": e.get("bodyBatteryImpact", 0),
                        })
                    except Exception:
                        pass

            # ── figure ────────────────────────────────────────────────────
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True,
                                           gridspec_kw={"height_ratios": [2, 1]})
            fig.suptitle(f"Daily Wellness — {date}  |  {account_id}", fontsize=13,
                         fontweight="bold")
            fig.subplots_adjust(hspace=0.08)

            # ── Panel 1: Body Battery ─────────────────────────────────────
            if bb_times and bb_vals:
                # colour segments: green when rising, red when falling
                for i in range(1, len(bb_times)):
                    color = "#2ecc71" if bb_vals[i] >= bb_vals[i - 1] else "#e74c3c"
                    ax1.fill_between(
                        [bb_times[i - 1], bb_times[i]],
                        [bb_vals[i - 1], bb_vals[i]],
                        alpha=0.4, color=color, linewidth=0,
                    )
                ax1.plot(bb_times, bb_vals, color="#2c3e50", linewidth=1.5, zorder=3)
                ax1.set_ylim(0, 105)
                ax1.set_ylabel("Body Battery", fontsize=10)
                for lv in [25, 50, 75]:
                    ax1.axhline(lv, color="gray", linestyle=":", linewidth=0.7, alpha=0.5)
                charged = raw.get("charged") or (bb_raw[0].get("charged") if bb_raw else None)
                drained = raw.get("drained") or (bb_raw[0].get("drained") if bb_raw else None)
                info = []
                if charged: info.append(f"+{charged} charged")
                if drained: info.append(f"-{drained} drained")
                if info:
                    ax1.set_title("  ".join(info), fontsize=9, loc="right", color="#555")

            # ── Panel 2: Stress ───────────────────────────────────────────
            if st_times and st_vals:
                # colour: blue=rest(0-25), orange=low(26-50), red=high(51-100)
                colors = []
                for v in st_vals:
                    if v <= 25:
                        colors.append("#3498db")
                    elif v <= 50:
                        colors.append("#f39c12")
                    else:
                        colors.append("#e74c3c")

                # bar width ≈ interval between readings
                interval = (st_times[1] - st_times[0]).total_seconds() / 86400 if len(st_times) > 1 else 1 / 480
                ax2.bar(st_times, st_vals, width=interval, color=colors, alpha=0.8, align="edge")
                ax2.set_ylim(0, 105)
                ax2.set_ylabel("Stress Level", fontsize=10)
                ax2.axhline(25, color="#3498db", linestyle=":", linewidth=0.7, alpha=0.5)
                ax2.axhline(50, color="#f39c12", linestyle=":", linewidth=0.7, alpha=0.5)
                avg_st = raw.get("avgStressLevel")
                max_st = raw.get("maxStressLevel")
                if avg_st:
                    ax2.set_title(f"avg {avg_st}  max {max_st}", fontsize=9, loc="right", color="#555")

                # legend
                from matplotlib.patches import Patch
                legend_elements = [
                    Patch(facecolor="#3498db", alpha=0.8, label="Rest (0-25)"),
                    Patch(facecolor="#f39c12", alpha=0.8, label="Low stress (26-50)"),
                    Patch(facecolor="#e74c3c", alpha=0.8, label="High stress (51+)"),
                ]
                ax2.legend(handles=legend_elements, fontsize=7, loc="upper right")

            # ── Event markers on both panels ──────────────────────────────
            for e in events:
                label = e["type"].title()
                impact_str = f"  {e['impact']:+d}" if e["impact"] else ""
                for ax in [ax1, ax2]:
                    ax.axvline(e["time"], color="#8e44ad", linestyle="--",
                               linewidth=1.0, alpha=0.6)
                ax1.annotate(f"{label}{impact_str}",
                             xy=(e["time"], 100), fontsize=7, color="#8e44ad",
                             rotation=90, va="top", ha="right")

            # ── x-axis formatting ─────────────────────────────────────────
            import matplotlib.dates as mdates
            ax2.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
            ax2.xaxis.set_major_locator(mdates.HourLocator(interval=2))
            plt.setp(ax2.xaxis.get_majorticklabels(), rotation=0, fontsize=8)
            ax2.set_xlabel("Local Time", fontsize=9)
            for ax in [ax1, ax2]:
                ax.grid(True, alpha=0.25)
                ax.tick_params(axis="y", labelsize=8)

            buf = io.BytesIO()
            plt.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
            plt.close(fig)
            buf.seek(0)
            png_b64 = base64.b64encode(buf.read()).decode()

            return CallToolResult(content=[
                ImageContent(type="image", data=png_b64, mimeType="image/png")
            ])

        except Exception as err:
            return service_error_result(str(err))

    # ── Workout creation ──────────────────────────────────────────────────

    _SPORT_TYPES = {
        "cycling": {"sportTypeId": 2, "sportTypeKey": "cycling", "displayOrder": 2},
        "running": {"sportTypeId": 1, "sportTypeKey": "running", "displayOrder": 1},
        "swimming": {"sportTypeId": 5, "sportTypeKey": "swimming", "displayOrder": 5},
    }
    _STEP_TYPES = {
        "warmup":   {"stepTypeId": 1, "stepTypeKey": "warmup",   "displayOrder": 1},
        "cooldown": {"stepTypeId": 2, "stepTypeKey": "cooldown", "displayOrder": 2},
        "interval": {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3},
        "recovery": {"stepTypeId": 4, "stepTypeKey": "recovery", "displayOrder": 4},
        "rest":     {"stepTypeId": 5, "stepTypeKey": "rest",     "displayOrder": 5},
    }
    _END_CONDITION_TIME = {
        "conditionTypeId": 2,
        "conditionTypeKey": "time",
        "displayOrder": 2,
        "displayable": True,
    }
    _TARGET_NO_TARGET = {
        "workoutTargetTypeId": 1,
        "workoutTargetTypeKey": "no.target",
        "displayOrder": 1,
    }
    # Cycling-specific target type IDs (differ from running)
    _TARGET_POWER = {
        "workoutTargetTypeId": 2,
        "workoutTargetTypeKey": "power.zone",
        "displayOrder": 2,
    }
    _TARGET_HR = {
        "workoutTargetTypeId": 4,
        "workoutTargetTypeKey": "heart.rate.zone",
        "displayOrder": 4,
    }

    @app.tool(
        annotations={
            "title": "Create Garmin Workout",
            "readOnlyHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
            "destructiveHint": False,
        },
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.fitness_read_scope]),
        structured_output=False,
    )
    async def create_workout(
        account_id: str,
        name: str,
        sport: str,
        steps_json: str,
        description: str = "",
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """Create a structured workout on Garmin Connect and return the workout ID.

        sport: "cycling" | "running" | "swimming"

        steps_json: JSON array of step objects. Each step:
          {
            "type": "warmup" | "interval" | "recovery" | "cooldown" | "rest",
            "duration_secs": <int>,
            "power_low": <float, optional — watts>,
            "power_high": <float, optional — watts>,
            "hr_low": <float, optional — bpm>,
            "hr_high": <float, optional — bpm>
          }

        Example steps_json for a 4h Z2 ride:
          [
            {"type": "warmup",   "duration_secs": 1200, "power_low": 100, "power_high": 130},
            {"type": "interval", "duration_secs": 2400, "power_low": 140, "power_high": 145},
            {"type": "interval", "duration_secs": 3600, "power_low": 155, "power_high": 165},
            {"type": "cooldown", "duration_secs": 1200, "power_low": 100, "power_high": 130}
          ]
        """

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
            import json as _json_mod

            sport_key = sport.lower()
            if sport_key not in _SPORT_TYPES:
                return service_error_result(
                    f"Unknown sport '{sport}'. Use: {', '.join(_SPORT_TYPES)}"
                )
            sport_type = _SPORT_TYPES[sport_key]

            raw_steps = _json_mod.loads(steps_json)
            if not isinstance(raw_steps, list) or not raw_steps:
                return service_error_result("steps_json must be a non-empty JSON array")

            workout_steps = []
            total_secs = 0
            for i, s in enumerate(raw_steps, start=1):
                step_key = str(s.get("type", "interval")).lower()
                if step_key not in _STEP_TYPES:
                    return service_error_result(
                        f"Step {i}: unknown type '{step_key}'. Use: {', '.join(_STEP_TYPES)}"
                    )
                dur = float(s.get("duration_secs", 0))
                if dur <= 0:
                    return service_error_result(f"Step {i}: duration_secs must be > 0")
                total_secs += int(dur)

                has_power = "power_low" in s or "power_high" in s
                has_hr = "hr_low" in s or "hr_high" in s

                if has_power:
                    target_type = _TARGET_POWER
                    target_low = float(s.get("power_low", 0))
                    target_high = float(s.get("power_high", target_low))
                elif has_hr:
                    target_type = _TARGET_HR
                    target_low = float(s.get("hr_low", 0))
                    target_high = float(s.get("hr_high", target_low))
                else:
                    target_type = _TARGET_NO_TARGET
                    target_low = None
                    target_high = None

                step: dict[str, Any] = {
                    "type": "ExecutableStepDTO",
                    "stepOrder": i,
                    "stepType": _STEP_TYPES[step_key],
                    "endCondition": _END_CONDITION_TIME,
                    "endConditionValue": dur,
                    "targetType": target_type,
                }
                if target_low is not None:
                    step["targetValueOne"] = target_low
                    step["targetValueTwo"] = target_high

                workout_steps.append(step)

            workout_payload: dict[str, Any] = {
                "workoutName": name,
                "description": description,
                "estimatedDurationInSecs": total_secs,
                "sportType": sport_type,
                "workoutSegments": [
                    {
                        "segmentOrder": 1,
                        "sportType": sport_type,
                        "workoutSteps": workout_steps,
                    }
                ],
            }

            client = manager.get_client(account_id)
            result = client.upload_workout(workout_payload)
            return _json({"account_id": account_id, "workout": result})  # outer _json helper

        except Exception as err:
            return service_error_result(str(err))

    @app.tool(
        annotations=_read_annotations("List Garmin Workouts"),
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.fitness_read_scope]),
        structured_output=False,
    )
    async def list_workouts(
        account_id: str,
        limit: int = 20,
        start: int = 0,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """List saved workouts on Garmin Connect.

        Returns workoutId, workoutName, sport, estimatedDurationInSecs, createdDate.
        Use limit/start for pagination.
        """
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
            workouts = client.get_workouts(start, limit)
            summary = [
                {
                    "workoutId": w.get("workoutId"),
                    "workoutName": w.get("workoutName"),
                    "sport": w.get("sportType", {}).get("sportTypeKey"),
                    "estimatedDurationInSecs": w.get("estimatedDurationInSecs"),
                    "createdDate": w.get("createdDate"),
                }
                for w in (workouts or [])
            ]
            return _json({"account_id": account_id, "count": len(summary), "workouts": summary})
        except Exception as err:
            return service_error_result(str(err))

    @app.tool(
        annotations=_read_annotations("Get Garmin Workout Detail"),
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.fitness_read_scope]),
        structured_output=False,
    )
    async def get_workout(
        account_id: str,
        workout_id: int,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """Get full detail of a saved Garmin workout by ID, including all steps and targets."""
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
            result = client.get_workout_by_id(workout_id)
            return _json({"account_id": account_id, "workout": result})
        except Exception as err:
            return service_error_result(str(err))

    @app.tool(
        annotations={
            "title": "Delete Garmin Workout",
            "readOnlyHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
            "destructiveHint": True,
        },
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.fitness_read_scope]),
        structured_output=False,
    )
    async def delete_workout(
        account_id: str,
        workout_id: int,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """Delete a saved workout from Garmin Connect by ID. Irreversible."""
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
            resp = with_auth_retry(
                manager, account_id,
                lambda c: c.garth.request(
                    "DELETE", "connectapi", f"/workout-service/workout/{workout_id}", api=True
                ),
            )
            return _json({
                "account_id": account_id,
                "workout_id": workout_id,
                "deleted": resp.status_code == 204,
                "status_code": resp.status_code,
            })
        except Exception as err:
            return service_error_result(str(err))

    @app.tool(
        annotations={
            "title": "Schedule Garmin Workout",
            "readOnlyHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
            "destructiveHint": False,
        },
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.fitness_read_scope]),
        structured_output=False,
    )
    async def schedule_workout(
        account_id: str,
        workout_id: int,
        date: str,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """Schedule a saved workout to a specific calendar date on Garmin Connect.

        date: ISO format YYYY-MM-DD
        The workout will appear in the Garmin Connect calendar and sync to the device.
        """
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
            resp = with_auth_retry(
                manager, account_id,
                lambda c: c.garth.post(
                    "connectapi",
                    f"/workout-service/schedule/{workout_id}",
                    json={"date": date},
                    api=True,
                ),
            )
            return _json({
                "account_id": account_id,
                "workout_id": workout_id,
                "scheduled_date": date,
                "result": resp.json() if resp.content else {"status": "scheduled"},
            })
        except Exception as err:
            return service_error_result(str(err))

    return app
