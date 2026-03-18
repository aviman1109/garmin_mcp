"""Functional tests for P1 Garmin tools.

P1 tools:
  - get_activity_details   (time-series: HR, cadence, pace, power, stride)
  - get_training_status    (training load ATL/CTL, VO2max)
  - get_max_metrics        (VO2max precise, fitness age)
  - get_endurance_score    (endurance index trend)
  - get_hrv_data           (nightly HRV readings + summary)
"""

from __future__ import annotations

import datetime
import pytest


# ---------------------------------------------------------------------------
# get_activity_details
# ---------------------------------------------------------------------------

class TestGetActivityDetails:
    def test_returns_dict(self, garmin_client, recent_activity_id):
        result = garmin_client.get_activity_details(recent_activity_id, maxchart=50, maxpoly=0)
        assert isinstance(result, dict), "Expected dict response"

    def test_has_metric_descriptors(self, garmin_client, recent_activity_id):
        result = garmin_client.get_activity_details(recent_activity_id, maxchart=50, maxpoly=0)
        assert "metricDescriptors" in result
        assert len(result["metricDescriptors"]) > 0

    def test_has_time_series_rows(self, garmin_client, recent_activity_id):
        result = garmin_client.get_activity_details(recent_activity_id, maxchart=50, maxpoly=0)
        assert "activityDetailMetrics" in result
        assert len(result["activityDetailMetrics"]) > 0

    def test_includes_heart_rate_metric(self, garmin_client, recent_activity_id):
        result = garmin_client.get_activity_details(recent_activity_id, maxchart=50, maxpoly=0)
        keys = [d["key"] for d in result["metricDescriptors"]]
        assert "directHeartRate" in keys, f"directHeartRate not in metrics: {keys}"

    def test_includes_cadence_metric(self, garmin_client, recent_activity_id):
        result = garmin_client.get_activity_details(recent_activity_id, maxchart=50, maxpoly=0)
        keys = [d["key"] for d in result["metricDescriptors"]]
        # at least one cadence variant must be present
        cadence_keys = {"directRunCadence", "directDoubleCadence"}
        assert cadence_keys & set(keys), f"No cadence key found in: {keys}"

    def test_includes_timestamp_metric(self, garmin_client, recent_activity_id):
        result = garmin_client.get_activity_details(recent_activity_id, maxchart=50, maxpoly=0)
        keys = [d["key"] for d in result["metricDescriptors"]]
        assert "directTimestamp" in keys

    def test_row_length_matches_descriptor_count(self, garmin_client, recent_activity_id):
        result = garmin_client.get_activity_details(recent_activity_id, maxchart=50, maxpoly=0)
        descriptor_count = len(result["metricDescriptors"])
        first_row = result["activityDetailMetrics"][0]["metrics"]
        assert len(first_row) == descriptor_count


# ---------------------------------------------------------------------------
# get_training_status
# ---------------------------------------------------------------------------

class TestGetTrainingStatus:
    def test_returns_dict(self, garmin_client, test_date):
        result = garmin_client.get_training_status(test_date)
        assert isinstance(result, dict)

    def test_has_vo2max(self, garmin_client, test_date):
        result = garmin_client.get_training_status(test_date)
        assert "mostRecentVO2Max" in result
        vo2 = result["mostRecentVO2Max"]
        assert "generic" in vo2
        assert vo2["generic"]["vo2MaxValue"] is not None

    def test_has_training_load_balance(self, garmin_client, test_date):
        result = garmin_client.get_training_status(test_date)
        assert "mostRecentTrainingLoadBalance" in result
        tlb = result["mostRecentTrainingLoadBalance"]
        assert "metricsTrainingLoadBalanceDTOMap" in tlb
        assert len(tlb["metricsTrainingLoadBalanceDTOMap"]) > 0

    def test_training_load_has_aerobic_fields(self, garmin_client, test_date):
        result = garmin_client.get_training_status(test_date)
        tlb = result["mostRecentTrainingLoadBalance"]["metricsTrainingLoadBalanceDTOMap"]
        entry = next(iter(tlb.values()))
        assert "monthlyLoadAerobicLow" in entry
        assert "monthlyLoadAerobicHigh" in entry
        assert "monthlyLoadAnaerobic" in entry


# ---------------------------------------------------------------------------
# get_max_metrics
# ---------------------------------------------------------------------------

class TestGetMaxMetrics:
    def test_returns_list(self, garmin_client, test_date):
        result = garmin_client.get_max_metrics(test_date)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_has_generic_vo2max(self, garmin_client, test_date):
        result = garmin_client.get_max_metrics(test_date)
        entry = result[0]
        assert "generic" in entry
        assert entry["generic"]["vo2MaxValue"] is not None

    def test_vo2max_value_is_plausible(self, garmin_client, test_date):
        result = garmin_client.get_max_metrics(test_date)
        vo2 = result[0]["generic"]["vo2MaxValue"]
        assert 20 <= vo2 <= 90, f"VO2max value {vo2} out of plausible range"

    def test_has_calendar_date(self, garmin_client, test_date):
        result = garmin_client.get_max_metrics(test_date)
        assert result[0]["generic"]["calendarDate"] is not None


# ---------------------------------------------------------------------------
# get_endurance_score
# ---------------------------------------------------------------------------

class TestGetEnduranceScore:
    @pytest.fixture(scope="class")
    def date_range(self):
        end = datetime.date.today() - datetime.timedelta(days=1)
        start = end - datetime.timedelta(days=29)
        return start.isoformat(), end.isoformat()

    def test_returns_dict(self, garmin_client, date_range):
        start, end = date_range
        result = garmin_client.get_endurance_score(start, end)
        assert isinstance(result, dict)

    def test_has_avg_and_max(self, garmin_client, date_range):
        start, end = date_range
        result = garmin_client.get_endurance_score(start, end)
        assert "avg" in result
        assert "max" in result
        assert result["avg"] > 0

    def test_has_weekly_groups(self, garmin_client, date_range):
        start, end = date_range
        result = garmin_client.get_endurance_score(start, end)
        assert "groupMap" in result
        assert len(result["groupMap"]) > 0

    def test_groups_have_contributors(self, garmin_client, date_range):
        start, end = date_range
        result = garmin_client.get_endurance_score(start, end)
        first_group = next(iter(result["groupMap"].values()))
        assert "enduranceContributorDTOList" in first_group
        contributors = first_group["enduranceContributorDTOList"]
        assert len(contributors) > 0
        total = sum(c["contribution"] for c in contributors)
        assert 95 <= total <= 105, f"Contributions should sum ~100%, got {total}"


# ---------------------------------------------------------------------------
# get_hrv_data
# ---------------------------------------------------------------------------

class TestGetHrvData:
    def test_returns_dict_or_none(self, garmin_client, test_date):
        result = garmin_client.get_hrv_data(test_date)
        assert result is None or isinstance(result, dict)

    def test_has_hrv_summary(self, garmin_client, test_date):
        result = garmin_client.get_hrv_data(test_date)
        if result is None:
            pytest.skip("No HRV data available for this date")
        assert "hrvSummary" in result

    def test_summary_has_key_fields(self, garmin_client, test_date):
        result = garmin_client.get_hrv_data(test_date)
        if result is None:
            pytest.skip("No HRV data available for this date")
        summary = result["hrvSummary"]
        assert "weeklyAvg" in summary
        assert "lastNightAvg" in summary
        assert "status" in summary
        assert "baseline" in summary

    def test_has_readings(self, garmin_client, test_date):
        result = garmin_client.get_hrv_data(test_date)
        if result is None:
            pytest.skip("No HRV data available for this date")
        assert "hrvReadings" in result
        assert len(result["hrvReadings"]) > 0

    def test_readings_have_value_and_timestamp(self, garmin_client, test_date):
        result = garmin_client.get_hrv_data(test_date)
        if result is None:
            pytest.skip("No HRV data available for this date")
        reading = result["hrvReadings"][0]
        assert "hrvValue" in reading
        assert "readingTimeLocal" in reading
        assert reading["hrvValue"] > 0

    def test_hrv_values_are_plausible(self, garmin_client, test_date):
        result = garmin_client.get_hrv_data(test_date)
        if result is None:
            pytest.skip("No HRV data available for this date")
        avg = result["hrvSummary"]["lastNightAvg"]
        assert 10 <= avg <= 200, f"HRV avg {avg} out of plausible range"
