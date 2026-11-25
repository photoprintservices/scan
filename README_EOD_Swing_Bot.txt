# India EOD Swing Intelligence — Dhan-free GitHub pack v1.3

## Included files
- `scan.py` — EOD swing scanner; no Dhan API, token, broker mapping or order execution.
- `index.html` — interactive GitHub Pages chart/dashboard.
- `.github/workflows/scan.yml` — weekday 16:15 IST scheduled scan plus manual dispatch.
- `README_EOD_Swing_Bot.txt` — this guide.

## User configuration
- Holding period: 1–3 trading sessions.
- Setups: breakout + pullback.
- Trading capital: ₹1,00,000.
- Per-setup risk budget: 0.5% = ₹500.
- Maximum capital allocation per position: 25% = ₹25,000.
- Target 1: 1.5R; Target 2: 2.5R.
- Research-only; manual review required; no broker orders.

## Chart layout
- Main price panel: candles, EMA20, EMA50, support/resistance, Entry, Stop Loss, Target 1 and Target 2.
- Separate volume panel.
- RSI panel (toggle; on by default).
- MACD panel (toggle; off by default).
- Timeframes: Daily, Weekly and Monthly. Weekly/monthly candles and indicators are aggregated/recalculated from daily OHLCV.
- Independent overlays: Support/Resistance, Supply/Demand, Fibonacci, swing trendlines, BOS, CHOCH, FVG, Order Blocks, Harmonic, Elliott, Gann, Volume Profile, Measured Moves and Wick Liquidity.
- FVG, Order Blocks, Harmonic, Elliott, Gann, Volume Profile, Measured Moves and Wick Liquidity are off by default to keep the chart uncluttered.

## Price-action modules carried over/adapted from Intelligence Engine v6.1.1
- Supply and Demand zones; swing support/resistance and confluence bands.
- Wick-liquidity levels and liquidity sweeps.
- Swing trendlines and Fibonacci retracement.
- Harmonic candidates: Gartley, Bat, Butterfly, Crab and Deep Crab.
- Elliott Wave candidate logic.
- Gann Square-of-9 levels and fan projections.
- Head & Shoulders / Inverse Head & Shoulders; Double Top / Double Bottom.
- Fixed-range Volume Profile: POC, VAL and VAH.
- BOS, CHOCH, three-candle FVG, Order Block candidates.
- Wyckoff spring/upthrust, candlestick rejection/engulfing and measured-move projections.

These tools are heuristic technical-analysis candidates, not verified institutional order-flow data or guaranteed patterns. They do not independently trigger trades.

## GitHub installation
1. Extract the ZIP.
2. Replace the repository root `scan.py` with the package `scan.py`.
3. Replace the repository root `index.html` with the package `index.html`.
4. Place `scan.yml` at `.github/workflows/scan.yml`.
5. Commit and push to the repository's default branch.
6. Ensure GitHub Pages deploys from that branch and root folder.
7. Run Actions → India EOD Swing Intelligence → Run workflow once.

## Refresh behaviour
The workflow scans at 16:15 IST, Monday–Friday. GitHub may start scheduled jobs later than the exact cron minute. On completion it commits `data.json` and `EOD_Swing_Report_LATEST.json`. The open webpage fetches the latest `data.json` every 60 seconds. Browser refresh does not start a new scan; use GitHub Actions for a manual scan.

## Data sources and limitations
- Yahoo Finance: daily OHLCV for stocks, indices and macro instruments.
- NSE archives / public NSE endpoints: F&O bhavcopy OI, MWPL, volume gainers, FII/DII and corporate events when available.
- Screener.in: quarterly shareholding snapshots, not daily institutional flows.
- Google News RSS and Forex Factory calendar.
- If a site blocks a request, changes its format or has not published data, the dashboard should show unavailable/empty context instead of inventing values. Public endpoints can rate-limit or delay data.

## Interpretation and risk
The entry is the latest completed daily close, not a guaranteed next-session fill. Check next-session price, liquidity, events and the chart before any decision. Backtest/replay metrics are historical diagnostics, not guarantees. Brokerage, taxes, slippage, market gaps and portfolio-level overlap can change real outcomes. No automated orders are placed.
