# Trade-First Whale Metrics

Dieser Ansatz nutzt `leaderboard` als primaere 30-Tage-Performance-Quelle und
`trades` als primaere Verhaltensquelle. `closed_positions` wird bewusst nicht
verwendet, weil die Metriken fuer unser 30-Tage-Fenster bereits ueber das
Leaderboard kommen und Trade-Aktivitaet genauer ueber Trades ableitbar ist.

Der Service platziert keine Orders, fuehrt keine Live-Trades aus und bewegt
keine Funds.

## Ansatz

1. Leaderboard mit `timePeriod=MONTH` holen.
2. Kandidaten ueber Monats-PnL und Monats-Volumen vorfiltern.
3. Fuer jeden Kandidaten Trades der letzten 30 Tage holen.
4. Aus den Trades Aktivitaet, Recency, Volumen und Marktverhalten berechnen.
5. Aus den Trades eindeutige `conditionId`s bilden.
6. `current_positions` fuer diese `conditionId`s abfragen.
7. Aktuelles Exposure und Konzentrationsrisiko fuer die zuletzt gehandelten
   Maerkte bewerten.

Damit hat jede Quelle eine klare Aufgabe:

```text
leaderboard:
  30d/Monats-PnL, 30d/Monats-Volumen, Rankings

trades:
  Aktivitaet, Recency, Buy/Sell-Verhalten, Marktbreite, Konzentration

current_positions:
  aktuell offenes Kapital und Risiko in den 30d-relevanten Maerkten
```

## Metriken

### Leaderboard

```text
leaderboard_pnl_month
Quelle: Leaderboard timePeriod=MONTH, orderBy=PNL
Bedeutung: Polymarket-PnL im Monatsfenster. Primaere Performance-Metrik.

leaderboard_volume_month
Quelle: Leaderboard timePeriod=MONTH, orderBy=VOL
Bedeutung: Polymarket-Volumen im Monatsfenster. Primaere Whale-Groesse.

pnl_rank
Quelle: Leaderboard orderBy=PNL
Bedeutung: Rang nach Monats-PnL.

volume_rank
Quelle: Leaderboard orderBy=VOL
Bedeutung: Rang nach Monats-Volumen.
```

### Trade-Aktivitaet

```text
trade_count_30d
Quelle: trades
Bedeutung: Anzahl Trades im 30-Tage-Fenster.

trade_count_7d
Quelle: trades
Bedeutung: Anzahl Trades in den letzten 7 Tagen.

trade_volume_30d
Quelle: trades, sum(price * size)
Bedeutung: Beobachtetes Trade-Volumen im 30-Tage-Fenster.

trade_volume_7d
Quelle: trades, sum(price * size)
Bedeutung: Beobachtetes Trade-Volumen in den letzten 7 Tagen.

last_trade_at
Quelle: trades timestamp
Bedeutung: Zeitpunkt des letzten Trades.

last_trade_age_days
Quelle: now - last_trade_at
Bedeutung: Alter der letzten Aktivitaet in Tagen.

avg_trade_size_30d
Quelle: trade_volume_30d / trade_count_30d
Bedeutung: Durchschnittliche Trade-Groesse im 30-Tage-Fenster.
```

### Trade-Verhalten

```text
buy_volume_30d
Quelle: BUY trades, sum(price * size)
Bedeutung: Kapital, das in den letzten 30 Tagen in Positionen geflossen ist.

sell_volume_30d
Quelle: SELL trades, sum(price * size)
Bedeutung: Kapital, das in den letzten 30 Tagen aus Positionen geflossen ist.

net_flow_30d
Quelle: buy_volume_30d - sell_volume_30d
Bedeutung: Netto-Aufbau oder Netto-Abbau von Positionen.

buy_sell_ratio_30d
Quelle: buy_volume_30d / sell_volume_30d
Bedeutung: Verhaeltnis zwischen Aufbau und Abverkauf.
```

### Marktverhalten

```text
unique_markets_30d
Quelle: unique conditionId aus trades
Bedeutung: Anzahl verschiedener Maerkte, die im 30-Tage-Fenster gehandelt wurden.

market_concentration_30d
Quelle: groesstes Marktvolumen / trade_volume_30d
Bedeutung: Anteil des groessten Marktes am gesamten 30-Tage-Trade-Volumen.

largest_market_volume_30d
Quelle: max(sum(price * size) pro conditionId)
Bedeutung: Volumen des groessten gehandelten Marktes im 30-Tage-Fenster.
```

### Aktuelles Exposure

```text
current_position_value
Quelle: current_positions fuer conditionIds aus 30d-Trades
Bedeutung: Aktuell offenes Kapital in den zuletzt gehandelten Maerkten.

open_position_count
Quelle: current_positions fuer conditionIds aus 30d-Trades
Bedeutung: Anzahl aktuell offener Positionen in diesen Maerkten.

largest_position_value
Quelle: current_positions
Bedeutung: Groesste offene Einzelposition.

position_concentration
Quelle: largest_position_value / current_position_value
Bedeutung: Konzentrationsrisiko innerhalb der offenen Positionen.
```

## Filter-Logik

Harte Filter sollten nur auf robuste, klar interpretierbare Metriken gehen:

```text
leaderboard_pnl_month > 0
leaderboard_volume_month >= min_month_volume
trade_count_30d >= min_trade_count_30d
trade_volume_30d >= min_trade_volume_30d
trade_count_7d >= min_trade_count_7d
last_trade_age_days <= max_last_trade_age_days
```

`current_position_value` ist optional als harter Filter. Wenn nur aktive Trader
gefunden werden sollen, reicht Trade-Aktivitaet. Wenn nur Whales mit aktuellem
offenem Kapital relevant sind, sollte `current_position_value` zusaetzlich
gefordert werden.

## Scoring

Ein pragmatischer Score kann so aufgebaut werden:

```text
performance_score:
  leaderboard_pnl_month
  leaderboard_volume_month
  pnl_rank
  volume_rank

activity_score:
  trade_volume_30d
  trade_volume_7d
  trade_count_30d
  trade_count_7d
  last_trade_age_days

behavior_score:
  unique_markets_30d
  avg_trade_size_30d
  buy_sell_ratio_30d
  net_flow_30d

risk_score:
  current_position_value
  open_position_count
  position_concentration
  market_concentration_30d
```

Wichtig: Leaderboard-PnL und Leaderboard-Volumen bleiben die Performance-Basis.
Trades erklaeren nur, wie aktiv und in welchen Maerkten der Wallet zuletzt war.
Current Positions zeigen, was davon aktuell noch als Exposure offen ist.
