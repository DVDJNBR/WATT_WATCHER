"""Tests for open_meteo_client.py — HTFX/WEATHER_CORRECT_DAY.

Regression cover for two defects that kept fact_meteo permanently a day behind
fact_energy_flow, which dragged the dashboard's shared window back to a
night-time cutoff where solar reads zero:

  * forecast_days=0 returns only *completed* past days, so the current day was
    never requested at all;
  * timezone=Europe/Paris returns naive local times, written verbatim into a
    column whose other rows are UTC — a ~2 h shift against production.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from functions.shared.open_meteo_client import REGION_CENTROIDS, fetch_meteo_all_regions


def _hour(offset_hours: int) -> str:
    """UTC hour offset from now, in Open-Meteo's "YYYY-MM-DDTHH:MM" shape."""
    return (datetime.now(timezone.utc) + timedelta(hours=offset_hours)).strftime("%Y-%m-%dT%H:%M")


def _mock_response(times):
    n = len(times)
    resp = MagicMock(status_code=200)
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "hourly": {
            "time": times,
            "temperature_2m":  [12.0] * n,
            "wind_speed_10m":  [5.0] * n,
            "cloudcover":      [50.0] * n,
        }
    }
    return resp


class TestRequestParams:
    def test_requests_utc_not_paris_local(self):
        """Paris-local hours in a UTC column is what shifted météo by ~2 h."""
        resp = _mock_response([_hour(-1)])
        with patch("functions.shared.open_meteo_client.requests.get", return_value=resp) as get:
            fetch_meteo_all_regions(past_days=1)

        assert all(c.kwargs["params"]["timezone"] == "UTC" for c in get.call_args_list)

    def test_requests_today_not_only_completed_days(self):
        """forecast_days=0 never reaches the current day — the core defect."""
        resp = _mock_response([_hour(-1)])
        with patch("functions.shared.open_meteo_client.requests.get", return_value=resp) as get:
            fetch_meteo_all_regions(past_days=1)

        assert all(c.kwargs["params"]["forecast_days"] == 1 for c in get.call_args_list)

    def test_queries_every_region(self):
        resp = _mock_response([_hour(-1)])
        with patch("functions.shared.open_meteo_client.requests.get", return_value=resp) as get:
            fetch_meteo_all_regions(past_days=1)

        assert get.call_count == len(REGION_CENTROIDS)


class TestForecastCutoff:
    def test_drops_hours_past_the_present(self):
        """forecast_days=1 also returns the rest of today; fact_meteo is an
        observations table, so future hours must not be stored."""
        resp = _mock_response([_hour(-2), _hour(-1), _hour(+3), _hour(+6)])
        with patch("functions.shared.open_meteo_client.requests.get", return_value=resp):
            records = fetch_meteo_all_regions(past_days=1)

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
        assert records, "past hours should still be returned"
        assert all(r["timestamp"] <= now for r in records)

    def test_keeps_past_hours(self):
        past = [_hour(-3), _hour(-2), _hour(-1)]
        resp = _mock_response(past)
        with patch("functions.shared.open_meteo_client.requests.get", return_value=resp):
            records = fetch_meteo_all_regions(past_days=1)

        per_region = len(records) / len(REGION_CENTROIDS)
        assert per_region == len(past)

    def test_skips_rows_with_no_temperature(self):
        resp = _mock_response([_hour(-2), _hour(-1)])
        resp.json.return_value["hourly"]["temperature_2m"] = [None, 12.0]
        with patch("functions.shared.open_meteo_client.requests.get", return_value=resp):
            records = fetch_meteo_all_regions(past_days=1)

        assert len(records) == len(REGION_CENTROIDS)


class TestFailureHandling:
    def test_one_region_failing_does_not_abort_the_rest(self):
        ok = _mock_response([_hour(-1)])

        def side_effect(*_args, **kwargs):
            if kwargs["params"]["latitude"] == REGION_CENTROIDS["11"]["lat"]:
                raise RuntimeError("upstream 500")
            return ok

        with patch("functions.shared.open_meteo_client.requests.get", side_effect=side_effect):
            records = fetch_meteo_all_regions(past_days=1)

        assert {r["region_code"] for r in records} == set(REGION_CENTROIDS) - {"11"}
