# trader/scripts — market data tools

Raw data only; the agent does the judging. `crypto.py` and `stock.py` are standard-library only;
the two volume-profile scripts need `matplotlib` (`pip install matplotlib`).

| Script | What | Source | Key? |
|---|---|---|---|
| `crypto.py BTC ETH SOL` | perp price, 24h %, funding, volume | OKX + Hyperliquid public APIs | no |
| `stock.py NVDA AAPL` | US quote: price, day %, open, prev close, high/low | Finnhub | free key |
| `volume_profile.py SYM [--source okx\|hl\|yahoo]` | volume profile PNG + JSON (POC, value area) | OKX / Hyperliquid / Yahoo | no |
| `volume_profile_recency.py SYM` | same, recent bars weighted more | same | no |

Finnhub: register at https://finnhub.io, put `FINNHUB_API_KEY=...` in the repo-root `.env`
(or point `FRIDAY_ENV_FILE` at another file). Free tier: 60 requests/minute.

Yahoo sometimes rate-limits (HTTP 429); the scripts then say "history unavailable" instead of drawing a chart.
Comments in the scripts are in Chinese.
