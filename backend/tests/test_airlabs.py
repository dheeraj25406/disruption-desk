import httpx
import pytest

from app.services.airlabs import (
    FlightProviderConfigurationError,
    FlightProviderNotFound,
    FlightProviderQuotaError,
    FlightProviderResponseError,
    AirLabsClient,
    normalize_flight,
)


FLIGHT = {
    "flight_iata": "AI101", "flight_date": "2026-10-29", "airline_iata": "AI",
    "airline_name": "Air India", "status": "active", "dep_iata": "DEL", "arr_iata": "LHR",
    "dep_name": "Indira Gandhi International", "arr_name": "Heathrow",
    "dep_time": "2026-10-29T13:00:00", "arr_time": "2026-10-29T18:00:00",
    "dep_time_utc": "2026-10-29T07:30:00Z", "arr_time_utc": "2026-10-29T17:00:00Z",
    "timeZone": "Asia/Kolkata", "delayMinutes": 12, "id": "provider-101",
}


def test_normalizes_airlabs_flight_without_claiming_inventory():
    flight = normalize_flight(FLIGHT, "2026-10-29")
    assert flight.provider == "airlabs"
    assert flight.flight_number == "AI101"
    assert flight.origin == "DEL" and flight.destination == "LHR"
    assert flight.scheduled_departure.replace("+00:00", "Z") == FLIGHT["dep_time_utc"]
    assert flight.scheduled_arrival.endswith("+00:00")
    assert flight.arrival_delay_minutes == 12
    assert flight.availability_confirmed is False


def test_rejects_missing_or_malformed_provider_facts():
    with pytest.raises(FlightProviderResponseError, match="missing number"):
        normalize_flight({**FLIGHT, "flight_iata": None, "flight_number": None, "flight_icao": None}, "2026-10-29")
    with pytest.raises(FlightProviderResponseError, match="invalid flight timestamp"):
        normalize_flight({**FLIGHT, "dep_time_utc": "not-a-date"}, "2026-10-29")


def test_flight_status_uses_documented_path_and_query_key():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        seen["headers"] = dict(request.headers)
        return httpx.Response(200, json={"response": FLIGHT})

    client = AirLabsClient(api_key="unit-test-key", http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    rows = client.flight_status("AI 101", "2026-10-29")
    assert len(rows) == 1 and rows[0].flight_number == "AI101"
    assert seen["path"] == "/api/v9/flight"
    assert seen["params"]["flight_iata"] == "AI101"
    assert seen["params"]["api_key"] == "unit-test-key"


def test_provider_key_never_appears_in_httpx_logs(caplog):
    client = AirLabsClient(api_key="private-unit-key", http_client=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"response": FLIGHT}))))
    with caplog.at_level("INFO"):
        client.flight_status("AI101", "2026-10-29")
    assert "private-unit-key" not in caplog.text


def test_flight_status_does_not_mislabel_closest_flight_as_requested_date():
    other_day = {**FLIGHT, "flight_date": None, "dep_time": "2026-10-30T13:00:00", "dep_time_utc": "2026-10-30T07:30:00Z"}
    client = AirLabsClient(api_key="unit-test-key", http_client=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"response": other_day}))))
    assert client.flight_status("AI101", "2026-10-29") == []


def test_schedule_search_uses_route_and_date_and_filters_provider_records():
    seen = {}

    def handler(request):
        seen.update(path=request.url.path, params=dict(request.url.params))
        return httpx.Response(200, json=[FLIGHT, {**FLIGHT, "flight_iata": "AI102", "dep_iata": "BOM"}])

    client = AirLabsClient(api_key="unit-test-key", http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    rows = client.search_schedules("DEL", "LHR", "2026-10-29")
    assert len(rows) == 1 and rows[0].flight_number == "AI101"
    assert seen["path"] == "/api/v9/schedules"
    assert seen["params"]["dep_iata"] == "DEL"
    assert seen["params"]["arr_iata"] == "LHR"
    assert "dep_date" not in seen["params"]
    assert seen["params"]["api_key"] == "unit-test-key"


def test_route_patterns_return_only_operating_day_records_with_local_times():
    seen = {}
    routes = [
        {"flight_iata":"6E201","airline_iata":"6E","dep_iata":"DEL","arr_iata":"BLR","dep_time":"10:30","arr_time":"13:15","duration":165,"days":["thu","fri"]},
        {"flight_iata":"AI202","airline_iata":"AI","dep_iata":"DEL","arr_iata":"BLR","dep_time":"15:00","arr_time":"17:40","duration":160,"days":["mon"]},
    ]
    def handler(request):
        seen.update(path=request.url.path,params=dict(request.url.params))
        return httpx.Response(200,json={"response":routes})
    client=AirLabsClient(api_key="unit-test-key",http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    rows=client.search_route_patterns("DEL","BLR","2026-10-29")
    assert len(rows)==1
    assert rows[0].flight_number=="6E201"
    assert rows[0].scheduled_departure=="2026-10-29T10:30:00"
    assert rows[0].scheduled_arrival=="2026-10-29T13:15:00"
    assert rows[0].availability_confirmed is False
    assert seen["path"]=="/api/v9/routes"
    assert seen["params"]["dep_iata"]=="DEL" and seen["params"]["arr_iata"]=="BLR"


def test_route_pattern_skips_malformed_rows_and_rejects_unexpected_payload():
    client=AirLabsClient(api_key="unit-test-key",http_client=httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json={"response":[{"flight_iata":"AI1","days":["thu"]}]}))))
    assert client.search_route_patterns("DEL","BLR","2026-10-29")==[]
    bad=AirLabsClient(api_key="unit-test-key",http_client=httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json={"response":"bad"}))))
    with pytest.raises(FlightProviderResponseError): bad.search_route_patterns("DEL","BLR","2026-10-29")


def test_rejects_invalid_key_without_leaking_it():
    client = AirLabsClient(api_key="private-test-key", http_client=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(401, json={"error": {"code": "unknown_api_key"}}))))
    with pytest.raises(FlightProviderConfigurationError) as error:
        client.flight_status("AI101", "2026-10-29")
    assert "private-test-key" not in str(error.value)


def test_quota_errors_remain_visible_and_not_success():
    client = AirLabsClient(api_key="unit-test-key", http_client=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(429, json={"detail": "limit"}))))
    with pytest.raises(FlightProviderQuotaError):
        client.search_schedules("DEL", "LHR", "2026-10-29")


def test_not_found_returns_empty_only_for_a_valid_flight_lookup():
    client = AirLabsClient(api_key="unit-test-key", http_client=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(404, json={"error":{"code":"not_found","message":"Flight not found"}}))))
    assert client.flight_status("AI101", "2026-10-29") == []
    with pytest.raises(FlightProviderNotFound):
        AirLabsClient(api_key="unit-test-key", http_client=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(404, json={"detail": "Not Found"}))))._get("wrong/endpoint")


def test_missing_key_fails_closed_and_status_is_safe():
    client = AirLabsClient(api_key="")
    with pytest.raises(FlightProviderConfigurationError):
        client.flight_status("AI101", "2026-10-29")
    status = AirLabsClient(api_key="private-test-key").status
    assert status["configured"] is True
    assert status["account_plan"] == "unknown"
    assert status["monthly_request_limit"] is None
    assert status["future_schedules_access"] is True
    assert "private-test-key" not in str(status)


def test_invalid_tool_inputs_are_rejected_before_request():
    client = AirLabsClient(api_key="unit-test-key")
    with pytest.raises(ValueError):
        client.flight_status("AI/101", "2026-10-29")
    with pytest.raises(ValueError):
        client.search_schedules("DEL", "LHR", "bad-date")
