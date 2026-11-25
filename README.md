# India Swing Scanner — GitHub Pages files

## Upload these files into the root of the GitHub repository
- `index.html` — dashboard page
- `scan.py` — Yahoo Finance scanner (no Dhan API and no broker orders)
- `fno_symbols.txt` — symbol list input
- `requirements.txt` — Python dependencies
- `.github/workflows/scan.yml` — scheduled GitHub Actions workflow

The workflow creates/updates `data.json`; the dashboard reads that file.

## Important
`fno_symbols.txt` currently contains the 28-stock starter universe, not the complete current NSE stock-F&O universe. Replace it with a verified current NSE list when available. Use one NSE symbol per line, without `.NS`.

GitHub Actions cron uses UTC. The included schedule corresponds to 09:15–15:30 India time on weekdays, but GitHub may delay scheduled jobs. Yahoo Finance intraday data may be delayed, missing, or rate-limited. The dashboard is report-only and never places orders.

After uploading, open GitHub → Actions → `scan` → Run workflow for the first manual run. Confirm that `data.json` is committed. Enable GitHub Pages from the repository's `main` branch and `/ (root)` if not already enabled.

## Refresh behavior
- GitHub Actions runs the scan on the configured 15-minute schedule (not every minute). GitHub may start scheduled workflows late.
- The website checks `data.json` every 60 seconds and updates the display when a new file is available.
- The dashboard's 60-second check does not run a new stock scan; it only checks whether GitHub has published newer `data.json`.

## Universe expansion (v3)
The old v6.1.1 engine contains 152 curated EXTENDED symbols in its code and dynamically adds the current stock-F&O underlyings from Dhan's public detailed scrip-master CSV. This package follows that same pattern: it uses the 152 curated list in `fno_symbols.txt`, then tries to add current `FUTSTK` NSE underlyings from the public master. It does NOT use a Dhan login/token, quote API, or order API; all OHLC candles still come from Yahoo Finance.

The actual total is calculated on each run and may differ from 221 if the public master membership has changed or cannot be downloaded. If auto-discovery fails, it safely scans the 152 curated symbols and records the discovery warning in `data.json`; it does not invent the missing 69 symbols.
