<a name="english"></a>

---

[English](#english) &nbsp;|&nbsp; [Français](#français)

---

# Google Flights MCP Server

![Python](https://img.shields.io/badge/python-%3E%3D3.10-brightgreen)
![fast-flights](https://img.shields.io/badge/fast--flights-3.x-blue)
![MCP](https://img.shields.io/badge/MCP-1.0%2B-purple)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

A **Model Context Protocol (MCP)** server for searching Google Flights with real-time pricing. Uses [fast-flights](https://pypi.org/project/fast-flights/) v3 with an automatic GDPR consent bypass.

No API key needed. No browser required. Just flight prices.

---

## Features

- **6 MCP tools**: flight search, multi-city, flexible-date search, destination comparison, and airport resolution
- **Airport resolution** — turn a city name or coordinates into IATA codes (`find_airport`, `find_airports_near`), offline
- **Flexible dates** — find the cheapest departure day over a range (`search_flexible_dates`)
- **Compare destinations** — rank several destinations by price from the same origin (`compare_destinations`)
- **Filters** — direct-only / max stops, specific airlines, currency & language
- Real-time prices from Google Flights
- Multiple departure **and arrival** airports (multi-airport cities like London LHR/LGW/STN)
- **Robust fetching** — automatic retry + throttle spacing when Google returns a consent/empty page
- Detailed results: price, airlines, stops, duration, legs, plane type
- **No API key** — uses fast-flights v3 Protocol Buffer encoding
- **GDPR consent bypass** — works from EU servers without manual cookie acceptance
- Configurable: passengers, seat class, departure airports

---

## Prerequisites

- **Python** >= 3.10
- A **MCP-compatible client**

---

## Quick Start

```bash
# 1. Clone and setup
git clone https://github.com/manganate006/google-flights-mcp
cd google-flights-mcp
python3 -m venv venv
./venv/bin/pip install "fast-flights>=3.0" "mcp[cli]>=1.0.0" "airportsdata>=20240101"

# 2. Add to your MCP client config (see Configuration below)
```

---

## How It Works

Google Flights is a JavaScript SPA — you can't just scrape the HTML. This server uses:

1. **fast-flights v3** to encode search queries as Protocol Buffers (the `tfs=` URL parameter)
2. **primp** (Rust-based HTTP client with TLS fingerprinting) to fetch the page
3. **SOCS cookie injection** to bypass the EU GDPR consent wall that blocks automated requests
4. **fast-flights parser** to extract flight data from the `<script class="ds:1">` embedded JavaScript data

The GDPR consent bypass is the key innovation — without it, EU-based servers get a "Before you continue" page instead of flight results.

---

## Configuration

### `.mcp.json`

```json
{
  "mcpServers": {
    "google-flights": {
      "type": "stdio",
      "command": "/absolute/path/to/google-flights-mcp/venv/bin/python",
      "args": ["/absolute/path/to/google-flights-mcp/server.py"]
    }
  }
}
```

No environment variables needed.

---

## Tools (6)

### `find_airport`

Resolve a city or airport name into IATA code(s). Call this **first** when you don't know the code. Handles common French exonyms (Londres → London) and fuzzy spelling (Barcelone → Barcelona).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | required | City, airport name, IATA code or country |
| `limit` | int | `8` | Max results |

Returns `{success, count, results:[{iata, name, city, country, lat, lon}]}`.

### `find_airports_near`

Find airports near a coordinate, sorted by distance (haversine).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `lat` | float | required | Latitude (decimal degrees) |
| `lon` | float | required | Longitude (decimal degrees) |
| `radius_km` | float | `150` | Search radius (km) |
| `limit` | int | `8` | Max results |

Returns `{success, count, results:[{iata, name, city, country, distance_km}]}`.

### `search_flights`

Search for one-way or round-trip flights. Handles multiple departure **and** arrival airports (pooled and sorted by price). All airports are IATA codes — resolve city names with `find_airport` first.

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

### `search_multi_city`

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

### `search_flexible_dates`

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

### `compare_destinations`

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

---

## Usage Examples

```
Search for flights from Nice to Lisbon on August 1st for 2 adults and 2 children

Compare prices Nice vs Marseille to Tenerife round-trip July 29 to August 12

Find multi-city flights: Nice to Barcelona August 1, Barcelona to Lisbon August 8
```

### Example Output

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
        {
          "from": "NCE",
          "to": "BCN",
          "departure": "2026-08-01 22:30",
          "arrival": "2026-08-01 23:55",
          "duration_min": 85,
          "airline": "Vueling",
          "plane": "Airbus A320"
        },
        {
          "from": "BCN",
          "to": "LIS",
          "departure": "2026-08-02 06:00",
          "arrival": "2026-08-02 07:00",
          "duration_min": 130,
          "airline": "Vueling",
          "plane": "Airbus A321"
        }
      ]
    }
  ]
}
```

---

## GDPR Consent Bypass

When fetching Google Flights from EU servers, Google returns a "Before you continue" consent page instead of flight results. This server injects a `SOCS` cookie that signals consent acceptance, allowing the request to reach the actual flight data.

This is the same mechanism your browser uses after you click "Accept" — we just skip the click.

---

## Limitations

- **Rate limiting**: Google may throttle or block requests if called too frequently. Add delays between searches.
- **Price accuracy**: Prices are real-time from Google Flights but may differ from booking sites due to caching
- **Currency**: Defaults to EUR. Set via the `currency` parameter in `create_query` (code change required)
- **No booking**: This is search-only. Booking must be done on the airline's website.

---

## Contributing

Contributions welcome! Feel free to open an issue or submit a pull request.

---

## License

MIT

---
---

<a name="français"></a>

[English](#english) &nbsp;|&nbsp; [Français](#français)

---

# Google Flights MCP Server

![Python](https://img.shields.io/badge/python-%3E%3D3.10-brightgreen)
![fast-flights](https://img.shields.io/badge/fast--flights-3.x-blue)
![MCP](https://img.shields.io/badge/MCP-1.0%2B-purple)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

Un serveur **Model Context Protocol (MCP)** pour rechercher des vols sur Google Flights avec des prix en temps réel. Utilise [fast-flights](https://pypi.org/project/fast-flights/) v3 avec un bypass automatique du consentement RGPD.

Pas de clé API. Pas de navigateur. Juste les prix des vols.

---

## Fonctionnalités

- **2 outils MCP** : aller simple, aller-retour et multi-destinations
- Prix en temps réel depuis Google Flights
- Support de plusieurs aéroports de départ (défaut : Nice + Marseille)
- Résultats détaillés : prix, compagnies, escales, durée, étapes, type d'avion
- **Pas de clé API** — utilise l'encodage Protocol Buffers de fast-flights v3
- **Bypass du consentement RGPD** — fonctionne depuis les serveurs EU sans acceptation manuelle des cookies
- Configurable : passagers, classe, aéroports de départ

---

## Prérequis

- **Python** >= 3.10
- Un **client compatible MCP**

---

## Démarrage rapide

```bash
# 1. Cloner et installer
git clone https://github.com/manganate006/google-flights-mcp
cd google-flights-mcp
python3 -m venv venv
./venv/bin/pip install "fast-flights>=3.0" "mcp[cli]>=1.0.0" "airportsdata>=20240101"

# 2. Ajouter à la config de votre client MCP (voir Configuration ci-dessous)
```

---

## Comment ça marche

Google Flights est une SPA JavaScript — on ne peut pas simplement scraper le HTML. Ce serveur utilise :

1. **fast-flights v3** pour encoder les requêtes en Protocol Buffers (le paramètre `tfs=` dans l'URL)
2. **primp** (client HTTP Rust avec empreinte TLS) pour récupérer la page
3. **Injection du cookie SOCS** pour contourner le mur de consentement RGPD qui bloque les requêtes automatisées
4. **Le parser fast-flights** pour extraire les données de vol depuis les données JavaScript embarquées dans `<script class="ds:1">`

Le bypass RGPD est l'innovation clé — sans lui, les serveurs basés en EU reçoivent une page "Avant de continuer" au lieu des résultats de vol.

---

## Configuration

### `.mcp.json`

```json
{
  "mcpServers": {
    "google-flights": {
      "type": "stdio",
      "command": "/chemin/absolu/vers/google-flights-mcp/venv/bin/python",
      "args": ["/chemin/absolu/vers/google-flights-mcp/server.py"]
    }
  }
}
```

Aucune variable d'environnement nécessaire.

---

## Outils (2)

### `search_flights`

Rechercher des vols aller simple ou aller-retour.

| Paramètre | Type | Défaut | Description |
|-----------|------|--------|-------------|
| `to_airport` | string | requis | Code IATA destination (ex : `LIS`, `TFS`, `BCN`) |
| `departure_date` | string | requis | `AAAA-MM-JJ` |
| `return_date` | string | `""` | `AAAA-MM-JJ` (vide = aller simple) |
| `from_airports` | string | `"NCE,MRS"` | Codes IATA de départ séparés par virgule |
| `adults` | int | `2` | Nombre d'adultes |
| `children` | int | `2` | Nombre d'enfants |
| `infants_in_seat` | int | `0` | Bébés avec siège |
| `infants_on_lap` | int | `0` | Bébés sur les genoux |
| `seat` | string | `"economy"` | `economy`, `premium-economy`, `business`, `first` |

### `search_multi_city`

Rechercher des vols multi-destinations.

| Paramètre | Type | Défaut | Description |
|-----------|------|--------|-------------|
| `legs` | string | requis | Tableau JSON : `[{"from":"NCE","to":"BCN","date":"2026-08-01"}, ...]` |
| `adults` | int | `2` | Nombre d'adultes |
| `children` | int | `2` | Nombre d'enfants |
| `seat` | string | `"economy"` | Classe |

---

## Exemples d'utilisation

```
Chercher des vols de Nice à Lisbonne le 1er août pour 2 adultes et 2 enfants

Comparer les prix Nice vs Marseille vers Tenerife aller-retour du 29 juillet au 12 août

Trouver des vols multi-city : Nice-Barcelone le 1er août, Barcelone-Lisbonne le 8 août
```

---

## Bypass du consentement RGPD

Lors de la récupération de Google Flights depuis des serveurs EU, Google renvoie une page de consentement "Avant de continuer" au lieu des résultats. Ce serveur injecte un cookie `SOCS` qui signale l'acceptation du consentement, permettant à la requête d'atteindre les données de vol.

C'est le même mécanisme que votre navigateur utilise après avoir cliqué "Accepter" — on saute simplement le clic.

---

## Limitations

- **Rate limiting** : Google peut limiter ou bloquer les requêtes si elles sont trop fréquentes. Ajoutez des délais entre les recherches.
- **Précision des prix** : les prix sont en temps réel depuis Google Flights mais peuvent différer des sites de réservation
- **Devise** : EUR par défaut
- **Pas de réservation** : recherche uniquement. La réservation doit se faire sur le site de la compagnie.

---

## Contribuer

Les contributions sont les bienvenues ! N'hésitez pas à ouvrir une issue ou soumettre une pull request.

---

## Licence

MIT
