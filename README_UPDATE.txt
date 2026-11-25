INDIA SWING SCANNER — CHART + PRICE-ACTION UPDATE

This update contains ONLY two replacement files:
  1. scan.py
  2. index.html

What it adds:
- Yahoo Finance daily OHLCV history (2 years; up to 520 daily candles) for the leading 40 scanner rows.
- EMA20, EMA50 and RSI14 on the daily chart.
- Daily swing structure (HH/HL, LH/LL where identifiable), pivot support/resistance,
  simple supply/demand zones, Fibonacci retracement levels, swing-anchored trendlines,
  and simple latest-candle pattern labels.
- Dashboard controls to toggle support/resistance, supply/demand, Fibonacci and trendlines.
- Chart-fetch failures are recorded separately in data.json errors; they do not change
  the existing 15-minute scan calculations, setup logic, backtest, replay or risk gate.

INSTALL:
1. Back up the current GitHub repository files.
2. Replace ONLY scan.py and index.html in the main branch with these versions.
3. Keep your existing scan.yml, fno_symbols.txt and requirements.txt unchanged.
4. Run Actions > scan > Run workflow once.
5. Open the committed data.json and verify chart_history_count is greater than zero
   and a signal row contains chart[] and price_action{}.
6. Hard-refresh the GitHub Pages website.

IMPORTANT:
- Do not overwrite scan.yml with an older workflow. This update deliberately excludes it,
  so your current 5-minute schedule (if configured in your repository) is preserved.
- Scanner signals continue to use Yahoo Finance 15-minute data. The chart and price-action
  overlays use Yahoo Finance daily data; weekly/monthly views are aggregated in the browser.
- Yahoo Finance can rate-limit or omit individual symbols. Missing chart history is reported;
  the scanner row and existing risk calculations remain available.
- Supply/demand zones and trendlines are rule-based technical annotations, not predictions.
- No broker API, account token or order placement is used.
