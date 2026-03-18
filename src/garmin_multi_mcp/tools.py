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

    # -----------------------------------------------------------------------
    # P1 Tools
    # -----------------------------------------------------------------------

    @app.tool(
        annotations=_read_annotations("Get Activity Time-Series Details"),
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.fitness_read_scope]),
        structured_output=False,
    )
    async def get_activity_details(
        account_id: str,
        activity_id: int,
        max_datapoints: int = 200,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """Get time-series for one activity: heart rate, cadence, pace, power, stride length, elevation.

        Returns sampled data points with named metric fields.
        max_datapoints controls sampling density (default 200, max ~2000).
        For a full-resolution dump use max_datapoints=2000 (response will be large).
        """

        auth_error = require_account_access(
            auth_config, authz_policy, account_id=account_id,
            required_scopes=[auth_config.fitness_read_scope], ctx=ctx,
        )
        if auth_error:
            return auth_error

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
                points.append(_clean({
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
                }))

            legend = {
                "t": "timestamp_ms", "s": "elapsed_seconds", "d": "distance_meters",
                "hr": "heart_rate_bpm", "cad": "cadence_spm", "spd": "speed_mps",
                "spd_ga": "grade_adjusted_speed_mps", "ele": "elevation_m",
                "pwr": "power_watts", "stride": "stride_length_m",
                "vo_mm": "vertical_oscillation_mm", "gct_ms": "ground_contact_time_ms",
                "vr_pct": "vertical_ratio_pct", "pc": "performance_condition",
                "bb": "body_battery",
            }
            return _json({
                "account_id": account_id,
                "activity_id": activity_id,
                "total_datapoints": raw.get("totalMetricsCount", len(points)),
                "returned_datapoints": len(points),
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
                "avg_hrv_ms": dto.get("avgSleepStress"),  # approximation via sleep stress
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

    return app
