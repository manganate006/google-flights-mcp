"""
Google Flights MCP Server — uses fast-flights v3 API.
Searches Google Flights for one-way, round-trip, and multi-city flights.
Bypasses GDPR consent via SOCS cookie.

Also exposes airport-resolution tools (find_airport, find_airports_near) so agents
can turn a city name or coordinates into the IATA codes the search tools expect.
"""

import difflib
import json
import logging
import math
import time
import unicodedata
from datetime import date, timedelta

import airportsdata
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("google-flights-mcp")

mcp = FastMCP("google-flights")

DEFAULT_DEPARTURES = ["NCE", "MRS"]
CONSENT_COOKIE = "SOCS=CAESEwgDEgk2NTczNjkyNTAaAmVuIAEaBgiA_LmsBg; CONSENT=PENDING+410"

# Throttle / retry tuning
FETCH_RETRIES = 3
FETCH_BACKOFF = [1, 3, 6]   # seconds before retry attempt 1, 2, 3
INTER_AIRPORT_DELAY = 2.5   # seconds between successive departure-airport requests

# Caps for the fan-out tools (each candidate triggers its own Google request[s])
MAX_FLEX_DATES = 14
MAX_DESTINATIONS = 8

# Airport dataset (offline, keyed by IATA code, commercial airports only).
# City names are in English, so map the most common French exonyms that diverge
# too much for fuzzy matching to catch.
AIRPORTS = airportsdata.load("IATA")
FR_CITY_ALIASES = {
    "londres": "london",
    "bruxelles": "brussels",
    "varsovie": "warsaw",
    "edimbourg": "edinburgh",
    "douvres": "dover",
    "la haye": "the hague",
    "munich": "munich",
    "cologne": "cologne",
    "aix-la-chapelle": "aachen",
    "francfort": "frankfurt",
    "sarrebruck": "saarbrucken",
    "geneve": "geneva",
    "bale": "basel",
    "milan": "milan",
    "florence": "florence",
    "naples": "naples",
    "venise": "venice",
    "genes": "genoa",
    "turin": "turin",
    "seville": "sevilla",
    "saint-jacques-de-compostelle": "santiago de compostela",
    "lisbonne": "lisbon",
    "porto": "porto",
    "athenes": "athens",
    "copenhague": "copenhagen",
    "moscou": "moscow",
    "vienne": "vienna",
    "prague": "prague",
    "cracovie": "krakow",
    "le caire": "cairo",
    "alger": "algiers",
    "tanger": "tangier",
}
FUZZY_THRESHOLD = 0.82


# ── Fetch & parse ─────────────────────────────────────────────

def _looks_parsable(html: str) -> bool:
    """Cheap check: does the response actually contain the data script Google embeds?"""
    return 'script class="ds:1"' in html or "ds:1" in html


def _fetch_and_parse(query):
    """
    Fetch Google Flights with SOCS cookie bypass and parse results.

    Retries on unparsable responses (GDPR consent page, empty body, throttling),
    which is what surfaced as raw `'NoneType' object is not subscriptable` /
    `list index out of range` errors. Raises a clear message if all retries fail.
    Returns [] (via FlightsNotFound) when Google reports genuinely no flights.
    """
    from primp import Client
    from fast_flights.parser import parse
    from fast_flights.exceptions import FlightsNotFound

    last_exc = None
    for attempt in range(FETCH_RETRIES):
        if attempt:
            time.sleep(FETCH_BACKOFF[min(attempt - 1, len(FETCH_BACKOFF) - 1)])

        # Fresh client each attempt → new TLS fingerprint, dodges soft blocks.
        c = Client(impersonate="random", impersonate_os="macos", referer=True, cookie_store=True)
        resp = c.get(
            "https://www.google.com/travel/flights/search",
            params=query.params(),
            headers={"Cookie": CONSENT_COOKIE},
        )
        html = resp.text or ""

        if not _looks_parsable(html):
            last_exc = "unparsable response (consent page / empty body)"
            logger.warning(f"Fetch attempt {attempt + 1}/{FETCH_RETRIES}: {last_exc}")
            continue

        try:
            return parse(html)
        except FlightsNotFound:
            # Google explicitly says no flights — not a transient error.
            return None
        except Exception as e:  # parser choked on an unexpected payload shape
            last_exc = f"parse failed ({type(e).__name__}: {e})"
            logger.warning(f"Fetch attempt {attempt + 1}/{FETCH_RETRIES}: {last_exc}")
            continue

    raise RuntimeError(
        f"Google returned an unusable page (throttling probable) after {FETCH_RETRIES} attempts "
        f"[last: {last_exc}]"
    )


# ── Result formatting ─────────────────────────────────────────

def _format_results(result, from_airport: str, to_airport: str) -> list[dict]:
    """Convert fast-flights v3 ResultList to clean dicts. Tolerates a None result."""
    if result is None:
        return []

    def _ints(seq, length):
        # Coerce each element to int, None/missing → 0, pad/truncate to `length`.
        seq = list(seq or [])
        out = [(int(x) if x is not None else 0) for x in seq[:length]]
        return out + [0] * (length - len(out))

    def fmt_dt(dt):
        d = _ints(dt.date, 3)
        t = _ints(dt.time, 2)
        return f"{d[0]:04d}-{d[1]:02d}-{d[2]:02d} {t[0]:02d}:{t[1]:02d}"

    flights = []
    for group in result:
        legs = []
        for leg in group.flights:
            legs.append({
                "from": leg.from_airport.code,
                "to": leg.to_airport.code,
                "departure": fmt_dt(leg.departure),
                "arrival": fmt_dt(leg.arrival),
                "duration_min": leg.duration,
                "airline": group.airlines[0] if group.airlines else None,
                "plane": leg.plane_type,
            })

        n_legs = len(group.flights)
        flights.append({
            "price_total": group.price,
            "currency": "EUR",
            "airlines": group.airlines,
            "stops": max(n_legs - 1, 0),
            "total_duration_min": sum(l.duration for l in group.flights),
            "legs": legs,
            "from": from_airport,
            "to": to_airport,
        })

    flights.sort(key=lambda x: (x["price_total"] is None, x["price_total"] or float("inf")))
    return flights


# ── Airport resolution helpers ────────────────────────────────

def _norm(s: str) -> str:
    """Lowercase + strip accents for accent/case-insensitive matching."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.casefold().strip()


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# ── Tools ─────────────────────────────────────────────────────

@mcp.tool()
def find_airport(query: str, limit: int = 8) -> str:
    """
    Resolve a city name or airport name into IATA airport codes.
    Use this FIRST when you don't know the IATA code to pass to search_flights.

    Args:
        query: City, airport name, IATA code or country (e.g. "Barcelone", "Nice", "JFK")
        limit: Max results (default 8)
    """
    q = _norm(query)
    if not q:
        return json.dumps({"success": False, "error": "empty query", "results": []}, ensure_ascii=False)

    # Candidate query terms: the raw query plus any French-exonym alias.
    terms = {q}
    if q in FR_CITY_ALIASES:
        terms.add(FR_CITY_ALIASES[q])

    scored = []
    for a in AIRPORTS.values():
        iata = _norm(a["iata"])
        city = _norm(a["city"])
        name = _norm(a["name"])
        country = _norm(a["country"])
        name_words = name.split()

        rank = None
        for t in terms:
            if t == iata:
                rank = 0
            elif t == city:
                rank = min(rank if rank is not None else 9, 1)
            elif city.startswith(t) or any(w.startswith(t) for w in name_words):
                rank = min(rank if rank is not None else 9, 2)
            elif t in city:
                rank = min(rank if rank is not None else 9, 3)
            elif t == country:
                rank = min(rank if rank is not None else 9, 4)
            elif difflib.SequenceMatcher(None, t, city).ratio() >= FUZZY_THRESHOLD:
                rank = min(rank if rank is not None else 9, 5)

        if rank is not None:
            scored.append((rank, a))

    scored.sort(key=lambda x: (x[0], x[1]["city"], x[1]["name"]))
    results = [
        {
            "iata": a["iata"],
            "name": a["name"],
            "city": a["city"],
            "country": a["country"],
            "lat": a["lat"],
            "lon": a["lon"],
        }
        for _, a in scored[:limit]
    ]
    return json.dumps(
        {"success": True, "count": len(results), "results": results},
        ensure_ascii=False, indent=2,
    )


@mcp.tool()
def find_airports_near(lat: float, lon: float, radius_km: float = 150, limit: int = 8) -> str:
    """
    Find airports near a geographic coordinate, sorted by distance.
    Useful for geolocated departure-airport selection.

    Args:
        lat: Latitude in decimal degrees
        lon: Longitude in decimal degrees
        radius_km: Search radius in kilometers (default 150)
        limit: Max results (default 8)
    """
    found = []
    for a in AIRPORTS.values():
        try:
            d = _haversine_km(lat, lon, float(a["lat"]), float(a["lon"]))
        except (TypeError, ValueError):
            continue
        if d <= radius_km:
            found.append((d, a))

    found.sort(key=lambda x: x[0])
    results = [
        {
            "iata": a["iata"],
            "name": a["name"],
            "city": a["city"],
            "country": a["country"],
            "distance_km": round(d, 1),
        }
        for d, a in found[:limit]
    ]
    return json.dumps(
        {"success": True, "count": len(results), "results": results},
        ensure_ascii=False, indent=2,
    )


def _parse_csv(s: str) -> list[str]:
    """Split a comma-separated string into a clean list of upper-case tokens."""
    return [x.strip().upper() for x in s.split(",") if x.strip()]


def _run_search_round(
    departures: list[str],
    to_airport: str,
    departure_date: str,
    return_date: str = "",
    *,
    seat: str = "economy",
    adults: int = 2,
    children: int = 2,
    infants_in_seat: int = 0,
    infants_on_lap: int = 0,
    max_stops=None,
    airlines=None,
    currency: str = "EUR",
    language: str = "fr",
):
    """
    Core search: query each departure airport for one route/date and return
    (flights, last_error). Shared by search_flights, search_flexible_dates and
    compare_destinations. Spaces requests apart to avoid Google throttling.
    """
    from fast_flights import FlightQuery, Passengers, create_query

    all_results = []
    last_error = None

    for i, dep in enumerate(departures):
        if i:
            time.sleep(INTER_AIRPORT_DELAY)
        try:
            logger.info(f"Searching {dep} → {to_airport} ({departure_date}{' / ' + return_date if return_date else ''})")

            flight_queries = [FlightQuery(date=departure_date, from_airport=dep, to_airport=to_airport, airlines=airlines)]
            trip = "one-way"
            if return_date:
                flight_queries.append(FlightQuery(date=return_date, from_airport=to_airport, to_airport=dep, airlines=airlines))
                trip = "round-trip"

            query = create_query(
                flights=flight_queries,
                seat=seat,
                trip=trip,
                passengers=Passengers(adults=adults, children=children, infants_in_seat=infants_in_seat, infants_on_lap=infants_on_lap),
                language=language,
                currency=currency,
                max_stops=max_stops,
            )

            result = _fetch_and_parse(query)
            flights = _format_results(result, dep, to_airport)
            for f in flights:
                f["currency"] = currency
            if flights:
                all_results.extend(flights)
                logger.info(f"Found {len(flights)} options from {dep}")

        except Exception as e:
            last_error = f"{dep}: {e}"
            logger.error(f"Error searching from {dep}: {e}")

    all_results.sort(key=lambda x: (x["price_total"] is None, x["price_total"] or float("inf")))
    return all_results, last_error


@mcp.tool()
def search_flights(
    to_airport: str,
    departure_date: str,
    return_date: str = "",
    from_airports: str = "",
    adults: int = 2,
    children: int = 2,
    infants_in_seat: int = 0,
    infants_on_lap: int = 0,
    seat: str = "economy",
    max_stops: int = -1,
    airlines: str = "",
    currency: str = "EUR",
    language: str = "fr",
) -> str:
    """
    Search Google Flights for the best prices.
    Tries multiple departure airports (default: Nice NCE, Marseille MRS).

    All airports must be IATA codes. If you only know a city name, call find_airport
    (or find_airports_near) first to resolve it.

    Args:
        to_airport: IATA destination code(s), comma-separated for multi-airport cities (e.g. "BCN" or "LHR,LGW,STN")
        departure_date: Departure date YYYY-MM-DD
        return_date: Return date YYYY-MM-DD (empty for one-way)
        from_airports: Comma-separated IATA departure codes (default: NCE,MRS)
        adults: Number of adults (default 2)
        children: Number of children (default 2)
        infants_in_seat: Infants with seat (default 0)
        infants_on_lap: Infants on lap (default 0)
        seat: Seat class: economy, premium-economy, business, first
        max_stops: Max stops: -1 = no limit (default), 0 = direct only, 1 = max one stop
        airlines: Comma-separated IATA airline codes to restrict to (e.g. "AF,U2"); empty = all
        currency: ISO currency code (default EUR)
        language: Language code (default fr)
    """
    departures = _parse_csv(from_airports) if from_airports else DEFAULT_DEPARTURES
    arrivals = _parse_csv(to_airport)
    al = _parse_csv(airlines) or None
    ms = None if max_stops < 0 else max_stops

    if not arrivals:
        return json.dumps({"success": False, "flights": [], "error": "to_airport required"})

    all_results = []
    last_error = None
    for idx, dest in enumerate(arrivals):
        if idx:
            time.sleep(INTER_AIRPORT_DELAY)  # space out across destinations too
        flights, err = _run_search_round(
            departures, dest, departure_date, return_date,
            seat=seat, adults=adults, children=children,
            infants_in_seat=infants_in_seat, infants_on_lap=infants_on_lap,
            max_stops=ms, airlines=al, currency=currency, language=language,
        )
        all_results.extend(flights)
        if err:
            last_error = err

    all_results.sort(key=lambda x: (x["price_total"] is None, x["price_total"] or float("inf")))

    if all_results:
        return json.dumps({
            "success": True,
            "count": len(all_results),
            "flights": all_results[:20],
            "searched_from": departures,
            "searched_to": arrivals,
            "warning": last_error,  # non-null if some routes failed transiently
        }, ensure_ascii=False, indent=2)
    else:
        return json.dumps({
            "success": False,
            "flights": [],
            "error": last_error or "No flights found",
            "searched_from": departures,
            "searched_to": arrivals,
        }, ensure_ascii=False, indent=2)


@mcp.tool()
def search_multi_city(
    legs: str,
    adults: int = 2,
    children: int = 2,
    seat: str = "economy",
    max_stops: int = -1,
    currency: str = "EUR",
    language: str = "fr",
) -> str:
    """
    Search a multi-city itinerary (legs on different dates) on Google Flights,
    priced as one combined trip.

    When to use: pick this over search_flights when the journey is NOT a simple
    one-way or round-trip — e.g. NCE->BCN on Aug 1, then BCN->LIS on Aug 8. For
    one-way/round-trip use search_flights; to compare prices across several
    destinations use compare_destinations.

    All airports must be IATA codes; if you only know a city name, call
    find_airport first. Legs are flown in the order given (chronological). Read
    only, no booking. Returns at most 20 flights sorted by price; Google Flights
    may throttle rapid successive calls.

    Args:
        legs: JSON array of legs in order; each item is an object with "from"
            (IATA departure), "to" (IATA destination) and "date" (YYYY-MM-DD).
            Example: [{"from":"NCE","to":"BCN","date":"2026-08-01"},{"from":"BCN","to":"LIS","date":"2026-08-08"}]
        adults: Number of adult passengers, age 12+ (default 2)
        children: Number of child passengers, ages 2-11 (default 2)
        seat: Cabin class: one of economy, premium-economy, business, first (default economy)
        max_stops: Max stops per leg: -1 = no limit (default), 0 = direct only, 1 = at most one stop
        currency: ISO 4217 currency code for the returned prices (default EUR)
        language: ISO 639-1 language code for the results (default fr)
    """
    from fast_flights import FlightQuery, Passengers, create_query

    try:
        leg_list = json.loads(legs)
    except json.JSONDecodeError:
        return json.dumps({"success": False, "error": "Invalid JSON for legs parameter"})

    if not isinstance(leg_list, list) or not leg_list:
        return json.dumps({"success": False, "error": "legs must be a non-empty JSON array"})

    try:
        flight_queries = [
            FlightQuery(date=leg["date"], from_airport=leg["from"], to_airport=leg["to"])
            for leg in leg_list
        ]
    except (KeyError, TypeError):
        return json.dumps({"success": False, "error": "each leg needs 'from', 'to' and 'date'"})

    query = create_query(
        flights=flight_queries,
        seat=seat,
        trip="multi-city",
        passengers=Passengers(adults=adults, children=children),
        language=language,
        currency=currency,
        max_stops=(None if max_stops < 0 else max_stops),
    )

    try:
        result = _fetch_and_parse(query)
        flights = _format_results(result, leg_list[0]["from"], leg_list[-1]["to"])
        for f in flights:
            f["currency"] = currency
        return json.dumps({"success": True, "count": len(flights), "flights": flights[:20]}, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
def search_flexible_dates(
    to_airport: str,
    date_from: str,
    date_to: str,
    from_airports: str = "",
    trip_length_days: int = 0,
    weekends_only: bool = False,
    adults: int = 2,
    children: int = 2,
    seat: str = "economy",
    max_stops: int = -1,
    airlines: str = "",
    currency: str = "EUR",
    language: str = "fr",
) -> str:
    """
    Find the cheapest departure day over a date range. Ideal for flexible holiday planning.
    Runs one search per candidate date (throttled) — keep ranges reasonable.

    Args:
        to_airport: IATA destination code
        date_from: Earliest departure date YYYY-MM-DD
        date_to: Latest departure date YYYY-MM-DD
        from_airports: Comma-separated IATA departure codes (default: NCE,MRS)
        trip_length_days: 0 = one-way (default); >0 = round-trip with return = departure + N days
        weekends_only: If true, only consider Friday/Saturday departures
        adults: Number of adults
        children: Number of children
        seat: Seat class
        max_stops: -1 = no limit (default), 0 = direct only
        airlines: Comma-separated IATA airline codes to restrict to; empty = all
        currency: ISO currency code (default EUR)
        language: Language code (default fr)
    """
    try:
        d0 = date.fromisoformat(date_from)
        d1 = date.fromisoformat(date_to)
    except ValueError:
        return json.dumps({"success": False, "error": "dates must be YYYY-MM-DD"})
    if d1 < d0:
        return json.dumps({"success": False, "error": "date_to must be >= date_from"})

    candidates = [d0 + timedelta(days=i) for i in range((d1 - d0).days + 1)]
    if weekends_only:
        candidates = [d for d in candidates if d.weekday() in (4, 5)]
    if not candidates:
        return json.dumps({"success": False, "error": "no candidate dates in range"})

    note = None
    if len(candidates) > MAX_FLEX_DATES:
        step = len(candidates) / MAX_FLEX_DATES
        sampled = [candidates[int(i * step)] for i in range(MAX_FLEX_DATES)]
        note = f"{len(candidates)} dates in range, sampled {MAX_FLEX_DATES} evenly: {[d.isoformat() for d in sampled]}"
        candidates = sampled

    departures = _parse_csv(from_airports) if from_airports else DEFAULT_DEPARTURES
    al = _parse_csv(airlines) or None
    dest = to_airport.strip().upper()
    ms = None if max_stops < 0 else max_stops

    per_date = []
    errors = []
    for idx, d in enumerate(candidates):
        if idx:
            time.sleep(INTER_AIRPORT_DELAY)
        dep_str = d.isoformat()
        ret_str = (d + timedelta(days=trip_length_days)).isoformat() if trip_length_days > 0 else ""
        flights, err = _run_search_round(
            departures, dest, dep_str, ret_str,
            seat=seat, adults=adults, children=children,
            max_stops=ms, airlines=al, currency=currency, language=language,
        )
        if flights:
            best = flights[0]
            per_date.append({
                "departure_date": dep_str,
                "return_date": ret_str or None,
                "best_price": best["price_total"],
                "currency": currency,
                "from": best["from"],
                "to": best["to"],
                "airline": best.get("airlines", [None])[0] if best.get("airlines") else None,
                "stops": best["stops"],
            })
        elif err:
            errors.append(f"{dep_str}: {err}")

    per_date.sort(key=lambda x: (x["best_price"] is None, x["best_price"] or float("inf")))

    return json.dumps({
        "success": bool(per_date),
        "count": len(per_date),
        "cheapest": per_date[0] if per_date else None,
        "by_date": per_date,
        "searched_from": departures,
        "note": note,
        "errors": errors or None,
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def compare_destinations(
    to_airports: str,
    departure_date: str,
    return_date: str = "",
    from_airports: str = "",
    adults: int = 2,
    children: int = 2,
    seat: str = "economy",
    max_stops: int = -1,
    airlines: str = "",
    currency: str = "EUR",
    language: str = "fr",
) -> str:
    """
    Compare the cheapest price to several destinations from the same departure airport(s).
    Great for "where can we go cheaply" inspiration searches. One search per destination (throttled).

    Args:
        to_airports: Comma-separated IATA destination codes (e.g. "BCN,LIS,TFS")
        departure_date: Departure date YYYY-MM-DD
        return_date: Return date YYYY-MM-DD (empty for one-way)
        from_airports: Comma-separated IATA departure codes (default: NCE,MRS)
        adults: Number of adults
        children: Number of children
        seat: Seat class
        max_stops: -1 = no limit (default), 0 = direct only
        airlines: Comma-separated IATA airline codes to restrict to; empty = all
        currency: ISO currency code (default EUR)
        language: Language code (default fr)
    """
    dests = _parse_csv(to_airports)
    if not dests:
        return json.dumps({"success": False, "error": "to_airports must list at least one IATA code"})

    note = None
    if len(dests) > MAX_DESTINATIONS:
        note = f"{len(dests)} destinations requested, capped to first {MAX_DESTINATIONS}: {dests[MAX_DESTINATIONS:]} skipped"
        dests = dests[:MAX_DESTINATIONS]

    departures = _parse_csv(from_airports) if from_airports else DEFAULT_DEPARTURES
    al = _parse_csv(airlines) or None
    ms = None if max_stops < 0 else max_stops

    ranked = []
    errors = []
    for idx, dest in enumerate(dests):
        if idx:
            time.sleep(INTER_AIRPORT_DELAY)
        flights, err = _run_search_round(
            departures, dest, departure_date, return_date,
            seat=seat, adults=adults, children=children,
            max_stops=ms, airlines=al, currency=currency, language=language,
        )
        if flights:
            best = flights[0]
            ranked.append({
                "to": dest,
                "best_price": best["price_total"],
                "currency": currency,
                "from": best["from"],
                "airline": best.get("airlines", [None])[0] if best.get("airlines") else None,
                "stops": best["stops"],
                "total_duration_min": best["total_duration_min"],
            })
        elif err:
            errors.append(f"{dest}: {err}")

    ranked.sort(key=lambda x: (x["best_price"] is None, x["best_price"] or float("inf")))

    return json.dumps({
        "success": bool(ranked),
        "count": len(ranked),
        "cheapest": ranked[0] if ranked else None,
        "destinations": ranked,
        "searched_from": departures,
        "note": note,
        "errors": errors or None,
    }, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
