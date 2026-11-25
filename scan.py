"""India Swing Scanner v3: Yahoo Finance 15m -> setups/backtest/replay -> data.json.

Price/candle data: Yahoo Finance only.
Universe: exact 152 curated EXTENDED symbols from the user's v6.1.1 engine,
plus current NSE stock-F&O underlyings discovered from Dhan's PUBLIC scrip-master CSV.
No Dhan account, access token, quotes API, or broker order placement is used.
"""
import os, json, datetime as dt, re, io
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
import pandas as pd
import requests

CFG = dict(
    universe="v6.1.1 EXTENDED + current F&O", timeframe="15m", rsi_period=14,
    capital=100000, risk_pct=1.0, min_rr=2.0, max_pos_pct=25,
    cost_pct=0.15, sims=2000, hold_bars=52, seed=19,
    breakout_lookback=20, volume_multiple=1.30,
    ema_fast=20, ema_slow=50, atr_period=14,
    rsi_buy_min=55, rsi_sell_max=45,
    use_nifty_filter=True
)
Dhan_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"
UA = {"User-Agent": "Mozilla/5.0"}

def _clean_symbol(value):
    z = str(value or "").strip().upper()
    z = re.sub(r"-(EQ|BE|BZ)$", "", z)
    if not z or "TEST" in z or not re.match(r"^[A-Z][A-Z0-9&._-]{0,24}$", z):
        return ""
    return z

def load_universe():
    p = Path(__file__).with_name("fno_symbols.txt")
    curated = [x.strip().upper() for x in p.read_text(encoding="utf-8").splitlines()
               if x.strip() and not x.strip().startswith("#")] if p.exists() else []
    curated = list(dict.fromkeys(curated))
    try:
        response = requests.get(Dhan_MASTER_URL, headers=UA, timeout=45)
        response.raise_for_status()
        master = pd.read_csv(io.BytesIO(response.content), low_memory=False).fillna("")
        # Support the detailed-master field names used by v6.1.1 and common aliases.
        exch_col = "SEM_EXM_EXCH_ID" if "SEM_EXM_EXCH_ID" in master else "EXCH_ID"
        inst_col = "SEM_INSTRUMENT_NAME" if "SEM_INSTRUMENT_NAME" in master else "INSTRUMENT"
        under_col = "UNDERLYING_SYMBOL" if "UNDERLYING_SYMBOL" in master else "SYMBOL_NAME"
        if not all(c in master.columns for c in (exch_col, inst_col, under_col)):
            raise ValueError("Dhan public master has an unexpected column layout")
        mask = master[exch_col].astype(str).str.upper().isin(["NSE", "NSE_FNO"])
        mask &= master[inst_col].astype(str).str.upper().eq("FUTSTK")
        extras = sorted({_clean_symbol(x) for x in master.loc[mask, under_col].tolist()} - {""})
        combined = list(dict.fromkeys(curated + [x for x in extras if x not in set(curated)]))
        return combined, f"v6.1.1 curated {len(curated)} + public F&O master {len([x for x in extras if x not in set(curated)])}", None
    except Exception as ex:
        return curated, f"v6.1.1 curated {len(curated)} (F&O auto-discovery unavailable)", \
               f"Public F&O master: {type(ex).__name__}: {str(ex)[:180]}"

def _demo_data(sym, periods=59):
    rng = np.random.default_rng(sum(map(ord, sym)))
    days = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=periods)
    idx = pd.DatetimeIndex([t for d in days for t in pd.date_range(
        d + pd.Timedelta("9h15min"), periods=25, freq="15min")])
    c = 1000 * np.exp(np.cumsum(rng.normal(0.0002, 0.003, len(idx))))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) * (1 + abs(rng.normal(0, .0015, len(idx))))
    l = np.minimum(o, c) * (1 - abs(rng.normal(0, .0015, len(idx))))
    return pd.DataFrame(dict(Open=o, High=h, Low=l, Close=c,
                             Volume=rng.lognormal(10, .5, len(idx))), index=idx)

def load(sym):
    if os.getenv("DEMO"):
        return _demo_data(sym)
    import yfinance as yf
    d = yf.download(sym + ".NS", period="59d", interval="15m",
                    progress=False, auto_adjust=True, prepost=False, threads=False)
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = d.columns.get_level_values(0)
    return d.dropna()

def load_nifty():
    if os.getenv("DEMO"):
        return _demo_data("NIFTY")
    import yfinance as yf
    d = yf.download("^NSEI", period="59d", interval="15m",
                    progress=False, auto_adjust=True, prepost=False, threads=False)
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = d.columns.get_level_values(0)
    return d.dropna()

def _rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    rs = gain / loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.mask((loss == 0) & (gain > 0), 100).fillna(50)

def prep(d):
    d = d.copy()
    c, pc = d.Close, d.Close.shift()
    d["e20"] = c.ewm(span=CFG["ema_fast"], adjust=False).mean()
    d["e50"] = c.ewm(span=CFG["ema_slow"], adjust=False).mean()
    tr = pd.concat([d.High-d.Low, (d.High-pc).abs(), (d.Low-pc).abs()], axis=1).max(axis=1)
    d["atr"] = tr.ewm(alpha=1/CFG["atr_period"], adjust=False, min_periods=CFG["atr_period"]).mean()
    d["rsi"] = _rsi(c, CFG["rsi_period"])
    lb = CFG["breakout_lookback"]
    d["hh"] = d.High.rolling(lb).max().shift()
    d["ll"] = d.Low.rolling(lb).min().shift()
    d["vr"] = d.Volume / d.Volume.shift().rolling(20).mean()
    d["sw"] = d.Low.rolling(10).min()
    body = c - d.Open
    engulf = (body > 0) & (body.shift() < 0) & (c > d.Open.shift()) & (d.Open <= pc)
    up = (d.e20 > d.e50) & (c > d.e50)
    brk = up & (c > d.hh) & (d.vr >= CFG["volume_multiple"]) & (d.rsi >= CFG["rsi_buy_min"])
    pull = up & (d.Low <= d.e20 * 1.002) & (c > d.e20) & engulf & (d.rsi >= 50)
    down = (d.e20 < d.e50) & (c < d.e50)
    breakdown = down & (c < d.ll) & (d.vr >= CFG["volume_multiple"]) & (d.rsi <= CFG["rsi_sell_max"])
    d["sig"] = np.select([brk, pull, breakdown],
                         ["Breakout", "Pullback + engulfing", "Breakdown / EXIT"], default="")
    return d

def nifty_regime(nifty):
    if nifty is None or len(nifty) < 60:
        return "UNKNOWN"
    n = prep(nifty)
    x = n.iloc[-1]
    if x.Close > x.e20 > x.e50: return "BULLISH"
    if x.Close < x.e20 < x.e50: return "BEARISH"
    return "SIDEWAYS"

def levels(e, atr, sw):
    sl = min(e - atr, max(sw, e - 2.5 * atr))
    return sl, e + CFG["min_rr"] * (e - sl)

def backtest(d):
    O,H,L,C = (d[k].values for k in ("Open","High","Low","Close"))
    A,S,n,hold = d.atr.values,d.sw.values,len(d),CFG["hold_bars"]
    out,last=[], -10**9
    for i in np.flatnonzero((d.sig.values != "") & (d.sig.values != "Breakdown / EXIT")):
        if i < last + hold or i+1 >= n or np.isnan(A[i]) or np.isnan(S[i]): continue
        e=C[i]; sl,tp=levels(e,A[i],S[i]); risk=e-sl
        if risk <= 0: continue
        last=i; r=None
        for j in range(i+1,min(i+1+hold,n)):
            if L[j] <= sl: r=-1.0; break
            if H[j] >= tp: r=CFG["min_rr"]; break
        if r is None: r=(C[min(i+hold,n-1)]-e)/risk
        out.append(r-CFG["cost_pct"]/100*e/risk)
    if not out: return dict(n=0,win=None,avg_r=None)
    a=np.array(out)
    return dict(n=len(a),win=round(float((a>0).mean()*100),1),avg_r=round(float(a.mean()),2))

def simulate(d,e,sl,tp):
    rng=np.random.default_rng(CFG["seed"]); N=CFG["sims"]
    tod=np.array(d.index.strftime("%H%M")); buckets=sorted(set(tod))
    r=np.c_[(d.High/d.Open-1).values,(d.Low/d.Open-1).values,(d.Close/d.Open-1).values]
    pool={b:r[tod==b] for b in buckets}; k=(buckets.index(tod[-1])+1)%len(buckets)
    p=np.full(N,e); st=np.zeros(N,int)
    for s in range(CFG["hold_bars"]):
        pl=pool[buckets[(k+s)%len(buckets)]]
        x=pl[rng.integers(0,len(pl),N)]
        hi,lo=p*(1+x[:,0]),p*(1+x[:,1])
        hs=(lo<=sl)&(st==0); ht=(hi>=tp)&(st==0)&~hs
        st[hs]=2; st[ht]=1; p=p*(1+x[:,2])
    return dict(target=round(float((st==1).mean()*100),1),
                stop=round(float((st==2).mean()*100),1),
                open=round(float((st==0).mean()*100),1))

def risk_gate(e,sl,tp,bt,sim):
    rps=e-sl; why=[]
    qty=int(min(CFG["capital"]*CFG["risk_pct"]/100/rps,
                CFG["capital"]*CFG["max_pos_pct"]/100/e))
    rr=(tp-e)/rps
    if qty<1: why.append("position size below 1 share")
    if rr<CFG["min_rr"]: why.append(f"reward:risk {rr:.1f} below {CFG['min_rr']}")
    if sim["target"]<=sim["stop"]: why.append("replay: stop hit at least as often as target")
    if bt["n"]>=5 and bt["avg_r"]<=0: why.append("backtest expectancy not positive")
    return dict(verdict="BLOCK" if why else "PASS",reasons=why,qty=qty,rr=round(rr,2),
                max_loss=round(qty*rps),capital_used=round(qty*e))

def _scan_one(symbol):
    raw = load(symbol)
    if len(raw) < 120:
        return symbol, None, "insufficient Yahoo Finance history"
    d = prep(raw)
    x = d.iloc[-1]
    if x.sig == "" or pd.isna(x.atr):
        return symbol, None, None
    e = float(x.Close); sl, tp = levels(e, float(x.atr), float(x.sw))
    if x.sig == "Breakdown / EXIT":
        return symbol, dict(symbol=symbol, signal="SELL / EXIT", setup=x.sig, entry=round(e,2),
            sl=None, target=None, rsi=round(float(x.rsi),1), vol_x=round(float(x.vr),2),
            market_regime=None, reason="Bearish breakdown: review/exit existing long; not a cash short entry",
            bar=str(d.index[-1])), None
    bt=backtest(d); sim=simulate(d,e,sl,tp); rg=risk_gate(e,sl,tp,bt,sim)
    return symbol, dict(symbol=symbol,signal="BUY" if rg["verdict"]=="PASS" else "WAIT",
        setup=x.sig,entry=round(e,2),sl=round(float(sl),2),target=round(float(tp),2),
        rsi=round(float(x.rsi),1),vol_x=round(float(x.vr),2),backtest=bt,replay=sim,
        risk=rg,market_regime=None,score=round(float(sim["target"]-sim["stop"]+10*(bt["avg_r"] or 0)),1),
        reason="; ".join(rg["reasons"]) if rg["reasons"] else "All configured gates passed",
        bar=str(d.index[-1])), None

def main():
    symbols, universe_source, universe_warning = load_universe()
    try:
        nifty=load_nifty()
        regime=nifty_regime(nifty)
    except Exception as ex:
        regime="UNKNOWN"
        print("NIFTY filter unavailable:",type(ex).__name__,str(ex)[:160])
    rows=[]; errors=[]; scanned=0
    if universe_warning:
        errors.append({"symbol":"UNIVERSE","error":universe_warning})
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures={pool.submit(_scan_one,s):s for s in symbols}
        for fut in as_completed(futures):
            s=futures[fut]
            try:
                _, row, err=fut.result()
                if row:
                    row["market_regime"]=regime
                    if row["signal"] != "SELL / EXIT" and CFG["use_nifty_filter"] and regime in ("BEARISH","SIDEWAYS"):
                        row["risk"]["verdict"]="BLOCK"
                        row["risk"]["reasons"].append(f"NIFTY regime {regime.lower()}")
                        row["signal"]="WAIT"
                    rows.append(row)
                if err: errors.append({"symbol":s,"error":err})
                if row is not None or err is None: scanned += 1
            except Exception as ex:
                errors.append({"symbol":s,"error":f"{type(ex).__name__}: {str(ex)[:160]}"})
    rows.sort(key=lambda r:(r.get("signal")!="BUY",-r.get("score",0)))
    ist=dt.datetime.now(dt.timezone(dt.timedelta(hours=5,minutes=30)))
    payload=dict(updated=ist.strftime("%d %b %Y, %H:%M IST"),scanned=scanned,
        universe_count=len(symbols),universe_source=universe_source,data_source="Yahoo Finance 15m",
        market_regime=regime,demo=bool(os.getenv("DEMO")),config=CFG,rows=rows,errors=errors)
    Path("data.json").write_text(json.dumps(payload,indent=2,default=str),encoding="utf-8")
    print(f"scanned {scanned}/{len(symbols)}, setups {len(rows)}, NIFTY {regime}; source={universe_source}")
if __name__=="__main__":
    main()
