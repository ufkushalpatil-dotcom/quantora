# QUANTORA V1 — working educational market-intelligence starter

This is a real, runnable first version, not a static mockup:
- Live public Binance Spot ticker data (read-only; no exchange account/API key)
- Historical OHLCV candles + live kline WebSocket updates
- EMA20, EMA50, RSI14 and relative-volume calculations
- Four-lane analysis view (technical/flow calculated; news and macro are explicitly not fabricated)
- Historical SMA crossover backtest using downloaded Binance candles
- Browser-local strategy library
- Browser-local virtual paper portfolio using fetched spot prices
- Publisher RSS headlines
- Optional local AI via Ollama

## Safety and scope
This project intentionally has no exchange login, real order placement, leverage, derivatives, or automated trading. Paper portfolio actions are local simulations only. This is an educational tool, not investment advice. Backtests are simplified and do not model slippage, market impact, taxes, or all execution constraints.

## Run locally

Requires Python 3.10+.

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Open http://127.0.0.1:8000

The app uses Binance's public market-data-only REST and WebSocket endpoints. These endpoints do not require API keys. Availability may vary by region, and provider limits/terms apply. See:
- https://developers.binance.com/en/docs/products/spot/market-data-only
- https://developers.binance.com/en/docs/products/spot/rest-api
- https://developers.binance.com/en/docs/products/spot/web-socket-streams

Charts use TradingView Lightweight Charts (Apache 2.0):
- https://www.tradingview.com/lightweight-charts/

## Optional local AI

The AI assistant is not falsely represented as connected by default. To enable it:
1. Install Ollama from https://ollama.com/
2. Download a model, e.g. `ollama pull qwen2.5:3b`
3. Keep Ollama running.
4. Start the backend. Defaults are `http://localhost:11434` and `qwen2.5:3b`.
5. To change them, set `OLLAMA_URL` and `OLLAMA_MODEL` environment variables before starting FastAPI.

The AI endpoint is restricted by its system prompt to financial education and explanations; it should not be treated as a source of personalized investment advice.

## Deployment notes

The easiest first run is local. For public deployment:
- Deploy the FastAPI app on a Python host that supports persistent web services.
- The included frontend is served by FastAPI from `/`.
- Free hosting tiers can sleep, impose bandwidth/CPU limits, or change terms; a permanent zero-cost production service cannot be guaranteed.
- Do not add exchange trading credentials. This starter does not need them.
- Add authentication, database persistence, abuse controls, monitoring, rate limiting, and a privacy policy before inviting public users.

## Current limitations / next build stages
- Macro calendar is a clearly marked placeholder because a reliable calendar provider/API key has not been configured.
- News is publisher RSS, not a comprehensive news terminal or sentiment engine.
- The AI feature requires a local Ollama install and downloaded model; no paid cloud API is called.
- Paper portfolio and saved strategies are stored in the current browser only; clearing browser storage removes them.
- Backtest uses a deliberately simple long-only SMA crossover and simplified fees; it is not a professional execution simulator.
