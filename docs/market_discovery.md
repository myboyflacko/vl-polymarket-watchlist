# Market Discovery

## Zweck

Market Discovery ist der naechste geplante Feature-Schritt. Der Schritt
entscheidet, welche Markets fuer die nachgelagerten Systeme interessant sind.

Alle spaeteren Schritte sollen mit einem stabilen, normalisierten
Market-Schema arbeiten, unabhaengig davon, aus welcher Quelle ein Market
gefunden wurde.

Der aktuelle Fokus ist `whale_markets`: Markets werden aus der bestehenden
Whale-Liste abgeleitet.

## Warum nicht Ingestion?

`ingestion` beschreibt eher das reine Laden oder Einsammeln von Rohdaten.
`market_discovery` macht mehr als das:

- Quellen auswerten
- relevante Markets ableiten
- doppelte Markets zusammenfuehren
- Signale pro Market aggregieren
- einen stabilen Output fuer Strategy, Risk und Execution bereitstellen

Der Name `market_discovery` beschreibt deshalb besser den fachlichen Schritt:
Welche Markets sollen ueberhaupt weiter betrachtet werden?

## Runtime-Grenze

Die fachliche Reihenfolge bleibt:

```text
track_whales -> market_discovery -> strategy -> risk -> execution -> runtime mode
```

Die technische Kopplung laeuft aber nicht mehr ueber direkte Imports zwischen
Pipeline-Schritten. Neue Schritte werden als Bindings an den Runtime-Bus
gehaengt:

```text
DomainEvent -> Runtime -> BindingRegistry -> Binding -> DomainEvent
```

`track_whales` kann weiter direkt ausgefuehrt werden, ist aber auch ueber
`PolymarketWhaleDiscoveryBinding` event-getrieben anschliessbar. Market Discovery
soll spaeter genauso angebunden werden: ein Binding konsumiert Whale-Events oder
persistierte Whale-Snapshots und produziert Market-Candidate-Events.

`market_discovery` nutzt diese Whale-Daten als Input und erzeugt daraus
normierte Market-Kandidaten.

Alles nach `market_discovery` soll nicht mehr direkt mit rohen Whale-JSONs
arbeiten.

## Stabiles Output-Schema

Der zentrale Vertrag von `market_discovery` ist ein spaeteres Schema wie
`MarketCandidate`.

Ein Market-Kandidat sollte mindestens folgende Informationen tragen:

- stabile Market-ID
- Titel oder Question, falls vorhanden
- Quelle, zum Beispiel `whale_markets`
- Discovery-Score oder Prioritaet
- Anzahl unterstuetzender Whales
- aggregierte Whale-Exposure
- Liste der unterstuetzenden Wallets
- normalisierte Signale
- optionale Metadaten fuer Analyse und Debugging

Beispielhafte Richtung:

```python
class MarketCandidate(BaseModel):
    market_id: str
    title: str | None = None
    source: str
    discovery_score: float = 0.0
    whale_count: int = 0
    total_whale_exposure: float = 0.0
    supporting_whales: list[str] = Field(default_factory=list)
    signals: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
```

Die konkrete ID-Frage sollte erst entschieden werden, wenn klar ist, welche
Polymarket-ID aus den Positionsdaten dauerhaft am stabilsten ist.

## Aktuelle Source: Whale Markets

`whale_markets` ist die erste geplante Discovery-Source.

Aufgabe:

- Whale-Liste lesen
- offene Whale-Positionen auswerten
- Markets aus diesen Positionen ableiten
- gleiche Markets ueber mehrere Whales deduplizieren
- Exposure und weitere Signale pro Market aggregieren
- `MarketCandidate`-Objekte zurueckgeben

Die Source sollte keine Strategy-Entscheidungen treffen. Sie liefert nur die
Markets und ihre Discovery-Signale.

## Spaetere Erweiterbarkeit

Weitere Sources koennen spaeter neben `whale_markets` ergaenzt werden:

- `volume_markets`
- `news_markets`
- `manual_watchlist`
- `arbitrage_markets`
- `trending_markets`

Alle Sources sollen denselben Output liefern. Dadurch muessen Strategy,
Backtesting, Paper Trading und Live Trading nicht wissen, woher ein Market
urspruenglich kam.

## Zielstruktur

Der Repo-Aufbau trennt bewusst Framework, Pipeline-Vertraege und externe Systeme:

```text
src/void_liquidity/
  core/
    events.py          # DomainEvent und EventBus
    bindings.py         # BindingSpec, BindingRegistry, Binding-Protokoll
    runtime.py         # kleine Runtime fuer Event-Routing

  pipeline/
    discovery/
      whales/
        events.py      # generische Whale-Discovery-Events

  bindings/
    polymarket/
      discovery/
        whales.py

  adapters/
    polymarket/
      api/             # HTTP/API-Details
      discovery/
        whales/        # aktuell whale-basierte Discovery
```

Market Discovery sollte spaeter als eigener Pipeline-Vertrag unter
`pipeline/markets/` entstehen. Die konkrete Polymarket-Ableitung aus
Whale-Daten kann dann unter `adapters/polymarket/markets/` liegen
und auf `polymarket.discovery.whales.discovered` reagieren.

## Spaetere Verantwortlichkeiten

`pipeline/markets/models.py`

- definiert das stabile Output-Schema
- enthaelt keine Polymarket-API-Logik

`pipeline/markets/sources.py`

- definiert das Interface fuer Discovery-Sources
- jede Source liefert `list[MarketCandidate]`

`pipeline/markets/whale_markets.py`

- implementiert die erste konkrete Source
- nutzt Whale-Daten als Input
- erzeugt normierte Market-Kandidaten

`bindings/polymarket/markets.py`

- orchestriert eine oder mehrere Sources
- dedupliziert Markets
- sortiert oder priorisiert die Ergebnisse
- publiziert finale Market-Kandidaten als Domain-Events

## Nicht-Ziele fuer den ersten Schritt

- keine Strategy-Logik
- keine Execution-Logik
- kein Risk Management
- kein Backtesting
- kein Paper Trading
- kein Live Trading
- keine echten Orders
- keine Funds-Bewegung

`market_discovery` beantwortet nur die Frage:

```text
Welche Markets sind interessant genug, um sie an die naechste Pipeline-Stufe
weiterzugeben?
```
