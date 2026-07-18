# Google Flights MCP — Tool reference

Full parameters for the 6 tools. Back to the [README](../README.md) · [README FR](../README.fr.md).

All airports are **IATA codes** — resolve city names with `find_airport` first.

## `find_airport`

Resolve a city or airport name into IATA code(s). Call this **first** when you don't know the code. Handles common French exonyms (Londres → London) and fuzzy spelling (Barcelone → Barcelona).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | required | City, airport name, IATA code or country |
| `limit` | int | `8` | Max results |

Returns `{success, count, results:[{iata, name, city, country, lat, lon}]}`.

## `find_airports_near`

Find airports near a coordinate, sorted by distance (haversine).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `lat` | float | required | Latitude (decimal degrees) |
| `lon` | float | required | Longitude (decimal degrees) |
| `radius_km` | float | `150` | Search radius (km) |
| `limit` | int | `8` | Max results |

Returns `{success, count, results:[{iata, name, city, country, distance_km}]}`.

## `search_flights`

Search for one-way or round-trip flights. Handles multiple departure **and** arrival airports (pooled and sorted by price).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `to_airport` | string | required | IATA destination code(s), comma-separated for multi-airport cities (e.g. `BCN` or `LHR,LGW,STN`) |
| `departure_date` | string | required | `YYYY-MM-DD` |
| `return_date` | string | `""` | `YYYY-MM-DD` (empty = one-way) |
| `from_airports` | string | `"NCE,MRS"` | Comma-separated IATA departure codes |
| `adults` | int | `2` | Number of adults |
| `children` | int | `2` | Number of children |
| `infants_in_seat` | int | `0` | Infants with own seat |
| `infants_on_lap` | int | `0` | Infants on lap |
| `seat` | string | `"economy"` | `economy`, `premium-economy`, `business`, `first` |
| `max_stops` | int | `-1` | `-1` = no limit, `0` = direct only, `1` = max one stop |
| `airlines` | string | `""` | Comma-separated IATA airline codes to restrict to (e.g. `"AF,U2"`) |
| `currency` | string | `"EUR"` | ISO currency code |
| `language` | string | `"fr"` | Language code |

## `search_multi_city`

Search for multi-city (multi-leg) flights.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `legs` | string | required | JSON array: `[{"from":"NCE","to":"BCN","date":"2026-08-01"}, ...]` |
| `adults` | int | `2` | Number of adults |
| `children` | int | `2` | Number of children |
| `seat` | string | `"economy"` | Seat class |
| `max_stops` | int | `-1` | `-1` = no limit, `0` = direct only |
| `currency` | string | `"EUR"` | ISO currency code |
| `language` | string | `"fr"` | Language code |

## `search_flexible_dates`

Find the cheapest departure day over a date range (one search per date, throttled; capped at 14 sampled dates).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `to_airport` | string | required | IATA destination code |
| `date_from` | string | required | Earliest departure `YYYY-MM-DD` |
| `date_to` | string | required | Latest departure `YYYY-MM-DD` |
| `from_airports` | string | `"NCE,MRS"` | Comma-separated IATA departure codes |
| `trip_length_days` | int | `0` | `0` = one-way; `>0` = round-trip (return = departure + N days) |
| `weekends_only` | bool | `false` | Only Friday/Saturday departures |
| `adults` / `children` | int | `2` | Passengers |
| `seat` | string | `"economy"` | Seat class |
| `max_stops` | int | `-1` | `-1` = no limit, `0` = direct only |
| `airlines` | string | `""` | Airline filter |
| `currency` / `language` | string | `EUR` / `fr` | Currency / language |

Returns `{cheapest, by_date:[...], note, errors}` sorted by price.

## `compare_destinations`

Rank several destinations by cheapest price from the same origin (one search per destination, throttled; capped at 8).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `to_airports` | string | required | Comma-separated IATA destination codes (e.g. `"BCN,LIS,TFS"`) |
| `departure_date` | string | required | `YYYY-MM-DD` |
| `return_date` | string | `""` | `YYYY-MM-DD` (empty = one-way) |
| `from_airports` | string | `"NCE,MRS"` | Comma-separated IATA departure codes |
| `adults` / `children` | int | `2` | Passengers |
| `seat` | string | `"economy"` | Seat class |
| `max_stops` | int | `-1` | `-1` = no limit, `0` = direct only |
| `airlines` | string | `""` | Airline filter |
| `currency` / `language` | string | `EUR` / `fr` | Currency / language |

Returns `{cheapest, destinations:[...], note, errors}` sorted by price.

## Full result shape (`search_flights`)

```json
{
  "success": true,
  "count": 7,
  "flights": [
    {
      "price_total": 836,
      "currency": "EUR",
      "airlines": ["Vueling"],
      "stops": 1,
      "total_duration_min": 215,
      "legs": [
        { "from": "NCE", "to": "BCN", "departure": "2026-08-01 22:30", "arrival": "2026-08-01 23:55", "duration_min": 85, "airline": "Vueling", "plane": "Airbus A320" },
        { "from": "BCN", "to": "LIS", "departure": "2026-08-02 06:00", "arrival": "2026-08-02 07:00", "duration_min": 130, "airline": "Vueling", "plane": "Airbus A321" }
      ]
    }
  ]
}
```
