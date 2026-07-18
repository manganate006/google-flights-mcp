<div align="center">

# Google Flights MCP

**Serveur MCP pour rechercher des vols sur Google Flights avec des prix en temps réel — depuis votre assistant IA, sans clé API ni navigateur.**

[![License: MIT](https://img.shields.io/github/license/manganate006/google-flights-mcp)](LICENSE)
![Python](https://img.shields.io/badge/python-%E2%89%A53.10-brightgreen)
![fast-flights](https://img.shields.io/badge/fast--flights-3.x-blue)
![MCP](https://img.shields.io/badge/MCP-1.0%2B-purple)

**[Installation](#installation) · [Outils](#outils) · [Exemples](#exemples) · [Limites](#limites) · [🇬🇧 English](README.md)**

</div>

## Aperçu

Ce serveur [MCP](https://modelcontextprotocol.io) interroge Google Flights et renvoie des prix en direct via **6 outils** que votre assistant peut appeler. Pas de clé API, pas de navigateur headless — il décode le propre format de requête de Google. Vous demandez en langage naturel :

> **Vous :** Compare les prix aller-retour depuis Nice ou Marseille vers Tenerife, du 29 juillet au 12 août, pour 2 adultes et 2 enfants.
>
> **Assistant :** *(appelle `compare_destinations`)*
> Le moins cher : **Tenerife (TFS) 612 €** depuis NCE, 1 escale, 8 h 40 — Vueling. Marseille coûtait 40 € de plus. Détail par date ci-dessous.

## Prérequis

- **Python ≥ 3.10**
- Un **client compatible MCP** — Claude Code, Claude Desktop, Cursor…

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
  /chemin/absolu/vers/google-flights-mcp/venv/bin/python \
  /chemin/absolu/vers/google-flights-mcp/server.py
```

### Claude Desktop / Cursor

Ajoutez à `claude_desktop_config.json` (ou à la config MCP de votre client) :

```json
{
  "mcpServers": {
    "google-flights": {
      "command": "/chemin/absolu/vers/google-flights-mcp/venv/bin/python",
      "args": ["/chemin/absolu/vers/google-flights-mcp/server.py"]
    }
  }
}
```

**Aucune variable d'environnement, aucune clé API.**

## Outils

6 outils — paramètres complets dans **[docs/TOOLS.md](docs/TOOLS.md)**.

| Outil | Rôle |
|---|---|
| `find_airport` | Convertir une ville/un nom en code(s) IATA — à appeler **en premier** (exonymes, orthographe approximative), hors ligne |
| `find_airports_near` | Aéroports proches d'un `lat`/`lon`, tri par distance |
| `search_flights` | Aller simple / aller-retour ; plusieurs aéroports de départ **et** d'arrivée ; filtres escales/compagnies/devise |
| `search_multi_city` | Itinéraires multi-étapes |
| `search_flexible_dates` | Jour de départ le moins cher sur une plage (throttlé, ≤ 14 dates) |
| `compare_destinations` | Classer plusieurs destinations par prix depuis une origine (≤ 8) |

## Exemples

- « Vols de Nice à Lisbonne le 1er août pour 2 adultes et 2 enfants »
- « Compare Nice vs Marseille vers Tenerife, aller-retour du 29 juillet au 12 août »
- « Jour le moins cher pour Nice → Barcelone entre le 1er et le 15 août, direct uniquement »
- « Multi-city : Nice → Barcelone le 1er août, Barcelone → Lisbonne le 8 août »

## Comment ça marche

Google Flights est une SPA JavaScript : scraper le HTML ne suffit pas. Ce serveur :

1. encode les requêtes en Protocol Buffers avec **fast-flights v3** (le paramètre `tfs=` de l'URL) ;
2. récupère la page avec **primp** (client HTTP Rust à empreinte TLS) ;
3. injecte un **cookie de consentement `SOCS`** pour contourner le mur RGPD « Avant de continuer » qui bloque les serveurs EU — la même acceptation que votre navigateur, sans le clic ;
4. extrait les données de vol du payload `<script class="ds:1">`.

## Limites

- **Rate limiting** — Google peut limiter si appelé trop souvent ; espacez les recherches
- **Prix** en temps réel mais pouvant légèrement différer des sites de réservation (cache)
- **Devise** EUR par défaut (paramètre `currency` par recherche)
- **Recherche uniquement** — pas de réservation ; réservez sur le site de la compagnie

## Licence

[MIT](LICENSE)
