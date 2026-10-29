"""Typed, server-side AirLabs flight and schedule adapter."""
from __future__ import annotations

from datetime import datetime, timezone, date as date_type, time as time_type, timedelta
import logging
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from app.core.config import settings

# AirLabs authenticates with a query parameter. httpx emits the full request URL
# at INFO, which would expose that credential in server logs. Keep both transport
# loggers above INFO; application logs contain only safe request summaries.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


class FlightProviderError(RuntimeError):
    category = "provider_failure"


class FlightProviderConfigurationError(FlightProviderError):
    category = "configuration"


class FlightProviderQuotaError(FlightProviderError):
    category = "quota"


class FlightProviderResponseError(FlightProviderError):
    category = "invalid_provider_response"


class FlightProviderNotFound(FlightProviderError):
    category = "not_found"


class AirLabsFlight(BaseModel):
    """Provider facts only; the schema intentionally has no inventory claim."""
    provider: Literal["airlabs"] = "airlabs"
    provider_flight_id: str | None = None
    flight_date: str
    flight_number: str
    airline: str | None = None
    status: str | None = None
    origin: str
    destination: str
    origin_name: str | None = None
    destination_name: str | None = None
    scheduled_departure: str
    scheduled_arrival: str
    estimated_departure: str | None = None
    estimated_arrival: str | None = None
    actual_departure: str | None = None
    actual_arrival: str | None = None
    departure_delay_minutes: int | None = None
    arrival_delay_minutes: int | None = None
    retrieved_at: datetime
    availability_confirmed: Literal[False] = False


class RawFlight(BaseModel):
    """Known AirLabs field family; ignore additive fields."""
    model_config = ConfigDict(extra="ignore")
    flight_iata: str | None = None
    flight_icao: str | None = None
    flight_number: str | None = None
    flight_date: str | None = None
    airline_iata: str | None = None
    airline_name: str | None = None
    status: str | None = None
    dep_iata: str | None = None
    arr_iata: str | None = None
    dep_name: str | None = None
    arr_name: str | None = None
    dep_time: str | None = None
    arr_time: str | None = None
    dep_time_utc: str | None = None
    arr_time_utc: str | None = None
    dep_estimated: str | None = None
    arr_estimated: str | None = None
    dep_estimated_utc: str | None = None
    arr_estimated_utc: str | None = None
    dep_actual: str | None = None
    arr_actual: str | None = None
    dep_actual_utc: str | None = None
    arr_actual_utc: str | None = None
    dep_delayed: int | None = None
    arr_delayed: int | None = None
    delay: int | None = None
    delayMinutes: int | None = None
    timeZone: str | None = None
    id: str | int | None = None


class AirLabsRoutePattern(BaseModel):
    """Published recurring AirLabs route pattern, not a date-specific live flight."""
    provider: Literal["airlabs"] = "airlabs"
    schedule_basis: Literal["published_route_pattern"] = "published_route_pattern"
    flight_date: str
    flight_number: str
    airline: str | None = None
    status: None = None
    origin: str
    destination: str
    scheduled_departure: str
    scheduled_arrival: str
    departure_local_time: str
    arrival_local_time: str
    operating_days: list[str]
    retrieved_at: datetime
    availability_confirmed: Literal[False] = False


class RawRoute(BaseModel):
    model_config = ConfigDict(extra="ignore")
    flight_iata: str | None = None
    flight_number: str | None = None
    airline_iata: str | None = None
    airline_name: str | None = None
    dep_iata: str | None = None
    arr_iata: str | None = None
    dep_time: str | None = None
    arr_time: str | None = None
    duration: int | None = None
    days: list[str] | None = None


class AirLabsClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 http_client: httpx.Client | None = None):
        self._api_key = settings.airlabs_api_key if api_key is None else api_key
        self.base_url = (base_url or settings.airlabs_base_url).rstrip("/")
        self._client = http_client

    @property
    def status(self) -> dict[str, Any]:
        return {
            "provider": "AirLabs", "configured": bool(self._api_key),
            "credentials_status": "configured_unverified" if self._api_key else "missing",
            "account_plan": "unknown", "monthly_request_limit": None,
            "live_status_access": True, "future_schedules_access": True,
            "schedule_access_level": "Subject to AirLabs account plan and the provider's 10-hour schedule horizon",
            "availability_note": "Schedules do not confirm seats, fares, or booking inventory.",
            "real_time_update_note": "Provider flight facts can lag airline operations.",
        }

    def _get(self, path: str, params: dict[str, str] | None = None,
             *, not_found_is_empty: bool = False) -> Any:
        if not self._api_key:
            raise FlightProviderConfigurationError("AirLabs is not configured. Set AIRLABS_API_KEY in backend/.env.")
        client = self._client or httpx.Client(timeout=httpx.Timeout(15.0, connect=5.0), follow_redirects=False)
        close_client = self._client is None
        try:
            response = client.get(
                f"{self.base_url}/{path.lstrip('/')}",
                params={**(params or {}), "api_key": self._api_key},
                headers={"Accept": "application/json"},
            )
        except httpx.TimeoutException:
            raise FlightProviderError("AirLabs request timed out") from None
        except httpx.HTTPError:
            # Do not include the request URL or headers; they are credential-sensitive.
            raise FlightProviderError("Could not connect to AirLabs") from None
        finally:
            if close_client:
                client.close()
        if response.status_code in {401, 403}:
            raise FlightProviderConfigurationError("AirLabs rejected the configured API key or account permissions. Verify the key and plan in the AirLabs dashboard.")
        if response.status_code == 429:
            raise FlightProviderQuotaError("AirLabs request limit reached; check the plan quota and retry window.")
        if response.status_code >= 500:
            raise FlightProviderError("AirLabs is temporarily unavailable")
        try:
            payload = response.json()
        except ValueError:
            if response.status_code == 404:
                raise FlightProviderNotFound("AirLabs endpoint was not found; verify the configured API route.") from None
            raise FlightProviderResponseError("AirLabs returned an unreadable response") from None
        if not isinstance(payload, (dict, list)):
            raise FlightProviderResponseError("AirLabs returned an unexpected response shape")
        if isinstance(payload, dict) and payload.get("error"):
            error = payload["error"]
            code = str(error.get("code", "provider_error")) if isinstance(error, dict) else "provider_error"
            if code in {"unknown_api_key", "invalid_api_key", "access_denied", "unauthorized"}:
                raise FlightProviderConfigurationError("AirLabs rejected the configured API key or account permissions. Verify the key and plan in the AirLabs dashboard.")
            if code in {"rate_limited", "quota_exceeded", "upstream_budget_exhausted"}:
                raise FlightProviderQuotaError("AirLabs request limit reached; check the plan quota and retry window.")
            if code == "not_found" and not_found_is_empty:
                return []
            # Provider messages may echo request parameters; never propagate raw messages
            # because AirLabs authenticates using a query parameter.
            raise FlightProviderError(f"AirLabs request failed ({code}).")
        if response.status_code == 404:
            detail = payload.get("detail") if isinstance(payload, dict) else None
            if not_found_is_empty and isinstance(detail, str) and "flight" in detail.casefold() and "not found" in detail.casefold():
                return []
            raise FlightProviderNotFound("AirLabs endpoint was not found; verify the configured API route.")
        if response.status_code >= 400:
            raise FlightProviderError(f"AirLabs request failed with HTTP {response.status_code}.")
        return payload

    def flight_status(self, flight_number: str, flight_date: str) -> list[AirLabsFlight]:
        number = _validate_flight_number(flight_number)
        _validate_date(flight_date)
        payload = self._get("api/v9/flight", {"flight_iata": number,
                              "_fields": "flight_iata,airline_iata,dep_iata,arr_iata,dep_time,arr_time,dep_time_utc,arr_time_utc,dep_estimated,arr_estimated,dep_actual,arr_actual,status,delayed,dep_delayed,arr_delayed"}, not_found_is_empty=True)
        rows = _normalize_payload(payload, flight_date, expected_number=number)
        # The single-flight endpoint returns the closest matching scheduled/live
        # instance, not a date-addressable lookup. Enforce the requested local date.
        return [row for row in rows if row.flight_date == flight_date]

    def search_schedules(self, origin: str, destination: str, flight_date: str) -> list[AirLabsFlight]:
        _validate_route_date(origin, destination, flight_date)
        payload = self._get("api/v9/schedules", {
            "dep_iata": origin.upper(), "arr_iata": destination.upper(),
            "limit": "50",
            "_fields": "flight_iata,airline_iata,dep_iata,arr_iata,dep_time,arr_time,dep_time_utc,arr_time_utc,dep_estimated,arr_estimated,dep_actual,arr_actual,status,delayed,dep_delayed,arr_delayed",
        }, not_found_is_empty=True)
        rows = _normalize_payload(payload, flight_date, expected_origin=origin, expected_destination=destination)
        # The documented schedules endpoint has no date query parameter and exposes a
        # rolling window up to 10 hours ahead. Never present another date's row as a match.
        return [row for row in rows if row.flight_date == flight_date]

    def search_route_patterns(self, origin: str, destination: str, flight_date: str) -> list[AirLabsRoutePattern]:
        """Fetch AirLabs' recurring route database for dates beyond its live schedule window."""
        _validate_route_date(origin, destination, flight_date)
        payload = self._get("api/v9/routes", {
            "dep_iata": origin.upper(), "arr_iata": destination.upper(), "limit": "50",
            "_fields": "flight_iata,flight_number,airline_iata,dep_iata,arr_iata,dep_time,arr_time,duration,days",
        }, not_found_is_empty=True)
        records = payload if isinstance(payload, list) else payload.get("response", payload.get("data", []))
        if not isinstance(records, list):
            raise FlightProviderResponseError("AirLabs returned an unexpected route-pattern response shape")
        wanted_day = datetime.strptime(flight_date, "%Y-%m-%d").strftime("%a").lower()
        from app.services.labels import AIRLINES
        now = datetime.now(timezone.utc)
        output = []
        for record in records:
            try:
                route = RawRoute.model_validate(record)
                days = [day[:3].lower() for day in (route.days or [])]
                if wanted_day not in days:
                    continue
                number = route.flight_iata or route.flight_number
                if not all((number, route.dep_iata, route.arr_iata, route.dep_time, route.arr_time, route.duration)):
                    continue
                dep_clock = time_type.fromisoformat(route.dep_time)
                arr_clock = time_type.fromisoformat(route.arr_time)
                dep_date = datetime.strptime(flight_date, "%Y-%m-%d").date()
                departure = datetime.combine(dep_date, dep_clock)
                arrival = datetime.combine(dep_date, arr_clock)
                # For India domestic cases both airport clocks use IST; handle overnight routes.
                if arrival <= departure:
                    arrival += timedelta(days=1)
                duration = int(route.duration)
                # Reject malformed provider rows where local times conflict substantially with duration.
                if abs(int((arrival - departure).total_seconds() / 60) - duration) > 180:
                    continue
                output.append(AirLabsRoutePattern(
                    flight_date=flight_date, flight_number=number.upper(),
                    airline=AIRLINES.get(route.airline_iata or "", route.airline_iata),
                    origin=route.dep_iata.upper(), destination=route.arr_iata.upper(),
                    scheduled_departure=departure.isoformat(), scheduled_arrival=arrival.isoformat(),
                    departure_local_time=route.dep_time, arrival_local_time=route.arr_time,
                    operating_days=days, retrieved_at=now,
                ))
            except (ValidationError, ValueError, TypeError):
                # A malformed record is ignored; it is never promoted to a candidate.
                continue
        return output

    def search_alternatives(self, origin: str, destination: str, flight_date: str) -> tuple[list[dict[str, Any]], str]:
        """Prefer date-specific schedule rows; use published patterns only when none match."""
        scheduled = self.search_schedules(origin, destination, flight_date)
        if scheduled:
            return [flight.model_dump(mode="json") | {"flight": flight.flight_number,
                    "departure": flight.scheduled_departure, "arrival": flight.scheduled_arrival,
                    "source": "airlabs"} for flight in scheduled], "live_schedule"
        patterns = self.search_route_patterns(origin, destination, flight_date)
        return [pattern.model_dump(mode="json") | {"flight": pattern.flight_number,
                "departure": pattern.scheduled_departure, "arrival": pattern.scheduled_arrival,
                "source": "airlabs_route_pattern"} for pattern in patterns], "published_route_pattern"


def _validate_date(value: str) -> None:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("flight_date must use YYYY-MM-DD") from exc


def _validate_route_date(origin: str, destination: str, flight_date: str) -> None:
    if len(origin) != 3 or not origin.isalpha() or len(destination) != 3 or not destination.isalpha():
        raise ValueError("Airport codes must be three-letter IATA codes")
    _validate_date(flight_date)


def _validate_flight_number(value: str) -> str:
    flight = value.strip().upper().replace(" ", "")
    if not flight or len(flight) > 16 or not flight.isalnum():
        raise ValueError("flight_number may contain only airline letters and digits")
    return flight


def _as_utc(value: str | None, local_value: str | None, timezone_name: str | None,
            value_is_utc: bool = False) -> str | None:
    value = value or local_value
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
            raise FlightProviderResponseError("AirLabs returned an invalid flight timestamp") from exc
    if parsed.tzinfo is None and value is not None and value_is_utc:
        parsed = parsed.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None and timezone_name:
        try:
            parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
        except ZoneInfoNotFoundError:
            # Keep the provider's local timestamp, clearly without fabricating an offset.
            return value
    return parsed.isoformat()


def normalize_flight(raw: dict[str, Any], requested_date: str) -> AirLabsFlight:
    try:
        flight = RawFlight.model_validate(raw)
    except ValidationError as exc:
        raise FlightProviderResponseError("AirLabs returned a malformed flight record") from exc
    number = flight.flight_iata or flight.flight_number or flight.flight_icao
    origin, destination = flight.dep_iata, flight.arr_iata
    departure = _as_utc(flight.dep_time_utc, flight.dep_time, flight.timeZone)
    arrival = _as_utc(flight.arr_time_utc, flight.arr_time, flight.timeZone)
    if not all((number, origin, destination, departure, arrival)):
        raise FlightProviderResponseError("AirLabs flight record is missing number, route, or scheduled times")
    try:
        departure_dt = datetime.fromisoformat(departure.replace("Z", "+00:00"))
        datetime.fromisoformat(arrival.replace("Z", "+00:00"))
        record_date = flight.flight_date or departure_dt.date().isoformat() or requested_date
        _validate_date(record_date)
    except ValueError as exc:
        raise FlightProviderResponseError("AirLabs returned an invalid date or schedule") from exc
    delay = flight.delayMinutes if flight.delayMinutes is not None else flight.delay
    from app.services.labels import AIRLINES
    airline_code = flight.airline_iata
    return AirLabsFlight(
        provider_flight_id=str(flight.id) if flight.id is not None else None,
        flight_date=record_date,
        flight_number=number.upper(), airline=flight.airline_name or AIRLINES.get(airline_code or "", airline_code),
        status=flight.status, origin=origin.upper(), destination=destination.upper(),
        origin_name=flight.dep_name, destination_name=flight.arr_name,
        scheduled_departure=_as_utc(flight.dep_time_utc, flight.dep_time, flight.timeZone, value_is_utc=True),
        scheduled_arrival=_as_utc(flight.arr_time_utc, flight.arr_time, flight.timeZone, value_is_utc=True),
        estimated_departure=_as_utc(flight.dep_estimated_utc, flight.dep_estimated, flight.timeZone, value_is_utc=True),
        estimated_arrival=_as_utc(flight.arr_estimated_utc, flight.arr_estimated, flight.timeZone, value_is_utc=True),
        actual_departure=_as_utc(flight.dep_actual_utc, flight.dep_actual, flight.timeZone, value_is_utc=True),
        actual_arrival=_as_utc(flight.arr_actual_utc, flight.arr_actual, flight.timeZone, value_is_utc=True),
        departure_delay_minutes=flight.dep_delayed,
        arrival_delay_minutes=flight.arr_delayed if flight.arr_delayed is not None else delay,
        retrieved_at=datetime.now(timezone.utc),
    )


def _normalize_payload(payload: Any, requested_date: str, expected_number: str | None = None,
                       expected_origin: str | None = None,
                       expected_destination: str | None = None) -> list[AirLabsFlight]:
    if payload == []:
        return []
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("data", payload.get("response", payload.get("flights")))
        if rows is None and any(k in payload for k in ("flight_iata", "flight_number")):
            rows = [payload]
        if isinstance(rows, dict):
            rows = [rows]
    else:
        rows = None
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise FlightProviderResponseError("AirLabs response did not contain a flight record list")
    normalized = [normalize_flight(row, requested_date) for row in rows]
    return [row for row in normalized
            if (expected_number is None or row.flight_number.replace(" ", "").casefold() == expected_number.casefold())
            and (expected_origin is None or row.origin == expected_origin.upper())
            and (expected_destination is None or row.destination == expected_destination.upper())]
