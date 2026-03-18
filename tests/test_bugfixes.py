"""Regression tests for bug fixes."""

from __future__ import annotations


class TestGetActivitySplitsFieldMapping:
    """get_activity_splits was reading from non-existent summaryDTO instead of lap directly."""

    def test_returns_dict(self, garmin_client, recent_activity_id):
        result = garmin_client.get_activity_splits(recent_activity_id)
        assert isinstance(result, dict)

    def test_has_lap_dtos(self, garmin_client, recent_activity_id):
        result = garmin_client.get_activity_splits(recent_activity_id)
        assert "lapDTOs" in result
        assert len(result["lapDTOs"]) > 0

    def test_lap_has_distance(self, garmin_client, recent_activity_id):
        result = garmin_client.get_activity_splits(recent_activity_id)
        lap = result["lapDTOs"][0]
        assert lap.get("distance") is not None, "distance should be at top level of lap, not in summaryDTO"
        assert lap["distance"] > 0

    def test_lap_has_heart_rate(self, garmin_client, recent_activity_id):
        result = garmin_client.get_activity_splits(recent_activity_id)
        lap = result["lapDTOs"][0]
        assert lap.get("averageHR") is not None
        assert 50 <= lap["averageHR"] <= 220

    def test_lap_has_cadence(self, garmin_client, recent_activity_id):
        result = garmin_client.get_activity_splits(recent_activity_id)
        lap = result["lapDTOs"][0]
        assert lap.get("averageRunCadence") is not None
        assert lap["averageRunCadence"] > 0

    def test_lap_has_speed(self, garmin_client, recent_activity_id):
        result = garmin_client.get_activity_splits(recent_activity_id)
        lap = result["lapDTOs"][0]
        assert lap.get("averageSpeed") is not None
        assert lap["averageSpeed"] > 0
