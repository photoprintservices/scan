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
    use_nifty_filter=True, min_backtest_trades=5, max_extension_atr=2.0,
    breakout_close_position_min=0.60, pullback_close_position_min=0.55
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

def technical_confirmation(d):
    """Confirm the latest 15m setup candle; this is a hard BUY quality gate."""
    x = d.iloc[-1]
    reasons = []
    candle_range = max(float(x.High - x.Low), 1e-9)
    close_position = float((x.Close - x.Low) / candle_range)
    bullish_candle = bool(x.Close > x.Open)
    ema20_rising = bool(len(d) >= 4 and x.e20 > d.e20.iloc[-4])
    atr = float(x.atr) if pd.notna(x.atr) and float(x.atr) > 0 else 0.0
    extension_atr = float((x.Close - x.e20) / atr) if atr else 0.0

    if not bullish_candle:
        reasons.append("latest 15m candle is not bullish")
    if not ema20_rising:
        reasons.append("15m EMA20 is not rising")

    if x.sig == "Breakout":
        if close_position < CFG["breakout_close_position_min"]:
            reasons.append("breakout candle did not close near its high")
        if pd.isna(x.hh) or x.Close <= x.hh:
            reasons.append("breakout close is not above prior 20-bar high")
        if pd.isna(x.vr) or x.vr < CFG["volume_multiple"]:
            reasons.append("breakout volume confirmation missing")
    elif x.sig == "Pullback + engulfing":
        if close_position < CFG["pullback_close_position_min"]:
            reasons.append("pullback candle close is weak")
        if x.Close <= x.e20:
            reasons.append("pullback has not reclaimed EMA20")
    else:
        reasons.append("setup type is not eligible for a long BUY")

    if atr and extension_atr > CFG["max_extension_atr"]:
        reasons.append(f"price extended {extension_atr:.1f} ATR above EMA20")

    return dict(passed=not reasons, reasons=reasons,
                close_position=round(close_position, 2),
                ema20_rising=ema20_rising,
                extension_atr=round(extension_atr, 2))


def confidence_score(bt, sim, technical):
    """A 0-100 diagnostic score; replay contributes context but never blocks BUY."""
    score = 35.0 if technical["passed"] else 10.0
    n = int(bt.get("n") or 0)
    avg_r = bt.get("avg_r")
    if avg_r is not None:
        score += float(np.clip(15.0 + 10.0 * float(avg_r), 0, 30))
    score += 15.0 if n >= 10 else (10.0 if n >= CFG["min_backtest_trades"] else 3.0)
    replay_edge = float(sim.get("target", 0)) - float(sim.get("stop", 0))
    score += float(np.clip(10.0 + replay_edge * 0.25, 0, 20))
    return int(round(float(np.clip(score, 0, 100))))


def risk_gate(e,sl,tp,bt,sim,technical):
    rps=e-sl; why=[]
    qty=int(min(CFG["capital"]*CFG["risk_pct"]/100/rps,
                CFG["capital"]*CFG["max_pos_pct"]/100/e)) if rps > 0 and e > 0 else 0
    rr=(tp-e)/rps if rps > 0 else 0
    if qty<1: why.append("position size below 1 share")
    if rr<CFG["min_rr"]: why.append(f"reward:risk {rr:.1f} below {CFG['min_rr']}")
    if not technical["passed"]:
        why.extend(technical["reasons"])
    # A BUY needs enough historical trades and positive expectancy.
    if int(bt.get("n") or 0) < CFG["min_backtest_trades"]:
        why.append(f"insufficient backtest sample: {bt.get('n', 0)} trades; need {CFG['min_backtest_trades']}")
    elif bt.get("avg_r") is None or bt["avg_r"] <= 0:
        why.append("backtest expectancy not positive")
    # Replay is deliberately NOT a hard gate; it is shown in confidence/risk context.
    return dict(verdict="BLOCK" if why else "PASS",reasons=why,qty=qty,rr=round(rr,2),
                max_loss=round(qty*rps) if qty else 0,
                capital_used=round(qty*e) if qty else 0,
                replay_is_blocker=False)


def _pivot_points(values, left=3, right=3):
    highs, lows = [], []
    arr = np.asarray(values, dtype=float)
    for i in range(left, len(arr)-right):
        w = arr[i-left:i+right+1]
        if arr[i] == np.max(w) and np.sum(w == arr[i]) == 1:
            highs.append(i)
        if arr[i] == np.min(w) and np.sum(w == arr[i]) == 1:
            lows.append(i)
    return highs, lows

def _price_action(d):
    """Descriptive daily price-action levels; not a predictive signal."""
    close=float(d.Close.iloc[-1]); high=float(d.High.iloc[-1]); low=float(d.Low.iloc[-1])
    tr=pd.concat([d.High-d.Low,(d.High-d.Close.shift()).abs(),(d.Low-d.Close.shift()).abs()],axis=1).max(axis=1)
    atr=float(tr.rolling(14).mean().iloc[-1]) if len(d)>=14 else max(high-low, close*.01)
    atr=atr if np.isfinite(atr) and atr>0 else max(close*.01, .01)
    ph,pl=_pivot_points(d.High.tail(180).values),_pivot_points(d.Low.tail(180).values)
    hidx,lidx=ph[0],pl[1]
    highs=[(int(i),float(d.High.tail(180).iloc[i])) for i in hidx[-6:]]
    lows=[(int(i),float(d.Low.tail(180).iloc[i])) for i in lidx[-6:]]
    resist=sorted([v for _,v in highs if v>close])
    support=sorted([v for _,v in lows if v<close],reverse=True)
    # Recent confirmed swing points form simple, auditable supply/demand zones.
    supply=[]; demand=[]
    for i,v in highs[-2:]:
        supply.append({'low':round(v-0.35*atr,2),'high':round(v+0.15*atr,2),'pivot_index':i})
    for i,v in lows[-2:]:
        demand.append({'low':round(v-0.15*atr,2),'high':round(v+0.35*atr,2),'pivot_index':i})
    last_highs=[v for _,v in highs[-2:]]; last_lows=[v for _,v in lows[-2:]]
    structure='RANGE / UNCONFIRMED'
    if len(last_highs)==2 and len(last_lows)==2:
        if last_highs[-1]>last_highs[-2] and last_lows[-1]>last_lows[-2]: structure='HH + HL (BULLISH)'
        elif last_highs[-1]<last_highs[-2] and last_lows[-1]<last_lows[-2]: structure='LH + LL (BEARISH)'
        elif last_highs[-1]>last_highs[-2]: structure='HIGHER HIGH; LOW STRUCTURE MIXED'
        elif last_highs[-1]<last_highs[-2]: structure='LOWER HIGH; LOW STRUCTURE MIXED'
    swing_low=float(d.Low.tail(180).iloc[lidx[-1]]) if lidx else float(d.Low.tail(60).min())
    swing_high=float(d.High.tail(180).iloc[hidx[-1]]) if hidx else float(d.High.tail(60).max())
    lo0,hi0=sorted([swing_low,swing_high]); span=hi0-lo0
    fib={k:round(hi0-span*r,2) for k,r in [('0.236',.236),('0.382',.382),('0.500',.5),('0.618',.618),('0.786',.786)]} if span>0 else {}
    # Last confirmed two swing lows/highs are used as simple trendline anchors.
    trend=[]
    if len(lows)>=2:
        (x1,y1),(x2,y2)=lows[-2:]
        trend.append({'kind':'Rising/falling support trendline','x1':x1,'y1':round(y1,2),'x2':x2,'y2':round(y2,2)})
    if len(highs)>=2:
        (x1,y1),(x2,y2)=highs[-2:]
        trend.append({'kind':'Resistance trendline','x1':x1,'y1':round(y1,2),'x2':x2,'y2':round(y2,2)})
    # Simple latest-candle pattern checks.
    o=float(d.Open.iloc[-1]); po=float(d.Open.iloc[-2]); pc=float(d.Close.iloc[-2])
    body=abs(close-o); rng=max(high-low,1e-9); lower=min(o,close)-low; upper=high-max(o,close)
    patterns=[]
    if close>o and pc<po and close>=po and o<=pc: patterns.append('Bullish engulfing')
    if close<o and pc>po and close<=po and o>=pc: patterns.append('Bearish engulfing')
    if lower>=2*max(body,1e-9) and upper<=.35*max(body,1e-9): patterns.append('Hammer-like candle')
    if upper>=2*max(body,1e-9) and lower<=.35*max(body,1e-9): patterns.append('Shooting-star-like candle')
    return {'as_of':d.index[-1].strftime('%Y-%m-%d'),'structure':structure,
        'nearest_support':round(support[0],2) if support else None,
        'next_support':round(support[1],2) if len(support)>1 else None,
        'nearest_resistance':round(resist[0],2) if resist else None,
        'next_resistance':round(resist[1],2) if len(resist)>1 else None,
        'supply_zones':supply,'demand_zones':demand,'fibonacci':fib,
        'trendlines':trend,'patterns':patterns or ['No simple reversal pattern detected'],
        'swing_range':{'low':round(lo0,2),'high':round(hi0,2)},
        'method':'Daily pivots (3 bars left/right), recent swing levels and latest candle rules; descriptive, not predictive.'}

def load_chart_history(symbol):
    """Fetch daily Yahoo OHLCV and compute visual indicators/price-action context."""
    import yfinance as yf
    d=yf.download(symbol+'.NS',period='2y',interval='1d',progress=False,auto_adjust=True,prepost=False,threads=False,timeout=15)
    if isinstance(d.columns,pd.MultiIndex): d.columns=d.columns.get_level_values(0)
    if d.empty: return None,None
    d=d.dropna().copy()
    needed=('Open','High','Low','Close','Volume')
    if any(c not in d.columns for c in needed) or len(d)<30: return None,None
    d['ema20']=d.Close.ewm(span=20,adjust=False).mean(); d['ema50']=d.Close.ewm(span=50,adjust=False).mean()
    d['rsi14']=_rsi(d.Close,14)
    out=[]
    for ts,row in d.tail(520).iterrows():
        out.append({'time':ts.strftime('%Y-%m-%d'),'open':round(float(row.Open),2),'high':round(float(row.High),2),
          'low':round(float(row.Low),2),'close':round(float(row.Close),2),'volume':int(max(0,row.Volume)),
          'ema20':round(float(row.ema20),2),'ema50':round(float(row.ema50),2),'rsi':round(float(row.rsi14),1)})
    return out,_price_action(d.tail(180).reset_index(drop=False).set_index(d.tail(180).index))

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
    bt=backtest(d); sim=simulate(d,e,sl,tp)
    technical=technical_confirmation(d)
    rg=risk_gate(e,sl,tp,bt,sim,technical)
    confidence=confidence_score(bt,sim,technical)
    return symbol, dict(symbol=symbol,signal="BUY" if rg["verdict"]=="PASS" else "WAIT",
        setup=x.sig,entry=round(e,2),sl=round(float(sl),2),target=round(float(tp),2),
        rsi=round(float(x.rsi),1),vol_x=round(float(x.vr),2),backtest=bt,replay=sim,
        technical_confirmation=technical,confidence_score=confidence,
        risk=rg,market_regime=None,score=confidence,
        reason="; ".join(rg["reasons"]) if rg["reasons"] else "Technical confirmation and positive backtest expectancy passed",
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
    rows.sort(key=lambda r:(r.get("signal")!="BUY",-r.get("confidence_score",r.get("score",0))))
    # Attach daily candles and descriptive price-action analysis to the leading 40 signal rows.
    # This is separate from the unchanged 15m scanner, setup, backtest and risk calculations.
    chart_errors=[]
    if not os.getenv("DEMO"):
        with ThreadPoolExecutor(max_workers=4) as chart_pool:
            jobs={chart_pool.submit(load_chart_history,row["symbol"]):row for row in rows[:40]}
            for job in as_completed(jobs):
                row=jobs[job]
                try:
                    candles,pa=job.result()
                    row["chart"]=candles
                    row["price_action"]=pa
                    if candles is None: chart_errors.append({"symbol":row["symbol"],"error":"Yahoo daily chart history unavailable"})
                except Exception as ex:
                    row["chart"]=None; row["price_action"]=None
                    chart_errors.append({"symbol":row["symbol"],"error":f"Chart: {type(ex).__name__}: {str(ex)[:120]}"})
    else:
        for row in rows[:40]: row["chart"]=None; row["price_action"]=None
    errors.extend(chart_errors)
    ist=dt.datetime.now(dt.timezone(dt.timedelta(hours=5,minutes=30)))
    payload=dict(updated=ist.strftime("%d %b %Y, %H:%M IST"),scanned=scanned,
        universe_count=len(symbols),universe_source=universe_source,data_source="Yahoo Finance 15m",
        chart_data_source="Yahoo Finance daily OHLCV", chart_history_count=sum(bool(r.get("chart")) for r in rows),
        price_action_version="daily-pivots-v1", market_regime=regime,
        demo=bool(os.getenv("DEMO")),config=CFG,rows=rows,errors=errors)
    Path("data.json").write_text(json.dumps(payload,indent=2,default=str),encoding="utf-8")
    print(f"scanned {scanned}/{len(symbols)}, setups {len(rows)}, NIFTY {regime}; source={universe_source}")
if __name__=="__main__":
    main()