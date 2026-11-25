"""India swing scanner: 15-min NSE candles (Yahoo) -> price action setups -> levels -> backtest -> Monte Carlo replay -> risk gate -> data.json"""
import os, json, datetime as dt
import numpy as np, pandas as pd

CFG = dict(capital=100000, risk_pct=1.0, min_rr=2.0, max_pos_pct=25,
           cost_pct=0.15, sims=2000, hold_bars=52, seed=19)
SYMS = ("RELIANCE TCS HDFCBANK ICICIBANK INFY SBIN BHARTIARTL ITC LT AXISBANK KOTAKBANK "
        "HINDUNILVR MARUTI SUNPHARMA TATASTEEL M&M BAJFINANCE ASIANPAINT NTPC POWERGRID "
        "ONGC COALINDIA ADANIPORTS TITAN ULTRACEMCO WIPRO HCLTECH JSWSTEEL").split()

def load(sym):
    if os.getenv("DEMO"):  # synthetic data for testing without internet
        rng = np.random.default_rng(sum(map(ord, sym)))
        days = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=59)
        idx = pd.DatetimeIndex([t for d in days for t in pd.date_range(d + pd.Timedelta("9h15min"), periods=25, freq="15min")])
        c = 1000 * np.exp(np.cumsum(rng.normal(0.0002, 0.003, len(idx))))
        o = np.r_[c[0], c[:-1]]
        h = np.maximum(o, c) * (1 + abs(rng.normal(0, .0015, len(idx))))
        l = np.minimum(o, c) * (1 - abs(rng.normal(0, .0015, len(idx))))
        return pd.DataFrame(dict(Open=o, High=h, Low=l, Close=c, Volume=rng.lognormal(10, .5, len(idx))), index=idx)
    import yfinance as yf
    d = yf.download(sym + ".NS", period="59d", interval="15m", progress=False, auto_adjust=True)
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = d.columns.get_level_values(0)
    return d.dropna()

def prep(d):
    d = d.copy(); c = d.Close; pc = c.shift()
    d["e20"] = c.ewm(span=20).mean(); d["e50"] = c.ewm(span=50).mean()
    tr = pd.concat([d.High - d.Low, (d.High - pc).abs(), (d.Low - pc).abs()], axis=1).max(axis=1)
    d["atr"] = tr.rolling(14).mean()
    dl = c.diff(); g = dl.clip(lower=0).rolling(14).mean(); l = (-dl.clip(upper=0)).rolling(14).mean()
    d["rsi"] = 100 - 100 / (1 + g / l.replace(0, np.nan))
    d["hh"] = d.High.rolling(20).max().shift()
    d["vr"] = d.Volume / d.Volume.rolling(20).mean()
    d["sw"] = d.Low.rolling(10).min()
    body = c - d.Open
    engulf = (body > 0) & (body.shift() < 0) & (c > d.Open.shift()) & (d.Open <= pc)
    up = (d.e20 > d.e50) & (c > d.e50)
    brk = up & (c > d.hh) & (d.vr > 1.3)
    pull = up & (d.Low <= d.e20 * 1.002) & (c > d.e20) & engulf
    d["sig"] = np.where(brk, "Breakout", np.where(pull, "Pullback + engulfing", ""))
    return d

def levels(e, atr, sw):
    sl = min(e - atr, max(sw, e - 2.5 * atr))
    return sl, e + CFG["min_rr"] * (e - sl)

def backtest(d):
    O, H, L, C = (d[k].values for k in ("Open", "High", "Low", "Close"))
    A, S, n, hold = d.atr.values, d.sw.values, len(d), CFG["hold_bars"]
    out, last = [], -10**9
    for i in np.flatnonzero(d.sig.values != ""):
        if i < last + hold or i + 1 >= n or np.isnan(A[i]):
            continue
        e = C[i]; sl, tp = levels(e, A[i], S[i]); risk = e - sl; last = i; r = None
        for j in range(i + 1, min(i + 1 + hold, n)):
            if L[j] <= sl: r = -1.0; break
            if H[j] >= tp: r = CFG["min_rr"]; break
        if r is None:
            r = (C[min(i + hold, n - 1)] - e) / risk
        out.append(r - CFG["cost_pct"] / 100 * e / risk)
    if not out:
        return dict(n=0, win=None, avg_r=None)
    a = np.array(out)
    return dict(n=len(a), win=round(float((a > 0).mean() * 100), 1), avg_r=round(float(a.mean()), 2))

def simulate(d, e, sl, tp):
    rng = np.random.default_rng(CFG["seed"]); N = CFG["sims"]
    tod = np.array(d.index.strftime("%H%M")); buckets = sorted(set(tod))
    r = np.c_[(d.High / d.Open - 1).values, (d.Low / d.Open - 1).values, (d.Close / d.Open - 1).values]
    pool = {b: r[tod == b] for b in buckets}
    k = (buckets.index(tod[-1]) + 1) % len(buckets)
    p = np.full(N, e); st = np.zeros(N, int)
    for s in range(CFG["hold_bars"]):
        pl = pool[buckets[(k + s) % len(buckets)]]; x = pl[rng.integers(0, len(pl), N)]
        hi, lo = p * (1 + x[:, 0]), p * (1 + x[:, 1])
        hs = (lo <= sl) & (st == 0); ht = (hi >= tp) & (st == 0) & ~hs  # same-bar hit counts as stop (conservative)
        st[hs] = 2; st[ht] = 1; p = p * (1 + x[:, 2])
    return dict(target=round(float((st == 1).mean() * 100), 1), stop=round(float((st == 2).mean() * 100), 1),
                open=round(float((st == 0).mean() * 100), 1))

def risk_gate(e, sl, tp, bt, sim):
    rps = e - sl; why = []
    qty = int(min(CFG["capital"] * CFG["risk_pct"] / 100 / rps, CFG["capital"] * CFG["max_pos_pct"] / 100 / e))
    rr = (tp - e) / rps
    if qty < 1: why.append("position size below 1 share")
    if rr < CFG["min_rr"]: why.append(f"reward:risk {rr:.1f} below {CFG['min_rr']}")
    if sim["target"] <= sim["stop"]: why.append("replay: stop hit more often than target")
    if bt["n"] >= 5 and bt["avg_r"] <= 0: why.append("backtest expectancy not positive")
    return dict(verdict="BLOCK" if why else "PASS", reasons=why, qty=qty, rr=round(rr, 2),
                max_loss=round(qty * rps), capital_used=round(qty * e))

def main():
    rows, scanned = [], 0
    for s in SYMS:
        try:
            d = load(s)
            if len(d) < 120: continue
            d = prep(d); scanned += 1; x = d.iloc[-1]
            if x.sig == "" or np.isnan(x.atr): continue
            e = float(x.Close); sl, tp = levels(e, x.atr, x.sw)
            bt, sim = backtest(d), simulate(d, e, sl, tp)
            rg = risk_gate(e, sl, tp, bt, sim)
            score = sim["target"] - sim["stop"] + 10 * (bt["avg_r"] or 0)
            rows.append(dict(symbol=s, setup=x.sig, entry=round(e, 2), sl=round(float(sl), 2), target=round(float(tp), 2),
                             rsi=round(float(x.rsi), 0), vol_x=round(float(x.vr), 1), backtest=bt, replay=sim,
                             risk=rg, score=round(float(score), 1), bar=str(d.index[-1])))
        except Exception as ex:
            print("skip", s, ex)
    rows.sort(key=lambda r: (r["risk"]["verdict"] != "PASS", -r["score"]))
    ist = dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30)))
    json.dump(dict(updated=ist.strftime("%d %b %Y, %H:%M IST"), scanned=scanned, demo=bool(os.getenv("DEMO")),
                   config=CFG, rows=rows), open("data.json", "w"), indent=1)
    print(f"scanned {scanned}, setups {len(rows)}")

if __name__ == "__main__":
    main()
