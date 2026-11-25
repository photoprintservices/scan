# India swing scanner
15-min NSE candles (Yahoo Finance) -> price-action setups (breakout, pullback + engulfing) -> stop/target -> backtest -> 2000-path replay -> risk gate (PASS/BLOCK) -> dashboard.
Setup: push all files, Settings > Pages > Deploy from branch `main` / root. Actions > scan > Run workflow once.
Test locally: `pip install -r requirements.txt && DEMO=1 python scan.py`. Edit `CFG` / `SYMS` at the top of scan.py. No orders are placed.
