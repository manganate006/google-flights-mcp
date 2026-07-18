<div align="center">

# Google Flights MCP

**MCP server for searching Google Flights with real-time prices — from your AI assistant, no API key and no browser.**

[![License: MIT](https://img.shields.io/github/license/manganate006/google-flights-mcp)](LICENSE)
![Python](https://img.shields.io/badge/python-%E2%89%A53.10-brightgreen)
![fast-flights](https://img.shields.io/badge/fast--flights-3.x-blue)
![MCP](https://img.shields.io/badge/MCP-1.0%2B-purple)

**[Installation](#installation) · [Tools](#tools) · [Examples](#examples) · [Limitations](#limitations) · [🇫🇷 Français](README.fr.md)**

</div>

## Overview

This [MCP](https://modelcontextprotocol.io) server searches Google Flights and returns live prices as **6 tools** your assistant can call. No API key, no headless browser — it decodes Google's own query format directly. Ask in natural language:

> **You:** Compare round-trip prices from Nice or Marseille to Tenerife, July 29 – August 12, for 2 adults and 2 kids.
>
> **Assistant:** *(calls `compare_destinations`)*
> Cheapest: **Tenerife (TFS) €612** from NCE, 1 stop, 8 h 40 — Vueling. Marseille was €40 more. Full breakdown by date below.

## Requirements

- **Python ≥ 3.10**
- Any **MCP client** — Claude Code, Claude Desktop, Cursor…

## Installation

```bash
git clone https://github.com/manganate006/google-flights-mcp
cd google-flights-mcp
python3 -m venv venv
./venv/bin/pip install "fast-flights>=3.0" "mcp[cli]>=1.0.0" "airportsdata>=20240101"
```

### Claude Code

```bash
claude mcp add google-flights -- \
  /absolute/path/to/google-flights-mcp/venv/bin/python \
  /absolute/path/to/google-flights-mcp/server.py
```

### Claude Desktop / Cursor

Add to `claude_desktop_config.json` (or your client's MCP config):

```json
{
  "mcpServers": {
    "google-flights": {
      "command": "/absolute/path/to/google-flights-mcp/venv/bin/python",
      "args": ["/absolute/path/to/google-flights-mcp/server.py"]
    }
  }
}
```

**No environment variables, no API key needed.**

## Tools

6 tools — full parameters in **[docs/TOOLS.md](docs/TOOLS.md)**.

| Tool | Purpose |
|---|---|
| `find_airport` | Resolve a city/name to IATA code(s) — call this **first** (handles exonyms, fuzzy spelling), offline |
| `find_airports_near` | Airports near a `lat`/`lon`, sorted by distance |
| `search_flights` | One-way / round-trip; multiple departure **and** arrival airports; stop/airline/currency filters |
| `search_multi_city` | Multi-leg itineraries |
| `search_flexible_dates` | Cheapest departure day over a date range (throttled, ≤ 14 dates) |
| `compare_destinations` | Rank several destinations by price from one origin (≤ 8) |

## Examples

- "Flights from Nice to Lisbon on August 1st for 2 adults and 2 children"
- "Compare Nice vs Marseille to Tenerife, round-trip July 29 – August 12"
- "Cheapest day to fly Nice → Barcelona between Aug 1 and Aug 15, direct only"
- "Multi-city: Nice → Barcelona Aug 1, Barcelona → Lisbon Aug 8"

Sample `search_flights` result (trimmed):

```json
{
  "success": true,
  "count": 7,
  "flights": [
    { "price_total": 836, "currency": "EUR", "airlines": ["Vueling"],
      "stops": 1, "total_duration_min": 215,
      "legs": [{ "from": "NCE", "to": "LIS", "departure": "2026-08-01 22:30",
                 "duration_min": 215, "plane": "Airbus A320" }] }
  ]
}
```

## How it works

Google Flights is a JavaScript SPA, so scraping the HTML doesn't work. This server:

1. uses **fast-flights v3** to encode queries as Protocol Buffers (the `tfs=` URL parameter);
2. fetches with **primp** (Rust HTTP client with TLS fingerprinting);
3. injects a **`SOCS` consent cookie** to bypass the EU GDPR "Before you continue" wall that otherwise blocks EU-based servers — the same acceptance your browser sends, without the click;
4. parses the flight data from the embedded `<script class="ds:1">` payload.

## Limitations

- **Rate limiting** — Google may throttle if called too often; space out searches
- **Prices** are real-time but may differ slightly from booking sites (caching)
- **Currency** defaults to EUR (per-search `currency` parameter)
- **Search-only** — no booking; book on the airline's site

## License

[MIT](LICENSE)
