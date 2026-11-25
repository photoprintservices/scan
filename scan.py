#!/usr/bin/env python3
# India EOD Swing Intelligence Engine — Dhan-free
# Daily OHLCV, 1–3 session holding, breakout + pullback, research-only.
import os, re, io, json, time, zipfile, datetime as dt, warnings, xml.etree.ElementTree as ET
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import requests
warnings.filterwarnings('ignore')

IST = ZoneInfo('Asia/Kolkata')
UA = {'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36'}
CFG = {
    'engine':'India EOD Swing Intelligence', 'version':'1.1.0', 'timeframe':'1D EOD',
    'holding_sessions':3, 'holding_min_sessions':1, 'capital':100000,
    'risk_fraction':0.005, 'max_position_fraction':0.25, 'min_rr':1.5,
    'volume_multiple':1.2, 'breakout_lookback':20, 'ema_fast':20, 'ema_slow':50,
    'atr_period':14, 'rsi_period':14, 'backtest_horizon':3, 'min_backtest_trades':5,
    'cost_pct_round_trip':0.15, 'monte_carlo_paths':1000, 'chart_rows':50,
    'chart_bars':520, 'universe':'v6.1.1 curated + NSE current F&O bhavcopy'
}
CURATED = '''TCS INFY WIPRO HCLTECH TECHM HDFCBANK ICICIBANK SBIN KOTAKBANK AXISBANK INDUSINDBK BAJFINANCE BAJAJFINSV SHRIRAMFIN SBILIFE HDFCLIFE MARUTI M&M EICHERMOT HEROMOTOCO ITC HINDUNILVR NESTLEIND BRITANNIA TATACONSUM JSWSTEEL TATASTEEL HINDALCO SUNPHARMA CIPLA DRREDDY APOLLOHOSP RELIANCE ONGC BPCL NTPC POWERGRID COALINDIA LT ADANIPORTS ULTRACEMCO GRASIM BEL ADANIENT BHARTIARTL TITAN ASIANPAINT TRENT FEDERALBNK IDFCFIRSTB AUBANK BANDHANBNK RBLBANK YESBANK CHOLAFIN MUTHOOTFIN MANAPPURAM PFC RECLTD LICHSGFIN SBICARD ICICIGI ICICIPRULI HDFCAMC LICI BSE CDSL JIOFIN POLICYBZR IRFC LTIM PERSISTENT COFORGE MPHASIS OFSS KPITTECH TATAELXSI BAJAJ-AUTO TVSMOTOR ASHOKLEY BHARATFORG BOSCHLTD MOTHERSON BALKRISIND TIINDIA UNOMINDA DABUR GODREJCP MARICO COLPAL UNITDSPR VBL VEDL NMDC SAIL JINDALSTEL NATIONALUM HINDCOPPER APLAPOLLO DIVISLAB LUPIN AUROPHARMA TORNTPHARM ZYDUSLIFE ALKEM MANKIND BIOCON MAXHEALTH FORTIS GLENMARK LAURUSLABS IOC GAIL TATAPOWER ADANIGREEN ADANIPOWER PETRONET OIL HINDPETRO NHPC JSWENERGY SIEMENS ABB HAL BHEL CGPOWER POLYCAB HAVELLS KEI CUMMINSIND RVNL CONCOR DIXON ETERNAL DMART INDIGO PIDILITIND NAUKRI SRF UPL BANKBARODA PNB CANBK UNIONBANK BANKINDIA INDIANB DLF GODREJPROP LODHA OBEROIRLTY PRESTIGE PHOENIXLTD'''.split()
WORLD = [('^GSPC','S&P 500'),('^IXIC','Nasdaq'),('^DJI','Dow'),('^N225','Nikkei'),('^HSI','Hang Seng'),('^FTSE','FTSE'),('^GDAXI','DAX')]
INDIA = [('^NSEI','Nifty 50'),('^NSEBANK','Bank Nifty'),('^BSESN','Sensex'),('^INDIAVIX','India VIX')]
MACRO = [('CL=F','Crude'),('GC=F','Gold'),('USDINR=X','USD/INR'),('^TNX','US 10Y')]
SECTOR_INDICES = [('^CNXIT','IT'),('^CNXFIN','Fin Services'),('^CNXAUTO','Auto'),('^CNXFMCG','FMCG'),('^CNXMETAL','Metal'),('^CNXPHARMA','Pharma'),('^CNXENERGY','Energy'),('^CNXINFRA','Infra'),('^CNXPSUBANK','PSU Bank'),('^CNXREALTY','Realty')]
SECTOR_GROUPS = {'IT':'TCS INFY WIPRO HCLTECH TECHM LTIM PERSISTENT COFORGE MPHASIS OFSS KPITTECH TATAELXSI','Bank':'HDFCBANK ICICIBANK SBIN KOTAKBANK AXISBANK INDUSINDBK FEDERALBNK IDFCFIRSTB AUBANK BANDHANBNK RBLBANK YESBANK BANKBARODA PNB CANBK UNIONBANK BANKINDIA INDIANB','Fin Services':'BAJFINANCE BAJAJFINSV SHRIRAMFIN CHOLAFIN MUTHOOTFIN MANAPPURAM PFC RECLTD LICHSGFIN SBICARD ICICIGI ICICIPRULI HDFCAMC LICI BSE CDSL JIOFIN POLICYBZR IRFC SBILIFE HDFCLIFE','Auto':'MARUTI M&M EICHERMOT HEROMOTOCO BAJAJ-AUTO TVSMOTOR ASHOKLEY BHARATFORG BOSCHLTD MOTHERSON BALKRISIND TIINDIA UNOMINDA','FMCG':'ITC HINDUNILVR NESTLEIND BRITANNIA TATACONSUM DABUR GODREJCP MARICO COLPAL UNITDSPR VBL','Metal':'JSWSTEEL TATASTEEL HINDALCO VEDL NMDC SAIL JINDALSTEL NATIONALUM HINDCOPPER APLAPOLLO','Pharma':'SUNPHARMA CIPLA DRREDDY APOLLOHOSP DIVISLAB LUPIN AUROPHARMA TORNTPHARM ZYDUSLIFE ALKEM MANKIND BIOCON MAXHEALTH FORTIS GLENMARK LAURUSLABS','Energy':'RELIANCE ONGC BPCL NTPC POWERGRID COALINDIA IOC GAIL TATAPOWER ADANIGREEN ADANIPOWER PETRONET OIL HINDPETRO NHPC JSWENERGY','Infra':'LT ADANIPORTS ULTRACEMCO GRASIM BEL ADANIENT SIEMENS ABB HAL BHEL CGPOWER POLYCAB HAVELLS KEI CUMMINSIND RVNL CONCOR DIXON','Realty':'DLF GODREJPROP LODHA OBEROIRLTY PRESTIGE PHOENIXLTD'}
SYMBOL_SECTOR={sym:sector for sector,items in SECTOR_GROUPS.items() for sym in items.split()}

SESSION = requests.Session(); SESSION.headers.update(UA)
def now_ist(): return dt.datetime.now(IST)
def safe_float(x):
    try:
        v=float(x)
        return v if np.isfinite(v) else None
    except Exception: return None
def clean_symbol(x):
    s=str(x or '').strip().upper(); s=re.sub(r'-(EQ|BE|BZ)$','',s)
    return s if re.fullmatch(r'[A-Z][A-Z0-9&._-]{0,24}',s) else ''
def yf_history(symbol, period='2y'):
    if os.getenv('DEMO'):
        rng=np.random.default_rng(sum(map(ord,symbol)))
        ix=pd.bdate_range(end=now_ist().date(),periods=520)
        close=1000*np.exp(np.cumsum(rng.normal(.0003,.018,len(ix))))
        op=np.r_[close[0],close[:-1]]*(1+rng.normal(0,.004,len(ix)))
        hi=np.maximum(op,close)*(1+abs(rng.normal(0,.006,len(ix))))
        lo=np.minimum(op,close)*(1-abs(rng.normal(0,.006,len(ix))))
        return pd.DataFrame({'Open':op,'High':hi,'Low':lo,'Close':close,'Volume':rng.lognormal(14,.45,len(ix))},index=ix)
    try:
        import yfinance as yf
        d=yf.download(symbol+'.NS',period=period,interval='1d',auto_adjust=True,actions=False,progress=False,threads=False,timeout=25)
        if isinstance(d.columns,pd.MultiIndex): d.columns=d.columns.get_level_values(0)
        if d is None or d.empty: return pd.DataFrame()
        d=d.rename(columns={str(c).title():str(c).title() for c in d.columns})
        return d[[c for c in ('Open','High','Low','Close','Volume') if c in d]].dropna(subset=['Close']).copy()
    except Exception: return pd.DataFrame()
def yf_index(symbol,period='1y'):
    if os.getenv('DEMO'): return yf_history('NIFTY')
    try:
        import yfinance as yf
        d=yf.download(symbol,period=period,interval='1d',auto_adjust=True,progress=False,threads=False,timeout=20)
        if isinstance(d.columns,pd.MultiIndex): d.columns=d.columns.get_level_values(0)
        return d.dropna(subset=['Close']) if d is not None and not d.empty else pd.DataFrame()
    except Exception: return pd.DataFrame()

def nse_session():
    s=requests.Session(); s.headers.update({**UA,'Accept':'application/json','Referer':'https://www.nseindia.com/'})
    try: s.get('https://www.nseindia.com',timeout=15)
    except Exception: pass
    return s

def fetch_fo_bhav():
    """NSE daily derivatives bhavcopy only; no broker or Dhan endpoints."""
    if os.getenv('DEMO'): return {},None,'DEMO: synthetic OI not generated'
    for k in range(8):
        day=now_ist().date()-dt.timedelta(days=k)
        if day.weekday()>=5: continue
        url=f'https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{day:%Y%m%d}_F_0000.csv.zip'
        try:
            r=SESSION.get(url,timeout=25)
            if r.status_code!=200: continue
            z=zipfile.ZipFile(io.BytesIO(r.content)); name=z.namelist()[0]
            df=pd.read_csv(z.open(name),low_memory=False); df.columns=[str(c).strip() for c in df.columns]
            def col(*names): return next((n for n in names if n in df.columns),None)
            symc=col('TckrSymb','TckrSymbNm','Underlying','SYMBOL')
            typc=col('FinInstrmTp','FinInstrmTyp','Instrument Type')
            oic=col('OpnIntrst','OpnIntrstQty','Open Interest')
            chgc=col('ChngInOpnIntrst','ChngInOpnIntrstQty','Change in OI')
            pricec=col('ClsPric','ClsgPric','Close Price')
            prevc=col('PrvsClsgPric','PrevClsgPric','Previous Close')
            if not all([symc,oic,chgc]): continue
            if typc: df=df[df[typc].astype(str).str.upper().isin(['STF','FUTSTK','FUTSTK '])]
            df[symc]=df[symc].map(clean_symbol); df[oic]=pd.to_numeric(df[oic],errors='coerce'); df[chgc]=pd.to_numeric(df[chgc],errors='coerce')
            out={}
            for sym,g in df.groupby(symc):
                if not sym: continue
                row=g.iloc[0]; cur=safe_float(row[oic]); change=safe_float(row[chgc]); base=(cur-change) if cur is not None and change is not None else None
                oi_pct=(change/base*100) if base and base>0 and change is not None else None
                px=safe_float(row[pricec]) if pricec else None; prev=safe_float(row[prevc]) if prevc else None
                px_pct=((px/prev-1)*100) if px and prev and prev>0 else None
                out[sym]={'oi':cur,'oich':oi_pct,'fut_price_change_pct':px_pct,'oi_source':'NSE_FO_BHAVCOPY','oi_asof':str(day)}
            if out: return out,day,None
        except Exception: continue
    return {},None,'NSE F&O bhavcopy unavailable / format changed / archive not published'

def fii_dii():
    try:
        s=nse_session(); r=s.get('https://www.nseindia.com/api/fiidiiTradeReact',timeout=20)
        return r.json() if r.status_code==200 else None
    except Exception: return None

def nse_volume_gainers():
    if os.getenv('DEMO'): return []
    try:
        s=nse_session(); r=s.get('https://www.nseindia.com/api/live-analysis-volume-gainers',timeout=18)
        j=r.json() if r.status_code==200 else {}
        return [{'symbol':x.get('symbol'),'change_pct':safe_float(x.get('pChange') or x.get('change')),'volume':x.get('volume')} for x in (j.get('data') or [])[:30]] if isinstance(j,dict) else []
    except Exception:return []

def mwpl_pct(names):
    if os.getenv('DEMO'): return {}
    for k in range(6):
        day=now_ist().date()-dt.timedelta(days=k)
        if day.weekday()>=5:continue
        for url in (f'https://nsearchives.nseindia.com/archives/nsccl/mwpl/combineoi_{day:%d%m%Y}.zip',f'https://nsearchives.nseindia.com/content/nsccl/combineoi_{day:%d%m%Y}.zip'):
            try:
                r=SESSION.get(url,timeout=20)
                if r.status_code!=200:continue
                z=zipfile.ZipFile(io.BytesIO(r.content)); df=pd.read_csv(z.open(z.namelist()[0])); df.columns=[str(c).strip() for c in df.columns]
                sc=next(c for c in df.columns if 'symbol' in c.lower()); oc=next(c for c in df.columns if 'open interest' in c.lower() or c.lower() in ('oi','total oi')); lc=next(c for c in df.columns if 'mwpl' in c.lower() or 'limit' in c.lower())
                df[sc]=df[sc].astype(str).str.strip(); df=df.drop_duplicates(sc).set_index(sc)
                return {sym:round(float(df.loc[sym,oc]/df.loc[sym,lc]*100),1) for sym in names if sym in df.index and safe_float(df.loc[sym,lc])}
            except Exception:continue
    return {}

def corporate_events(symbols,session_date):
    out={}; s=nse_session()
    for sym in symbols[:35]:
        found=[]
        for path,keydate,keytext in [('corporates-corporateActions','exDate','subject'),('event-calendar','date','purpose')]:
            try:
                r=s.get('https://www.nseindia.com/api/'+path,params={'index':'equities','symbol':sym},timeout=12)
                j=r.json() if r.status_code==200 else None
                if isinstance(j,list):
                    for x in j:
                        d=pd.to_datetime(x.get(keydate),errors='coerce',dayfirst=True)
                        if pd.notna(d) and -2 <= (d.date()-session_date).days <= 30:
                            found.append({'date':str(d.date()),'event':str(x.get(keytext) or x.get('bm_desc') or '')[:100]})
            except Exception: pass
        if found: out[sym]=found
    return out

def economic_events():
    if os.getenv('DEMO'): return []
    try:
        r=SESSION.get('https://nfs.faireconomy.media/ff_calendar_thisweek.json',timeout=20); r.raise_for_status(); data=r.json(); out=[]; now=now_ist()
        for e in data if isinstance(data,list) else []:
            if str(e.get('impact','')).lower()!='high' or not e.get('date'): continue
            try:
                t=dt.datetime.fromisoformat(str(e['date']).replace('Z','+00:00'))
                if t.tzinfo is None:t=t.replace(tzinfo=dt.timezone.utc)
                t=t.astimezone(IST)
            except Exception:continue
            dh=(t-now).total_seconds()/3600
            if -72<=dh<=168: out.append({'time':t.strftime('%d %b %H:%M IST'),'country':e.get('country'),'title':e.get('title'),'actual':e.get('actual'),'forecast':e.get('forecast'),'previous':e.get('previous'),'status':'UPCOMING' if dh>0 else 'RELEASED' if e.get('actual') else 'PAST — ACTUAL NOT UPDATED','hours_from_now':round(dh,1)})
        return sorted(out,key=lambda x:x['hours_from_now'])
    except Exception:return []

def google_news(query,n=5):
    if os.getenv('DEMO'): return []
    try:
        r=SESSION.get('https://news.google.com/rss/search',params={'q':query,'hl':'en-IN','gl':'IN','ceid':'IN:en'},timeout=18); r.raise_for_status()
        root=ET.fromstring(r.content); out=[]
        for item in root.findall('.//item')[:n]:
            out.append({'title':item.findtext('title',''),'url':item.findtext('link',''),'published':item.findtext('pubDate',''),'source':item.findtext('source','')})
        return out
    except Exception:return []

def screener_shareholding(sym):
    if os.getenv('DEMO'): return {}
    for url in (f'https://www.screener.in/company/{sym}/consolidated/',f'https://www.screener.in/company/{sym}/'):
        try:
            r=SESSION.get(url,timeout=18)
            if r.status_code!=200:continue
            m=re.search(r'id="quarterly-shp".*?(<table.*?</table>)',r.text,re.S)
            if not m:continue
            table=pd.read_html(io.StringIO(m.group(1)))[0]; labels=table.iloc[:,0].astype(str).str.strip(); result={}
            for label in ('Promoters','FIIs','DIIs','Public'):
                rr=table[labels.str.startswith(label)]
                if not rr.empty:
                    vals=[safe_float(str(v).replace('%','').replace(',','')) for v in rr.iloc[0,1:]]
                    vals=[v for v in vals if v is not None]
                    if vals:result[label]={'latest':vals[-1],'previous':vals[-2] if len(vals)>1 else None,'change_pp':round(vals[-1]-vals[-2],2) if len(vals)>1 else None}
            if result:return result
        except Exception:pass
    return {}

def rsi(series,n=14):
    delta=series.diff(); gain=delta.clip(lower=0).ewm(alpha=1/n,adjust=False,min_periods=n).mean(); loss=(-delta.clip(upper=0)).ewm(alpha=1/n,adjust=False,min_periods=n).mean()
    rs=gain/loss.replace(0,np.nan); out=100-100/(1+rs); return out.mask((loss==0)&(gain>0),100).fillna(50)
def enrich(d):
    x=d.copy(); c=x.Close; prev=c.shift()
    x['ema20']=c.ewm(span=20,adjust=False).mean(); x['ema50']=c.ewm(span=50,adjust=False).mean()
    tr=pd.concat([x.High-x.Low,(x.High-prev).abs(),(x.Low-prev).abs()],axis=1).max(axis=1)
    x['atr']=tr.ewm(alpha=1/CFG['atr_period'],adjust=False,min_periods=CFG['atr_period']).mean()
    x['rsi']=rsi(c); x['prior_high']=x.High.rolling(20).max().shift(); x['prior_low']=x.Low.rolling(20).min().shift()
    x['vol_x']=x.Volume/x.Volume.shift().rolling(20).mean()
    x['macd']=c.ewm(span=12,adjust=False).mean()-c.ewm(span=26,adjust=False).mean()
    x['macd_signal']=x['macd'].ewm(span=9,adjust=False).mean()
    x['macd_hist']=x['macd']-x['macd_signal']
    return x

def _pivot_points(values,left=3,right=3):
    highs=[];lows=[];a=np.asarray(values,dtype=float)
    for i in range(left,len(a)-right):
        w=a[i-left:i+right+1]
        if a[i]==np.max(w) and np.sum(w==a[i])==1:highs.append(i)
        if a[i]==np.min(w) and np.sum(w==a[i])==1:lows.append(i)
    return highs,lows

def confirmed_pivots(d,k=3):
    h=d.High.values; l=d.Low.values; raw=[]
    for i in range(k,len(d)-k):
        if h[i]>=h[i-k:i+k+1].max():raw.append((i,'H',float(h[i])))
        if l[i]<=l[i-k:i+k+1].min():raw.append((i,'L',float(l[i])))
    raw.sort(key=lambda x:(x[0],x[1])); out=[]
    for p in raw:
        if out and out[-1][1]==p[1]:
            if (p[1]=='H' and p[2]>=out[-1][2]) or (p[1]=='L' and p[2]<=out[-1][2]):out[-1]=p
        else:out.append(p)
    return out

def harmonic_candidate(d,atr):
    pv=confirmed_pivots(d.tail(180).reset_index(drop=True),3); zig=[]
    for p in pv:
        if not zig:zig.append(p);continue
        last=zig[-1]
        if p[1]==last[1]:
            if (p[1]=='H' and p[2]>=last[2]) or (p[1]=='L' and p[2]<=last[2]):zig[-1]=p
        elif abs(p[2]-last[2])>=max(1.5*atr,float(d.Close.iloc[-1])*.015):zig.append(p)
    if len(zig)<5:return None
    q=zig[-5:]; types=''.join(x[1] for x in q)
    if types not in ('LHLHL','HLHLH'):return None
    X,A,B,C,D=[x[2] for x in q]; xa=abs(A-X);ab=abs(A-B);bc=abs(C-B);cd=abs(C-D)
    if min(xa,ab,bc,cd)<=0:return None
    rab=ab/xa;rbc=bc/ab;rcd=cd/bc;rxd=abs(A-D)/xa
    tests={
      'Gartley':(.55<=rab<=.68 and .382<=rbc<=.886 and .70<=rxd<=.84 and 1.0<=rcd<=1.7),
      'Bat':(.35<=rab<=.55 and .382<=rbc<=.886 and .82<=rxd<=.95 and 1.5<=rcd<=2.7),
      'Butterfly':(.70<=rab<=.86 and .382<=rbc<=.886 and 1.2<=rxd<=1.7 and 1.5<=rcd<=2.4),
      'Crab':(.35<=rab<=.68 and .382<=rbc<=.886 and 1.5<=rxd<=1.72 and 2.0<=rcd<=3.8),
      'Deep Crab':(.82<=rab<=.92 and .382<=rbc<=.886 and 1.5<=rxd<=1.72 and 2.0<=rcd<=3.8)}
    name=next((k for k,v in tests.items() if v),None)
    if not name:return None
    return {'name':name,'direction':'BULL' if types=='LHLHL' else 'BEAR','ratios':[round(rab,3),round(rbc,3),round(rcd,3),round(rxd,3)],'status':'CANDIDATE — PRZ/reversal confirmation required','points':[{'index':int(x[0]),'price':round(float(x[2]),2),'label':lab} for x,lab in zip(q,'XABCD')]}

def elliott_candidate(d,atr):
    pv=confirmed_pivots(d.tail(180).reset_index(drop=True),3); zig=[]
    for p in pv:
        if not zig:zig.append(p);continue
        last=zig[-1]
        if p[1]==last[1]:
            if (p[1]=='H' and p[2]>=last[2]) or (p[1]=='L' and p[2]<=last[2]):zig[-1]=p
        elif abs(p[2]-last[2])>=max(1.2*atr,float(d.Close.iloc[-1])*.012):zig.append(p)
    if len(zig)>=5:
        q=zig[-5:]; ty=''.join(x[1] for x in q); p=[x[2] for x in q]; close=float(d.Close.iloc[-1])
        if ty=='LHLHL':
            l0,h1,l2,h3,l4=p; w1=h1-l0; w3=h3-l2
            if l2>l0 and h3>h1 and l4>h1 and w3>w1 and .236<=(h3-l4)/max(w3,1e-9)<=.62 and close>l4:return 'Wave-4 pullback candidate; Wave-5 extension possible'
    return None

def gann_levels(close,anchor=None):
    root=np.sqrt(max(close,.01)); sq=[round((root+.25*k)**2,2) for k in range(-8,9) if k]
    near=sorted(sq,key=lambda x:abs(x-close))[:4]
    fan=None
    if anchor:
        i1,p1,i2,p2=anchor; unit=(p2-p1)/max(i2-i1,1); bars=max(0,179-i2)
        fan={'1x1':round(p2+unit*bars,2),'2x1':round(p2+2*unit*bars,2),'1x2':round(p2+.5*unit*bars,2)}
    return {'square_of_9_nearby':sorted(near),'fan_projection':fan,'note':'Heuristic geometry only; not a standalone trade signal'}

def price_action(d):
    close=float(d.Close.iloc[-1]); high=float(d.High.iloc[-1]); low=float(d.Low.iloc[-1]); tr=pd.concat([d.High-d.Low,(d.High-d.Close.shift()).abs(),(d.Low-d.Close.shift()).abs()],axis=1).max(axis=1)
    atr=float(tr.rolling(14).mean().iloc[-1]) if len(d)>=14 else max(high-low,close*.01); atr=atr if np.isfinite(atr) and atr>0 else max(close*.01,.01)
    z=d.tail(180); hi_idx,lo_idx=_pivot_points(z.High.values)[0],_pivot_points(z.Low.values)[1]
    highs=[(int(i),float(z.High.iloc[i])) for i in hi_idx[-6:]]; lows=[(int(i),float(z.Low.iloc[i])) for i in lo_idx[-6:]]
    resist=sorted([v for _,v in highs if v>close]); support=sorted([v for _,v in lows if v<close],reverse=True)
    supply=[{'low':round(v-.35*atr,2),'high':round(v+.15*atr,2),'pivot_index':i} for i,v in highs[-2:]]
    demand=[{'low':round(v-.15*atr,2),'high':round(v+.35*atr,2),'pivot_index':i} for i,v in lows[-2:]]
    structure='RANGE / UNCONFIRMED'
    if len(highs)>=2 and len(lows)>=2:
        if highs[-1][1]>highs[-2][1] and lows[-1][1]>lows[-2][1]:structure='HH + HL (BULLISH)'
        elif highs[-1][1]<highs[-2][1] and lows[-1][1]<lows[-2][1]:structure='LH + LL (BEARISH)'
        elif highs[-1][1]>highs[-2][1]:structure='HIGHER HIGH; LOW STRUCTURE MIXED'
        elif highs[-1][1]<highs[-2][1]:structure='LOWER HIGH; LOW STRUCTURE MIXED'
    swlo=float(lows[-1][1]) if lows else float(z.Low.tail(60).min()); swhi=float(highs[-1][1]) if highs else float(z.High.tail(60).max()); lo0,hi0=sorted([swlo,swhi]); span=hi0-lo0
    fib={k:round(hi0-span*r,2) for k,r in [('0.236',.236),('0.382',.382),('0.500',.5),('0.618',.618),('0.786',.786)]} if span>0 else {}
    trend=[]
    if len(lows)>=2:trend.append({'kind':'Swing support trendline','x1':lows[-2][0],'y1':round(lows[-2][1],2),'x2':lows[-1][0],'y2':round(lows[-1][1],2)})
    if len(highs)>=2:trend.append({'kind':'Swing resistance trendline','x1':highs[-2][0],'y1':round(highs[-2][1],2),'x2':highs[-1][0],'y2':round(highs[-1][1],2)})
    o=float(d.Open.iloc[-1]); po=float(d.Open.iloc[-2]); pc=float(d.Close.iloc[-2]); body=abs(close-o); rng=max(high-low,1e-9); lower=min(o,close)-low; upper=high-max(o,close); patterns=[]
    if close>o and pc<po and close>=po and o<=pc:patterns.append('Bullish engulfing')
    if close<o and pc>po and close<=po and o>=pc:patterns.append('Bearish engulfing')
    if lower>=2*max(body,1e-9) and upper<=.35*max(body,1e-9):patterns.append('Hammer-like candle')
    if upper>=2*max(body,1e-9) and lower<=.35*max(body,1e-9):patterns.append('Shooting-star-like candle')
    # Fixed-range volume profile approximation: distribute each candle volume across price bins.
    profile=z.tail(120); plo=float(profile.Low.min()); phi=float(profile.High.max()); poc=vah=val=None
    if phi>plo and profile.Volume.sum()>0:
        edges=np.linspace(plo,phi,41); bins=np.zeros(40)
        for hh,ll,vv in zip(profile.High.values,profile.Low.values,profile.Volume.values):
            a=max(0,min(39,int(np.searchsorted(edges,ll,'right')-1))); b=max(a,min(39,int(np.searchsorted(edges,hh,'left')-1))); bins[a:b+1]+=vv/(b-a+1)
        pi=int(bins.argmax()); aa=bb=pi; acc=bins[pi]
        while acc<.70*bins.sum() and (aa>0 or bb<39):
            up=bins[bb+1] if bb<39 else -1; dn=bins[aa-1] if aa>0 else -1
            if up>=dn:bb+=1;acc+=bins[bb]
            else:aa-=1;acc+=bins[aa]
        ctr=(edges[:-1]+edges[1:])/2; poc=round(float(ctr[pi]),2); vah=round(float(edges[bb+1]),2); val=round(float(edges[aa]),2)
    harm=harmonic_candidate(d,atr); ell=elliott_candidate(d,atr); gann=gann_levels(close, (lows[-2][0],lows[-2][1],lows[-1][0],lows[-1][1]) if len(lows)>=2 else None)
    # Original LT engine pattern family: H&S / inverse H&S plus double top/bottom candidates.
    piv=confirmed_pivots(z.reset_index(drop=True),3); chart_patterns=[]
    elliott_points=[{'index':int(x[0]),'price':round(float(x[2]),2),'label':str(i)} for i,x in enumerate(piv[-6:])] if ell else []
    if len(piv)>=5:
        q=piv[-5:];ty=''.join(x[1] for x in q);pp=[x[2] for x in q]
        if ty=='HLHLH' and pp[2]>max(pp[0],pp[4]) and abs(pp[0]-pp[4])/max((pp[0]+pp[4])/2,1e-9)<=.10:
            neck=(pp[1]+pp[3])/2;chart_patterns.append({'name':'Head & Shoulders','side':'BEAR','neckline':round(neck,2),'status':'BROKEN' if close<neck else 'FORMING'})
        if ty=='LHLHL' and pp[2]<min(pp[0],pp[4]) and abs(pp[0]-pp[4])/max((pp[0]+pp[4])/2,1e-9)<=.10:
            neck=(pp[1]+pp[3])/2;chart_patterns.append({'name':'Inverse Head & Shoulders','side':'BULL','neckline':round(neck,2),'status':'BROKEN' if close>neck else 'FORMING'})
    # Measured-move / AB=CD / consolidation-range projections (candidate levels only).
    measured=[]
    if len(piv)>=3:
        q=piv[-3:]
        if ''.join(x[1] for x in q)=='LHL':
            A,B,C=[x[2] for x in q]
            if C>A and close>B:
                measured.append({'name':'AB=CD measured move','level':round(C+(B-A),2),'side':'BULL'})
                measured.append({'name':'AB=CD 1.272 extension','level':round(C+1.272*(B-A),2),'side':'BULL'})
        if ''.join(x[1] for x in q)=='HLH':
            A,B,C=[x[2] for x in q]
            if C<A and close<B:
                measured.append({'name':'Bearish measured move','level':round(C-(A-B),2),'side':'BEAR'})
    for nbox in (20,30,40):
        if len(d)>nbox+5:
            seg=d.iloc[-(nbox+5):-5];bh=float(seg.High.max());bl=float(seg.Low.min())
            if (bh-bl)/max(bl,1e-9)<.12 and close>bh:
                measured.append({'name':f'{nbox}-bar range breakout projection','level':round(bh+(bh-bl),2),'side':'BULL'});break
            if (bh-bl)/max(bl,1e-9)<.12 and close<bl:
                measured.append({'name':f'{nbox}-bar range breakdown projection','level':round(bl-(bh-bl),2),'side':'BEAR'});break
    # Wick-based liquidity references from the same rejection logic used by LT weekly/monthly analysis.
    wick_liquidity=[]
    for j in range(max(0,len(z)-150),len(z)):
        oo,hh,ll,cc=map(float,(z.Open.iloc[j],z.High.iloc[j],z.Low.iloc[j],z.Close.iloc[j]))
        rr=max(hh-ll,1e-9);up=hh-max(oo,cc);dn=min(oo,cc)-ll
        if up>=.40*rr and up>=.5*atr:wick_liquidity.append({'kind':'RESISTANCE / upper-wick liquidity','level':round(hh,2)})
        if dn>=.40*rr and dn>=.5*atr:wick_liquidity.append({'kind':'SUPPORT / lower-wick liquidity','level':round(ll,2)})
    # Cluster pivot levels into confluence bands rather than flooding the chart with every pivot.
    levels=sorted([(v,'SUPPORT') for v in support[:6]]+[(v,'RESISTANCE') for v in resist[:6]])
    confluence=[]
    for val,kind in levels:
        if confluence and confluence[-1]['kind']==kind and abs(val-confluence[-1]['mid'])<=.5*atr:
            zc=confluence[-1];zc['levels'].append(round(val,2));zc['mid']=round(float(np.mean(zc['levels'])),2)
        else:confluence.append({'kind':kind,'mid':round(val,2),'levels':[round(val,2)]})
    return {'as_of':str(pd.Timestamp(d.index[-1]).date()),'structure':structure,'nearest_support':round(support[0],2) if support else None,'next_support':round(support[1],2) if len(support)>1 else None,'nearest_resistance':round(resist[0],2) if resist else None,'next_resistance':round(resist[1],2) if len(resist)>1 else None,'supply_zones':supply,'demand_zones':demand,'fibonacci':fib,'trendlines':trend,'patterns':patterns or ['No simple reversal pattern detected'],'swing_range':{'low':round(lo0,2),'high':round(hi0,2)},'volume_profile':{'poc':poc,'vah':vah,'val':val},'harmonic_candidate':harm,'elliott_candidate':ell,'gann_levels':gann,'chart_patterns':chart_patterns,'measured_moves':measured,'wick_liquidity':wick_liquidity[-12:],'confluence_levels':confluence,'elliott_points':elliott_points,'method':'Adapted Intelligence Engine v6.1.1: supply/demand, swing trendlines, Fibonacci, harmonic (Gartley/Bat/Butterfly/Crab/Deep Crab), Elliott, Gann Square-of-9/fan, H&S/double patterns, fixed-range volume profile, wick liquidity, BOS/CHOCH, FVG/OB, Wyckoff, liquidity sweeps and measured moves. All rule-based candidates.'}


def pa_evidence(d):
    out=[]
    if len(d)<60:return out
    o,h,l,c,v=[d[k].astype(float).values for k in ('Open','High','Low','Close','Volume')]; n=len(c); body=abs(c[-1]-o[-1]); rng=max(h[-1]-l[-1],1e-9); med=float(np.nanmedian(v[-21:-1])); vr=v[-1]/med if med>0 else 0
    lower=min(o[-1],c[-1])-l[-1]; upper=h[-1]-max(o[-1],c[-1])
    if c[-2]<o[-2] and c[-1]>o[-1] and c[-1]>=o[-2] and o[-1]<=c[-2]:out.append(('Candlestick','BULL','Bullish engulfing'))
    if c[-2]>o[-2] and c[-1]<o[-1] and c[-1]<=o[-2] and o[-1]>=c[-2]:out.append(('Candlestick','BEAR','Bearish engulfing'))
    if lower>=max(2*body,.45*rng) and c[-1]>=l[-1]+.6*rng:out.append(('Candlestick','BULL','Hammer / lower-wick rejection'))
    if upper>=max(2*body,.45*rng) and c[-1]<=l[-1]+.4*rng:out.append(('Candlestick','BEAR','Shooting-star / upper-wick rejection'))
    ph=float(np.max(h[-21:-1])); pl=float(np.min(l[-21:-1]))
    if c[-1]>ph:out.append(('Market Structure','BULL',f'BOS above {ph:.2f}; volume {vr:.2f}x'))
    if c[-1]<pl:out.append(('Market Structure','BEAR',f'BOS below {pl:.2f}; volume {vr:.2f}x'))
    boxh=float(np.max(h[-41:-1])); boxl=float(np.min(l[-41:-1]))
    if l[-1]<boxl and c[-1]>boxl and vr>=1.2:out.append(('Wyckoff','BULL',f'Spring/reclaim {boxl:.2f}; volume {vr:.2f}x'))
    if h[-1]>boxh and c[-1]<boxh and vr>=1.2:out.append(('Wyckoff','BEAR',f'Upthrust/rejection {boxh:.2f}; volume {vr:.2f}x'))
    if h[-1]>ph and c[-1]<ph:out.append(('Liquidity Sweep','BEAR',f'Buy-side sweep above {ph:.2f}'))
    if l[-1]<pl and c[-1]>pl:out.append(('Liquidity Sweep','BULL',f'Sell-side sweep below {pl:.2f}'))
    if l[-1]>h[-3]:out.append(('SMC / FVG','BULL',f'Bullish FVG {h[-3]:.2f}-{l[-1]:.2f}'))
    if h[-1]<l[-3]:out.append(('SMC / FVG','BEAR',f'Bearish FVG {h[-1]:.2f}-{l[-3]:.2f}'))
    atr=float(np.nanmean([max(h[j]-l[j],abs(h[j]-c[j-1]),abs(l[j]-c[j-1])) for j in range(max(1,n-15),n)]))
    if atr>0 and c[-2]>o[-2] and c[-2]-o[-2]>1.5*atr and c[-2]>np.max(h[-12:-2]):
        j=next((j for j in range(n-3,max(-1,n-8),-1) if c[j]<o[j]),None)
        if j is not None:out.append(('SMC / Order Block','BULL',f'Demand OB candidate {l[j]:.2f}-{h[j]:.2f}'))
    if atr>0 and o[-2]>c[-2] and o[-2]-c[-2]>1.5*atr and c[-2]<np.min(l[-12:-2]):
        j=next((j for j in range(n-3,max(-1,n-8),-1) if c[j]>o[j]),None)
        if j is not None:out.append(('SMC / Order Block','BEAR',f'Supply OB candidate {l[j]:.2f}-{h[j]:.2f}'))
    # Double top/bottom candidates: explicitly unconfirmed until neckline breaks.
    look=min(80,n-1); tol=float(np.nanmedian(c[-20:]))*.018; hh=h[-look:]; ll=l[-look:]
    tops=sorted([(i,float(hh[i])) for i in range(2,look-2) if hh[i]>=np.max(hh[i-2:i+3])]); bottoms=sorted([(i,float(ll[i])) for i in range(2,look-2) if ll[i]<=np.min(ll[i-2:i+3])])
    for i in range(len(tops)):
        for j in range(i+1,len(tops)):
            i1,p1=tops[i];i2,p2=tops[j]
            if i2-i1>=8 and abs(p1-p2)<=tol:
                neck=float(np.min(l[-look+i1:-look+i2+1]));out.append(('Chart Pattern','BEAR',f'Double Top candidate; neckline {neck:.2f}; '+('broken' if c[-1]<neck else 'unconfirmed')));break
        else:continue
        break
    for i in range(len(bottoms)):
        for j in range(i+1,len(bottoms)):
            i1,p1=bottoms[i];i2,p2=bottoms[j]
            if i2-i1>=8 and abs(p1-p2)<=tol:
                neck=float(np.max(h[-look+i1:-look+i2+1]));out.append(('Chart Pattern','BULL',f'Double Bottom candidate; neckline {neck:.2f}; '+('broken' if c[-1]>neck else 'unconfirmed')));break
        else:continue
        break
    # Flag / compression candidates, never promoted to a confirmed trade by themselves.
    impulse=(c[-11]/c[-26]-1)*100 if n>=30 else 0; consolidation=(np.max(h[-10:])-np.min(l[-10:]))/max(c[-10],1e-9)*100 if n>=30 else 999
    if impulse>7 and consolidation<max(4,abs(impulse)*.55):out.append(('Chart Pattern','BULL',f'Bull-flag candidate; impulse {impulse:.1f}%, consolidation {consolidation:.1f}%'))
    elif impulse<-7 and consolidation<max(4,abs(impulse)*.55):out.append(('Chart Pattern','BEAR',f'Bear-flag candidate; impulse {impulse:.1f}%, consolidation {consolidation:.1f}%'))
    return out

def signal_at(d,i):
    if i<60:return None
    x=d.iloc[i]; px=float(x.Close); atr=safe_float(x.atr); e20=float(x.ema20); e50=float(x.ema50); vr=safe_float(x.vol_x) or 0; r=float(x.rsi)
    if not atr or not np.isfinite(atr):return None
    prior_hi=float(d.High.iloc[i-20:i].max()); prior_lo=float(d.Low.iloc[i-20:i].min()); bullish=bool(x.Close>x.Open); prev_bear=bool(d.Close.iloc[i-1]<d.Open.iloc[i-1]); engulf=bullish and prev_bear and x.Close>=d.Open.iloc[i-1] and x.Open<=d.Close.iloc[i-1]
    breakout=px>prior_hi and vr>=CFG['volume_multiple'] and e20>e50 and r>=52
    pullback=e20>e50 and x.Low<=e20*1.015 and px>e20 and (engulf or (bullish and px>(x.High+x.Low)/2)) and 48<=r<=72 and (px-e20)/atr<=2.0
    breakdown=px<prior_lo and vr>=CFG['volume_multiple'] and e20<e50
    if breakout:kind='Breakout'; side='BUY'; sl=min(float(x.Low)-.25*atr,prior_hi-.45*atr)
    elif pullback:kind='Pullback'; side='BUY'; sl=min(float(x.Low)-.25*atr,e20-.35*atr)
    elif breakdown:kind='Breakdown / EXIT'; side='SELL'; sl=None
    else:return None
    entry=px; risk=entry-sl if side=='BUY' else None
    target=entry+CFG['min_rr']*risk if risk and risk>0 else None
    target2=entry+2.5*risk if risk and risk>0 else None
    return {'setup':kind,'side':side,'entry':entry,'sl':sl,'target':target,'target2':target2,'atr':atr,'rsi':r,'vol_x':vr,'prior_high':prior_hi,'prior_low':prior_lo,'ema20':e20,'ema50':e50,'bar':str(pd.Timestamp(d.index[i]).date())}

def backtest(d):
    trades=[]; last=-999
    for i in range(60,len(d)-CFG['backtest_horizon']-1):
        sig=signal_at(d,i)
        if not sig or sig['side']!='BUY' or i<last+CFG['holding_sessions']:continue
        e=sig['entry']; sl=sig['sl']; tp=sig['target']; risk=e-sl
        if risk<=0:continue
        result=None
        for j in range(i+1,min(i+1+CFG['backtest_horizon'],len(d))):
            # Conservative tie-break: if both touched in same daily candle, assume stop first.
            if d.Low.iloc[j]<=sl:result=-1.0;break
            if d.High.iloc[j]>=tp:result=CFG['min_rr'];break
        if result is None:result=(float(d.Close.iloc[min(i+CFG['backtest_horizon'],len(d)-1)])-e)/risk
        result-=CFG['cost_pct_round_trip']/100*e/risk; trades.append(result);last=i
    if not trades:return {'n':0,'win':None,'avg_r':None,'net_r':0}
    a=np.asarray(trades);return {'n':len(a),'win':round(float((a>0).mean()*100),1),'avg_r':round(float(a.mean()),2),'net_r':round(float(a.sum()),2)}

def monte_carlo(d,entry,sl,tp):
    if os.getenv('DEMO'): pass
    ret=d.Close.pct_change().dropna().tail(180).values
    if len(ret)<30:return {'target':None,'stop':None,'open':None}
    rng=np.random.default_rng(27); n=CFG['monte_carlo_paths']; hits={'target':0,'stop':0,'open':0}
    for _ in range(n):
        price=entry; state='open'
        for rr in rng.choice(ret,size=CFG['holding_sessions'],replace=True):
            nxt=price*(1+rr)
            if nxt<=sl:state='stop';break
            if nxt>=tp:state='target';break
            price=nxt
        hits[state]+=1
    return {k:round(v/n*100,1) for k,v in hits.items()}

def chart_payload(d):
    x=enrich(d).tail(CFG['chart_bars']); out=[]
    for ts,r in x.iterrows():
        out.append({'time':pd.Timestamp(ts).strftime('%Y-%m-%d'),'open':round(float(r.Open),2),'high':round(float(r.High),2),'low':round(float(r.Low),2),'close':round(float(r.Close),2),'volume':int(max(0,float(r.Volume))),'ema20':round(float(r.ema20),2),'ema50':round(float(r.ema50),2),'rsi':round(float(r.rsi),1),'macd':round(float(r.macd),4),'macd_signal':round(float(r.macd_signal),4),'macd_hist':round(float(r.macd_hist),4)})
    return out

def quant_metrics(d,benchmark):
    r=d.Close.pct_change().dropna(); rf=.065/252
    result={'alpha':None,'beta':None,'sharpe':None,'sortino':None,'correlation':None,'annual_volatility':None,'obv':'DATA UNAVAILABLE','parabolic':'—'}
    if benchmark is not None and len(benchmark)>2:
        b=benchmark.Close.pct_change().dropna(); ix=r.index.intersection(b.index); a=r.loc[ix]; bb=b.loc[ix]
        if len(ix)>=40 and bb.var()>0 and a.std()>0:
            beta=float(np.cov(a,bb)[0,1]/bb.var()); alpha=float(((a.mean()-rf)-beta*(bb.mean()-rf))*252*100)
            result.update(alpha=round(alpha,2),beta=round(beta,2),correlation=round(float(a.corr(bb)),2))
    if len(r)>=40 and r.std()>0:
        result['sharpe']=round(float((r.mean()-rf)/r.std()*np.sqrt(252)),2)
        downside=np.sqrt((np.minimum(r-rf,0)**2).mean())
        result['sortino']=round(float((r.mean()-rf)/downside*np.sqrt(252)),2) if downside>0 else None
        result['annual_volatility']=round(float(r.std()*np.sqrt(252)*100),1)
    obv=(np.sign(d.Close.diff().fillna(0))*d.Volume).cumsum()
    result['obv']='↑' if len(obv)>=11 and obv.iloc[-1]>obv.iloc[-11] else '↓'
    y=d.Close.values[-40:-3]
    if len(y)>=30:
        xx=np.linspace(-1,1,len(y)); aa,bb,cc=np.polyfit(xx,y,2); xl=(len(y)+2)/(len(y)-1)*2-1
        projected=aa*xl*xl+bb*xl+cc; dev=(d.Close.iloc[-1]/projected-1)*100 if projected else 0
        result['parabolic']='↑' if aa>0 and dev>2 else '↓' if aa<0 and dev< -2 else '—'
    return result

def build_row(sym,d,fo,regime,benchmark=None):
    x=enrich(d); s=signal_at(x,len(x)-1)
    if s is None:return None
    patterns=pa_evidence(x); pa=price_action(x); pa.update(structure_overlay(x))
    bt=backtest(x); quant=quant_metrics(x,benchmark)
    if s['side']=='BUY':
        risk=s['entry']-s['sl']; rr=(s['target']-s['entry'])/risk if risk>0 else 0
        risk_budget=CFG['capital']*CFG['risk_fraction']; max_cap=CFG['capital']*CFG['max_position_fraction']
        qty=max(0,min(int(risk_budget/risk) if risk>0 else 0,int(max_cap/s['entry']) if s['entry']>0 else 0))
        max_loss=round(qty*risk,2); capital_used=round(qty*s['entry'],2)
        mc=monte_carlo(x,s['entry'],s['sl'],s['target'])
        why=[]
        if rr<CFG['min_rr']:why.append('R:R below minimum')
        if qty<1:why.append('Position size is below one share at the configured ₹500 risk budget / capital cap')
        if bt['n']<CFG['min_backtest_trades']:why.append(f"3-session backtest sample {bt['n']} below {CFG['min_backtest_trades']}")
        if bt['avg_r'] is None or bt['avg_r']<=0:why.append('Backtest expectancy not positive / unavailable')
        if regime in ('BEARISH','SIDEWAYS'):why.append(f'NIFTY regime {regime}: long setup needs stronger confirmation')
        signal='BUY' if not why else 'WAIT'
        risk_obj={'verdict':'PASS' if not why else 'BLOCK','reasons':why,'qty':qty,'rr':round(rr,2),'max_loss':max_loss,'capital_used':capital_used,'risk_budget':round(risk_budget,2)}
    else:
        signal='SELL / EXIT';why=['Bearish breakdown: review existing long positions; not a cash short-entry instruction'];risk_obj={'verdict':'INFO','reasons':why,'qty':0,'rr':None,'max_loss':0,'capital_used':0}
        mc={'target':None,'stop':None,'open':None}
    fo_row=fo.get(sym); oi_pattern='DATA UNAVAILABLE'
    if fo_row and fo_row.get('oich') is not None and fo_row.get('fut_price_change_pct') is not None:
        op=fo_row['oich']; pp=fo_row['fut_price_change_pct']
        oi_pattern='LONG BUILDUP' if pp>0 and op>0 else 'SHORT BUILDUP' if pp<0 and op>0 else 'SHORT COVERING' if pp>0 and op<0 else 'LONG UNWINDING' if pp<0 and op<0 else 'NEUTRAL'
    setup_results=[{'strategy':s['setup'],'side':s['side'],'state':'SETUP','reason':f"Daily close {s['entry']:.2f}; EMA20 {s['ema20']:.2f}; EMA50 {s['ema50']:.2f}; volume {s['vol_x']:.2f}x"}]
    for cat,side,desc in patterns:setup_results.append({'strategy':cat,'side':'BUY' if side=='BULL' else 'SELL','state':'PATTERN_CANDIDATE','reason':desc})
    score=55+(10 if s['setup']=='Breakout' else 7)+(8 if s['vol_x']>=1.5 else 0)+(6 if s['ema20']>s['ema50'] else 0)+(6 if bt['avg_r'] and bt['avg_r']>0 else 0)+(5 if oi_pattern=='LONG BUILDUP' else 0)+(3 if quant.get('alpha') and quant['alpha']>0 else 0)+(3 if quant.get('sortino') and quant['sortino']>0 else 0)-min(20,len(why)*5)
    row={'symbol':sym,'signal':signal,'setup':s['setup'],'entry':round(s['entry'],2),'sl':round(s['sl'],2) if s['sl'] else None,'target':round(s['target'],2) if s['target'] else None,'target1':round(s['target'],2) if s['target'] else None,'target2':round(s.get('target2'),2) if s.get('target2') else None,'rsi':round(s['rsi'],1),'vol_x':round(s['vol_x'],2),'backtest':bt,'replay':mc,'risk':risk_obj,'market_regime':regime,'score':int(max(0,min(100,score))),'confidence_score':int(max(0,min(100,score))),'reason':'; '.join(why) if why else 'Daily EOD setup passed technical, risk and backtest gates; next-session trigger/price must be checked manually.','bar':s['bar'],'holding_sessions':3,'sector':SYMBOL_SECTOR.get(sym,'Others / Unclassified'),'quant':quant,'time_exit':'Close after maximum 3 trading sessions if neither SL nor target hits','oi':fo_row,'oi_pattern':oi_pattern,'strategy_results':setup_results,'pattern_candidates':patterns,'price_action':pa,'chart':None}
    return row

def market_regime(nifty):
    if nifty is None or len(nifty)<60:return 'UNKNOWN'
    x=enrich(nifty).iloc[-1]
    if x.Close>x.ema20>x.ema50:return 'BULLISH'
    if x.Close<x.ema20<x.ema50:return 'BEARISH'
    return 'SIDEWAYS'

def source_links():
    return [{'name':'Yahoo Finance','url':'https://finance.yahoo.com/','role':'Daily OHLCV, indices and chart history'}, {'name':'NSE India','url':'https://www.nseindia.com/','role':'F&O bhavcopy OI, FII/DII and corporate events'}, {'name':'Screener.in','url':'https://www.screener.in/','role':'Quarterly promoter/FII/DII shareholding'}, {'name':'Google News','url':'https://news.google.com/','role':'Company and macro news'}, {'name':'Forex Factory Calendar','url':'https://www.forexfactory.com/calendar','role':'High-impact global economic calendar'}, {'name':'Trendlyne F&O','url':'https://trendlyne.com/futures-options/','role':'External F&O / MWPL cross-check; not treated as a verified feed'}, {'name':'Investing.com Calendar','url':'https://in.investing.com/economic-calendar/','role':'External India/global calendar cross-check'}, {'name':'TradingView Heatmap','url':'https://www.tradingview.com/heatmap/stock/','role':'External sector/market breadth visual cross-check'}]


# =================== PRICE ACTION MODULES PORTED FROM INTELLIGENCE ENGINE v6.1.1 ===================
# Evidence is heuristic/descriptive; never interpreted as institutional order flow or a standalone signal.
def structure_overlay(d):
    x=d.tail(220).reset_index(drop=True)
    if len(x)<25:return {'bos':[],'choch':[],'fvg':[],'order_blocks':[],'structure_state':'INSUFFICIENT DATA','liquidity_sweeps':[]}
    h=x.High.values.astype(float); l=x.Low.values.astype(float); c=x.Close.values.astype(float); o=x.Open.values.astype(float)
    piv=confirmed_pivots(x,3); highs=[p for p in piv if p[1]=='H']; lows=[p for p in piv if p[1]=='L']
    close=float(c[-1]); bos=[]; choch=[]; fvg=[]; obs=[]; state='RANGE / UNCONFIRMED'
    if len(highs)>=2 and len(lows)>=2:
        if highs[-1][2]>highs[-2][2] and lows[-1][2]>lows[-2][2]:state='HH + HL (BULLISH)'
        elif highs[-1][2]<highs[-2][2] and lows[-1][2]<lows[-2][2]:state='LH + LL (BEARISH)'
    if highs and close>highs[-1][2]:
        bos.append({'side':'BULL','level':round(highs[-1][2],2),'index':highs[-1][0],'label':'Bullish BOS'})
        if state.startswith('LH + LL'):choch.append({'side':'BULL','level':round(highs[-1][2],2),'index':highs[-1][0],'label':'Bullish CHOCH'})
    if lows and close<lows[-1][2]:
        bos.append({'side':'BEAR','level':round(lows[-1][2],2),'index':lows[-1][0],'label':'Bearish BOS'})
        if state.startswith('HH + HL'):choch.append({'side':'BEAR','level':round(lows[-1][2],2),'index':lows[-1][0],'label':'Bearish CHOCH'})
    for i in range(2,len(x)):
        if l[i]>h[i-2]:
            lo,hi=float(h[i-2]),float(l[i])
            if not np.any(l[i+1:]<=lo):fvg.append({'side':'BULL','low':round(lo,2),'high':round(hi,2),'index':i-2,'label':'Bullish FVG'})
        if h[i]<l[i-2]:
            lo,hi=float(h[i]),float(l[i-2])
            if not np.any(h[i+1:]>=hi):fvg.append({'side':'BEAR','low':round(lo,2),'high':round(hi,2),'index':i-2,'label':'Bearish FVG'})
    tr=np.maximum(h-l,np.maximum(np.abs(h-np.r_[c[0],c[:-1]]),np.abs(l-np.r_[c[0],c[:-1]])))
    atr=float(np.nanmean(tr[-14:])) if len(tr)>=14 else float(np.nanmean(tr))
    if np.isfinite(atr) and atr>0:
        for i in range(max(12,len(x)-45),len(x)):
            if abs(c[i]-o[i])<1.5*atr:continue
            if c[i]>o[i] and c[i]>np.max(h[max(0,i-10):i]):
                j=next((j for j in range(i-1,max(-1,i-6),-1) if c[j]<o[j]),None)
                if j is not None:obs.append({'side':'BULL','low':round(float(l[j]),2),'high':round(float(h[j]),2),'index':j,'label':'Demand OB candidate'})
            elif c[i]<o[i] and c[i]<np.min(l[max(0,i-10):i]):
                j=next((j for j in range(i-1,max(-1,i-6),-1) if c[j]>o[j]),None)
                if j is not None:obs.append({'side':'BEAR','low':round(float(l[j]),2),'high':round(float(h[j]),2),'index':j,'label':'Supply OB candidate'})
    valid=[]
    for z in obs:
        after=x.iloc[z['index']+1:]
        broken=(after.Close<z['low']).any() if z['side']=='BULL' else (after.Close>z['high']).any()
        if not broken:valid.append(z)
    sweeps=[]
    ph=float(np.max(h[-21:-1])); pl=float(np.min(l[-21:-1]))
    if h[-1]>ph and close<ph:sweeps.append({'side':'BEAR','level':round(ph,2),'label':'Buy-side liquidity sweep'})
    if l[-1]<pl and close>pl:sweeps.append({'side':'BULL','level':round(pl,2),'label':'Sell-side liquidity sweep'})
    return {'bos':bos[-2:],'choch':choch[-2:],'fvg':fvg[-5:],'order_blocks':valid[-5:],
            'structure_state':state,'liquidity_sweeps':sweeps}

def pa_evidence(d):
    out=[]
    if len(d)<60:return out
    o,h,l,c,v=[d[k].astype(float).values for k in ('Open','High','Low','Close','Volume')]
    n=len(c); body=abs(c[-1]-o[-1]); rng=max(h[-1]-l[-1],1e-9); med=float(np.nanmedian(v[-21:-1])); vr=v[-1]/med if med>0 else 0
    lower=min(o[-1],c[-1])-l[-1]; upper=h[-1]-max(o[-1],c[-1])
    if c[-2]<o[-2] and c[-1]>o[-1] and c[-1]>=o[-2] and o[-1]<=c[-2]:out.append(('Candlestick','BULL','Bullish engulfing'))
    if c[-2]>o[-2] and c[-1]<o[-1] and c[-1]<=o[-2] and o[-1]>=c[-2]:out.append(('Candlestick','BEAR','Bearish engulfing'))
    if lower>=max(2*body,.45*rng) and c[-1]>=l[-1]+.6*rng:out.append(('Candlestick','BULL','Hammer / lower-wick rejection'))
    if upper>=max(2*body,.45*rng) and c[-1]<=l[-1]+.4*rng:out.append(('Candlestick','BEAR','Shooting-star / upper-wick rejection'))
    ph=float(np.max(h[-21:-1])); pl=float(np.min(l[-21:-1]))
    if c[-1]>ph:out.append(('Market Structure','BULL',f'BOS above {ph:.2f}; volume {vr:.2f}x'))
    if c[-1]<pl:out.append(('Market Structure','BEAR',f'BOS below {pl:.2f}; volume {vr:.2f}x'))
    boxh=float(np.max(h[-41:-1])); boxl=float(np.min(l[-41:-1]))
    if l[-1]<boxl and c[-1]>boxl and vr>=1.2:out.append(('Wyckoff','BULL',f'Spring/reclaim {boxl:.2f}; volume {vr:.2f}x'))
    if h[-1]>boxh and c[-1]<boxh and vr>=1.2:out.append(('Wyckoff','BEAR',f'Upthrust/rejection {boxh:.2f}; volume {vr:.2f}x'))
    if h[-1]>ph and c[-1]<ph:out.append(('Liquidity Sweep','BEAR',f'Buy-side sweep above {ph:.2f}'))
    if l[-1]<pl and c[-1]>pl:out.append(('Liquidity Sweep','BULL',f'Sell-side sweep below {pl:.2f}'))
    if l[-1]>h[-3]:out.append(('SMC / FVG','BULL',f'Bullish FVG {h[-3]:.2f}-{l[-1]:.2f}'))
    if h[-1]<l[-3]:out.append(('SMC / FVG','BEAR',f'Bearish FVG {h[-1]:.2f}-{l[-3]:.2f}'))
    tr=np.maximum(h-l,np.maximum(np.abs(h-np.r_[c[0],c[:-1]]),np.abs(l-np.r_[c[0],c[:-1]])))
    atr=float(np.nanmean(tr[-14:]))
    if atr>0 and c[-2]>o[-2] and c[-2]-o[-2]>1.5*atr and c[-2]>np.max(h[-12:-2]):
        j=next((j for j in range(n-3,max(-1,n-8),-1) if c[j]<o[j]),None)
        if j is not None:out.append(('SMC / Order Block','BULL',f'Demand OB candidate {l[j]:.2f}-{h[j]:.2f}'))
    if atr>0 and o[-2]>c[-2] and o[-2]-c[-2]>1.5*atr and c[-2]<np.min(l[-12:-2]):
        j=next((j for j in range(n-3,max(-1,n-8),-1) if c[j]>o[j]),None)
        if j is not None:out.append(('SMC / Order Block','BEAR',f'Supply OB candidate {l[j]:.2f}-{h[j]:.2f}'))
    # Double top/bottom and flag/compression candidates, unconfirmed until neckline break.
    look=min(80,n-1);tol=float(np.nanmedian(c[-20:]))*.018;hh=h[-look:];ll=l[-look:]
    tops=sorted([(i,float(hh[i])) for i in range(2,look-2) if hh[i]>=np.max(hh[i-2:i+3])]);bottoms=sorted([(i,float(ll[i])) for i in range(2,look-2) if ll[i]<=np.min(ll[i-2:i+3])])
    for seq,side in ((tops,'BEAR'),(bottoms,'BULL')):
        found=False
        for ai in range(len(seq)):
            for bi in range(ai+1,len(seq)):
                i1,p1=seq[ai];i2,p2=seq[bi]
                if i2-i1>=8 and abs(p1-p2)<=tol:
                    neck=float(np.min(l[-look+i1:-look+i2+1])) if side=='BEAR' else float(np.max(h[-look+i1:-look+i2+1]))
                    name='Double Top' if side=='BEAR' else 'Double Bottom'
                    out.append(('Chart Pattern',side,f'{name} candidate; neckline {neck:.2f}; '+('broken' if (c[-1]<neck if side=='BEAR' else c[-1]>neck) else 'unconfirmed')))
                    found=True;break
            if found:break
    impulse=(c[-11]/c[-26]-1)*100 if n>=30 else 0
    consolidation=(np.max(h[-10:])-np.min(l[-10:]))/max(c[-10],1e-9)*100 if n>=30 else 999
    if impulse>7 and consolidation<max(4,abs(impulse)*.55):out.append(('Chart Pattern','BULL',f'Bull-flag candidate; impulse {impulse:.1f}%, consolidation {consolidation:.1f}%'))
    elif impulse<-7 and consolidation<max(4,abs(impulse)*.55):out.append(('Chart Pattern','BEAR',f'Bear-flag candidate; impulse {impulse:.1f}%, consolidation {consolidation:.1f}%'))
    # Harmonic / Elliott / H&S candidates are shown as evidence, never as trade votes.
    atr0=float(np.nanmean(tr[-14:])) if len(tr)>=14 else float(np.nanmean(tr))
    hm=harmonic_candidate(d,atr0) if atr0>0 else None
    if hm:out.append(('Harmonic',hm['direction'],f"{hm['name']} candidate; ratios {hm['ratios']}"))
    el=elliott_candidate(d,atr0) if atr0>0 else None
    if el:out.append(('Elliott Wave','BULL' if 'expected' in el.lower() or 'bounce' in el.lower() else 'BEAR',el))
    overlays=structure_overlay(d)
    for z in overlays['bos']:out.append(('BOS',z['side'],f"{z['label']} at {z['level']:.2f}"))
    for z in overlays['choch']:out.append(('CHOCH',z['side'],f"{z['label']} at {z['level']:.2f}"))
    for z in overlays['fvg']:out.append(('SMC / FVG',z['side'],f"{z['label']} {z['low']:.2f}-{z['high']:.2f}"))
    for z in overlays['order_blocks']:out.append(('SMC / Order Block',z['side'],f"{z['label']} {z['low']:.2f}-{z['high']:.2f}"))
    for z in overlays['liquidity_sweeps']:out.append(('Liquidity Sweep',z['side'],f"{z['label']} at {z['level']:.2f}"))
    for z in price_action(d).get('chart_patterns',[]):out.append(('Chart Pattern',z['side'],f"{z['name']} {z['status']}; neckline {z['neckline']}"))
    # Ported intelligence modules: harmonic, Elliott, Gann, volume profile, Fib, trendlines,
    # supply/demand, plus measured-move references are added to the per-symbol analysis payload.
    return out

def chart_payload(d):
    x=enrich(d).tail(CFG['chart_bars']); out=[]
    for ts,r in x.iterrows():
        out.append({'time':pd.Timestamp(ts).strftime('%Y-%m-%d'),'open':round(float(r.Open),2),'high':round(float(r.High),2),'low':round(float(r.Low),2),'close':round(float(r.Close),2),'volume':int(max(0,float(r.Volume))),'ema20':round(float(r.ema20),2),'ema50':round(float(r.ema50),2),'rsi':round(float(r.rsi),1),'macd':round(float(r.macd),4),'macd_signal':round(float(r.macd_signal),4),'macd_hist':round(float(r.macd_hist),4)})
    return out
# ================= END PORTED PRICE ACTION MODULES =================


def main():
    start=time.time(); fo,fo_date,fo_error=fetch_fo_bhav(); symbols=list(dict.fromkeys(CURATED+[s for s in fo if s not in CURATED])); universe_source=f'v6.1.1 curated {len(CURATED)} + NSE F&O bhavcopy {len([s for s in fo if s not in CURATED])} additional underlyings'
    nifty=yf_index('^NSEI'); regime=market_regime(nifty); indices={}
    for sym,name in INDIA+WORLD+MACRO+SECTOR_INDICES:
        if sym=='^NSEI' and not nifty.empty:indices[sym]=nifty;continue
        d=yf_index(sym,'6mo')
        if not d.empty:indices[sym]=d
    rows=[]; errors=[]; histories={}
    def fetch_one(sym):return sym,yf_history(sym,'2y')
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures={pool.submit(fetch_one,s):s for s in symbols}
        for f in as_completed(futures):
            sym=futures[f]
            try:
                _,d=f.result()
                if d is None or len(d)<80:errors.append({'symbol':sym,'error':'insufficient Yahoo Finance daily OHLCV history'});continue
                # Do not include an unfinished current NSE candle before 15:45 IST.
                if str(d.index[-1].date())==str(now_ist().date()) and now_ist().time()<dt.time(15,45):d=d.iloc[:-1]
                if len(d)<80:continue
                histories[sym]=d
                row=build_row(sym,d,fo,regime,nifty)
                if row:rows.append(row)
            except Exception as e:errors.append({'symbol':sym,'error':f'{type(e).__name__}: {str(e)[:140]}'})
    rows.sort(key=lambda r:(r['signal']!='BUY',r['signal']=='SELL / EXIT',-r['score']))
    # Attach rich daily charts to the leading 50 candidates, not every universe row.
    for row in rows[:CFG['chart_rows']]:
        d=histories.get(row['symbol'])
        if d is not None:
            try:row['chart']=chart_payload(d)
            except Exception as e:errors.append({'symbol':row['symbol'],'error':'chart: '+type(e).__name__})
    top_syms=[r['symbol'] for r in rows[:15]]
    mwpl=mwpl_pct(symbols)
    volume_gainers=nse_volume_gainers()
    for row in rows:
        row['mwpl_pct']=mwpl.get(row['symbol'])
    # Quarterly ownership data is context only; it is not a daily flow or a trade trigger.
    shareholding={}
    if not os.getenv('DEMO'):
        for sym in top_syms[:10]:
            sh=screener_shareholding(sym)
            if sh:shareholding[sym]=sh
    events=corporate_events(top_syms,fo_date or now_ist().date()) if not os.getenv('DEMO') else {}
    fii=fii_dii(); calendar=economic_events(); macro_news=google_news('India markets Nifty RBI FII crude oil Fed',6)
    stock_news={sym:google_news(sym+' stock India',3) for sym in top_syms[:8]} if not os.getenv('DEMO') else {}
    context=[]
    for sym,name in INDIA+WORLD+MACRO+SECTOR_INDICES:
        d=indices.get(sym)
        if d is None or len(d)<2:context.append({'name':name,'symbol':sym,'change_pct':None,'asof':None});continue
        change=(float(d.Close.iloc[-1])/float(d.Close.iloc[-2])-1)*100
        context.append({'name':name,'symbol':sym,'change_pct':round(change,2),'asof':str(pd.Timestamp(d.index[-1]).date()),'close':round(float(d.Close.iloc[-1]),2)})
    asof=max([str(pd.Timestamp(d.index[-1]).date()) for d in histories.values()] or ['—'])
    updated=now_ist().strftime('%d %b %Y, %H:%M IST')
    payload={'updated':updated,'scan_asof':asof,'scanned':len(histories),'universe_count':len(symbols),'universe_source':universe_source,'data_source':'Yahoo Finance daily OHLCV + NSE F&O bhavcopy / NSE FII-DII / Screener.in / Google News','chart_data_source':'Yahoo Finance daily OHLCV','chart_history_count':sum(bool(r.get('chart')) for r in rows),'price_action_version':'v6.1.1-ported-plus-bos-choch-fvg-ob-v2','market_regime':regime,'demo':bool(os.getenv('DEMO')),'config':CFG,'rows':rows,'errors':errors,'fo_bhavcopy_asof':str(fo_date) if fo_date else None,'fo_bhavcopy_status':'AVAILABLE' if fo else 'DATA UNAVAILABLE','fo_bhavcopy_error':fo_error,'mwpl_pct':mwpl,'nse_volume_gainers':volume_gainers,'fii_dii':fii,'economic_events':calendar,'corporate_events':events,'shareholding':shareholding,'macro_news':macro_news,'stock_news':stock_news,'market_context':context,'sources':source_links(),'runtime_seconds':round(time.time()-start,1)}
    Path('data.json').write_text(json.dumps(payload,indent=2,default=str,ensure_ascii=False),encoding='utf-8')
    # Human-readable EOD snapshot uses same live dashboard + its JSON data file.
    Path('EOD_Swing_Report_LATEST.json').write_text(json.dumps(payload,indent=2,default=str,ensure_ascii=False),encoding='utf-8')
    print(f"EOD scan complete: {len(histories)}/{len(symbols)} daily histories; {len(rows)} setups; NIFTY={regime}; OI={'available' if fo else 'unavailable'}; runtime={payload['runtime_seconds']}s")
    print('Updated data.json and EOD_Swing_Report_LATEST.json; GitHub Pages dashboard reads data.json automatically.')

if __name__=='__main__':main()
