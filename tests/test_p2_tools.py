"""Functional tests for P2 Garmin tools.

P2 tools:
  - get_sleep_data        (sleep stages, scores)
  - get_heart_rates       (full-day HR timeseries)
  - get_stress_data       (stress level timeseries)
  - get_respiration_data  (respiration rate timeseries)
  - get_spo2_data         (blood oxygen saturation)
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# get_sleep_data
# ---------------------------------------------------------------------------

class TestGetSleepData:
    def test_returns_dict_or_none(self, garmin_client, test_date):
        result = garmin_client.get_sleep_data(test_date)
        assert result is None or isinstance(result, dict)

    def test_has_daily_sleep_dto(self, garmin_client, test_date):
        result = garmin_client.get_sleep_data(test_date)
        if not result:
            pytest.skip("No sleep data available for this date")
        assert "dailySleepDTO" in result

    def test_has_sleep_duration_fields(self, garmin_client, test_date):
        result = garmin_client.get_sleep_data(test_date)
        if not result:
            pytest.skip("No sleep data available for this date")
        dto = result["dailySleepDTO"]
        assert "sleepTimeSeconds" in dto or "totalSleepSeconds" in dto

    def test_has_sleep_levels_map(self, garmin_client, test_date):
        result = garmin_client.get_sleep_data(test_date)
        if not result:
            pytest.skip("No sleep data available for this date")
        assert "sleepLevels" in result or "sleepLevelsMap" in result or "sleepMovement" in result

    def test_sleep_score_is_plausible(self, garmin_client, test_date):
        result = garmin_client.get_sleep_data(test_date)
        if not result:
            pytest.skip("No sleep data available for this date")
        dto = result.get("dailySleepDTO", {})
        score = dto.get("sleepScores", {})
        if not score:
            pytest.skip("No sleep score in response")
        overall = score.get("overall", {}).get("value") if isinstance(score, dict) else None
        if overall is not None:
            assert 0 <= overall <= 100, f"Sleep score {overall} out of range"


# ---------------------------------------------------------------------------
# get_heart_rates
# ---------------------------------------------------------------------------

class TestGetHeartRates:
    def test_returns_dict(self, garmin_client, test_date):
        result = garmin_client.get_heart_rates(test_date)
        assert isinstance(result, dict)

    def test_has_heart_rate_values(self, garmin_client, test_date):
        result = garmin_client.get_heart_rates(test_date)
        # API returns heartRateValues list or heartRateReadings
        has_data = (
            "heartRateValues" in result
            or "heartRateReadings" in result
        )
        assert has_data, f"Expected heartRateValues or heartRateReadings in response keys: {list(result.keys())}"

    def test_readings_are_nonempty(self, garmin_client, test_date):
        result = garmin_client.get_heart_rates(test_date)
        values = result.get("heartRateValues") or result.get("heartRateReadings") or []
        assert len(values) > 0, "Expected at least one HR reading"

    def test_resting_hr_is_plausible(self, garmin_client, test_date):
        result = garmin_client.get_heart_rates(test_date)
        rhr = result.get("restingHeartRate")
        if rhr is None:
            pytest.skip("No restingHeartRate field in response")
        assert 30 <= rhr <= 120, f"Resting HR {rhr} out of plausible range"


# ---------------------------------------------------------------------------
# get_stress_data
# ---------------------------------------------------------------------------

class TestGetStressData:
    def test_returns_dict(self, garmin_client, test_date):
        result = garmin_client.get_stress_data(test_date)
        assert isinstance(result, dict)

    def test_has_stress_values(self, garmin_client, test_date):
        result = garmin_client.get_stress_data(test_date)
        assert "stressValuesArray" in result or "stressDetails" in result, \
            f"Expected stress values in response keys: {list(result.keys())}"

    def test_stress_readings_nonempty(self, garmin_client, test_date):
        result = garmin_client.get_stress_data(test_date)
        values = result.get("stressValuesArray") or []
        assert len(values) > 0, "Expected at least one stress reading"

    def test_avg_stress_is_plausible(self, garmin_client, test_date):
        result = garmin_client.get_stress_data(test_date)
        avg = result.get("avgStressLevel")
        if avg is None:
            pytest.skip("No avgStressLevel in response")
        assert 0 <= avg <= 100, f"Avg stress {avg} out of range"


# ---------------------------------------------------------------------------
# get_respiration_data
# ---------------------------------------------------------------------------

class TestGetRespirationData:
    def test_returns_dict_or_none(self, garmin_client, test_date):
        result = garmin_client.get_respiration_data(test_date)
        assert result is None or isinstance(result, dict)

    def test_has_respiration_values(self, garmin_client, test_date):
        result = garmin_client.get_respiration_data(test_date)
        if not result:
            pytest.skip("No respiration data available for this date")
        has_data = (
            "respirationValues" in result
            or "respirationValuesArray" in result
            or "respirationReadings" in result
        )
        assert has_data, f"Expected respiration values in keys: {list(result.keys())}"

    def test_respiration_readings_nonempty(self, garmin_client, test_date):
        result = garmin_client.get_respiration_data(test_date)
        if not result:
            pytest.skip("No respiration data available for this date")
        values = (
            result.get("respirationValues")
            or result.get("respirationValuesArray")
            or result.get("respirationReadings")
            or []
        )
        assert len(values) > 0

    def test_respiration_rate_plausible(self, garmin_client, test_date):
        result = garmin_client.get_respiration_data(test_date)
        if not result:
            pytest.skip("No respiration data available for this date")
        avg = result.get("avgWakingRespirationValue") or result.get("avgRespirationValue")
        if avg is None:
            pytest.skip("No avg respiration value in response")
        assert 5 <= avg <= 40, f"Avg respiration {avg} breaths/min out of plausible range"


# ---------------------------------------------------------------------------
# get_spo2_data
# ---------------------------------------------------------------------------

class TestGetSpo2Data:
    def test_returns_dict_or_none(self, garmin_client, test_date):
        result = garmin_client.get_spo2_data(test_date)
        assert result is None or isinstance(result, dict)

    def test_has_spo2_readings(self, garmin_client, test_date):
        result = garmin_client.get_spo2_data(test_date)
        if not result:
            pytest.skip("No SpO2 data available for this date")
        has_data = (
            "spO2HourlyAverages" in result
            or "continuousReadings" in result
            or "SpO2SleepSummary" in result
        )
        assert has_data, f"Expected SpO2 readings in keys: {list(result.keys())}"

    def test_spo2_values_plausible(self, garmin_client, test_date):
        result = garmin_client.get_spo2_data(test_date)
        if not result:
            pytest.skip("No SpO2 data available for this date")
        hourly = result.get("spO2HourlyAverages") or []
        if not hourly:
            pytest.skip("No hourly SpO2 averages in response")
        # Each entry is [timestamp_ms, spo2_pct] or similar
        valid = [v for v in hourly if v is not None and isinstance(v, (list, dict))]
        assert len(valid) > 0

    def test_avg_spo2_plausible(self, garmin_client, test_date):
        result = garmin_client.get_spo2_data(test_date)
        if not result:
            pytest.skip("No SpO2 data available for this date")
        avg = (result.get("SpO2SleepSummary") or {}).get("averageSpO2")
        if avg is None:
            pytest.skip("No average SpO2 in response")
        assert 70 <= avg <= 100, f"Avg SpO2 {avg}% out of plausible range"
