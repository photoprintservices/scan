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
