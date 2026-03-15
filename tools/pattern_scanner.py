"""Pattern Scanner — Layers 1-4 of Pattern Match & Options Intelligence."""
import json, logging, math
from datetime import date
import numpy as np, pandas as pd
from scipy.signal import argrelextrema
from scipy.stats import gaussian_kde
from statsmodels.regression.linear_model import OLS
from statsmodels.tools import add_constant
from tools.db import query, query_df, get_conn
from tools.config import (
    BENCHMARK_STOCK, ROTATION_RS_LOOKBACK, ROTATION_MOMENTUM_LOOKBACK,
    ROTATION_HISTORY_DAYS, PATTERN_MIN_BARS, PATTERN_SR_KDE_BANDWIDTH_ATR_MULT,
    PATTERN_SR_TOUCH_TOLERANCE, PATTERN_VOLUME_PROFILE_BINS,
    PATTERN_TRIANGLE_MIN_TOUCHES, PATTERN_TRIANGLE_R2_MIN,
    HURST_MIN_OBSERVATIONS, MR_ZSCORE_THRESHOLD, MR_HALF_LIFE_MIN,
    MR_HALF_LIFE_MAX, MOMENTUM_VR_THRESHOLD, COMPRESSION_HV_PERCENTILE_LOW,
    COMPRESSION_SQUEEZE_MIN_BARS, PATTERN_LAYER_WEIGHTS,
)
logger = logging.getLogger(__name__)
_clamp = lambda v: max(0, min(100, v))

def _load_price_matrix():
    df = query_df("SELECT symbol, date, close FROM price_data WHERE close IS NOT NULL ORDER BY date")
    return pd.DataFrame() if df.empty else df.pivot_table(index="date", columns="symbol", values="close").sort_index().ffill(limit=5).dropna(axis=1, thresh=100)
def _load_ohlcv(sym):
    df = query_df("SELECT date,open,high,low,close,volume FROM price_data WHERE symbol=? AND close IS NOT NULL ORDER BY date", [sym])
    return df.assign(date=pd.to_datetime(df["date"])).set_index("date").sort_index() if not df.empty else df
def _load_sector_map(): return {r["symbol"]: r["sector"] for r in query("SELECT symbol,sector FROM stock_universe WHERE sector IS NOT NULL AND sector!=''")}
def _atr(o, period=14):
    h,l,c = o["high"],o["low"],o["close"]
    return pd.concat([h-l,(h-c.shift(1)).abs(),(l-c.shift(1)).abs()],axis=1).max(axis=1).rolling(period).mean()

def compute_regime_context():
    rows = query("SELECT regime, total_score FROM macro_scores ORDER BY date DESC LIMIT 1")
    regime, regime_score = (rows[0]["regime"], rows[0]["total_score"]) if rows else ("neutral", 0)
    vix_df = query_df("SELECT close FROM price_data WHERE symbol='^VIX' AND close IS NOT NULL ORDER BY date DESC LIMIT 252")
    vix_level = vix_df.iloc[0]["close"] if not vix_df.empty else 20.0
    vix_vals = vix_df["close"].values if not vix_df.empty else np.array([20.0])
    vix_pct = float(np.sum(vix_vals > vix_level) / len(vix_vals) * 100)
    spy = query_df("SELECT close FROM price_data WHERE symbol='SPY' AND close IS NOT NULL ORDER BY date DESC LIMIT 200")
    if len(spy) >= 200:
        p, s50, s200 = spy.iloc[0]["close"], spy.iloc[:50]["close"].mean(), spy["close"].mean()
        tf = "bullish" if p > s50 > s200 else ("bearish" if p < s50 < s200 else "neutral")
    else: tf = "neutral"
    return {"regime": regime, "regime_score": regime_score, "vix_level": vix_level, "vix_percentile": vix_pct, "trend_filter": tf}

def _regime_score(ctx):
    return _clamp({"strong_risk_on":90,"risk_on":70,"neutral":50,"risk_off":30,"strong_risk_off":10}.get(ctx["regime"], 50) + (-10 if ctx["vix_percentile"] < 20 else 0))
def _compute_rs(aligned, hist_days):
    lb = min(ROTATION_RS_LOOKBACK, len(aligned)-1); w = min(hist_days, len(aligned))
    rs_raw = aligned.iloc[:,0].pct_change(lb) - aligned.iloc[:,1].pct_change(lb)
    return (rs_raw - rs_raw.rolling(w, min_periods=60).mean()) / rs_raw.rolling(w, min_periods=60).std().replace(0, np.nan)
def _rotation_result(rs_norm):
    if rs_norm.dropna().empty or len(rs_norm.dropna()) < ROTATION_MOMENTUM_LOOKBACK+1: return None
    r = float(rs_norm.iloc[-1]); m = float(rs_norm.iloc[-1]-rs_norm.iloc[-1-ROTATION_MOMENTUM_LOOKBACK])
    if np.isnan(r) or np.isnan(m): return None
    q = "leading" if r>0 and m>0 else ("weakening" if r>0 else ("lagging" if m<=0 else "improving"))
    return {"rs_ratio":round(r,4),"rs_momentum":round(m,4),"quadrant":q,"rotation_score":round(_clamp(50+25*math.tanh(r)+25*math.tanh(m)),1)}

def compute_sector_rotation(pm, sector_map):
    if pm.empty or BENCHMARK_STOCK not in pm.columns: return {}
    bench = pm[BENCHMARK_STOCK]; sp = {}
    for sec in set(sector_map.values()):
        mb = [s for s, se in sector_map.items() if se == sec and s in pm.columns]
        if len(mb) >= 3: sp[sec] = pm[mb].mean(axis=1)
    results = {}
    for sec, ss in sp.items():
        al = pd.DataFrame({"s": ss, "b": bench}).dropna()
        if len(al) >= ROTATION_HISTORY_DAYS:
            res = _rotation_result(_compute_rs(al, ROTATION_HISTORY_DAYS))
            if res: results[sec] = res
    return results

def compute_stock_rotation(sym, pm, sector_map):
    _d = {"rotation_score":50,"quadrant":"neutral","rs_ratio":0,"rs_momentum":0}
    sec = sector_map.get(sym)
    if not sec or sym not in pm.columns: return _d
    mb = [s for s,se in sector_map.items() if se==sec and s in pm.columns and s!=sym]
    if len(mb)<2: return _d
    al = pd.DataFrame({"s":pm[sym],"b":pm[mb].mean(axis=1)}).dropna()
    return (_rotation_result(_compute_rs(al, ROTATION_HISTORY_DAYS)) or _d) if len(al)>=120 else _d

def _find_swings(series, order=5):
    return series.iloc[argrelextrema(series.values, np.greater_equal, order=order)[0]], series.iloc[argrelextrema(series.values, np.less_equal, order=order)[0]]

def _detect_triangle(sh, sl, direction):
    if len(sh) < PATTERN_TRIANGLE_MIN_TOUCHES or len(sl) < PATTERN_TRIANGLE_MIN_TOUCHES: return None
    fv, tv = (sh.iloc[-5:].values, sl.iloc[-5:].values) if direction == "asc" else (sl.iloc[-5:].values, sh.iloc[-5:].values)
    fi = np.arange(len(fv))
    if len(fi) < 3: return None
    try:
        mf = OLS(fv, add_constant(fi)).fit(); t = tv[:len(fi)]
        if len(t) < 3: return None
        mt = OLS(t, add_constant(np.arange(len(t)))).fit(); st = mt.params[1]/t.mean()
    except Exception: return None
    sf = mf.params[1]/fv.mean(); cf = round(min(1.0,(mf.rsquared+mt.rsquared)/2),2); lv = float(fv.mean())
    if direction == "asc":
        if not (abs(sf)<0.003 and st>0.001 and mt.rsquared>PATTERN_TRIANGLE_R2_MIN): return None
        return {"pattern":"ascending_triangle","direction":"bullish","confidence":cf,"price_target":round(lv+(lv-t[-1]),2),"invalidation":round(float(t[-1])*0.98,2),"bars_since":0}
    else:
        if not (abs(sf)<0.003 and st<-0.001 and mt.rsquared>PATTERN_TRIANGLE_R2_MIN): return None
        return {"pattern":"descending_triangle","direction":"bearish","confidence":cf,"price_target":round(lv-(t[-1]-lv),2),"invalidation":round(float(t[-1])*1.02,2),"bars_since":0}

def _detect_flag(c, v, atr_val, d):
    if len(c) < 30 or not atr_val or atr_val <= 0: return None
    pre, fl = c.iloc[-30:-10], c.iloc[-10:]
    if len(pre) == 0 or len(fl) == 0: return None
    mp = (pre.iloc[-1] - pre.iloc[0]) / pre.iloc[0]; fr = (fl.max() - fl.min()) / atr_val
    if (d == 1 and mp <= 0.05) or (d == -1 and mp >= -0.05) or fr >= 3.0: return None
    vs = np.polyfit(range(len(v.iloc[-10:])), v.iloc[-10:].values, 1)[0] if len(v) > 12 else 0
    cf = round(min(1.0, 0.5 + (0.25 if vs < 0 else 0) + (0.25 if fr < 1.5 else 0)), 2)
    ms = abs(pre.iloc[-1] - pre.iloc[0]); cp = c.iloc[-1]
    nm = ("bull_flag","bullish") if d == 1 else ("bear_flag","bearish")
    tgt = cp + ms * d; inv = float(fl.min())*0.98 if d == 1 else float(fl.max())*1.02
    return {"pattern":nm[0],"direction":nm[1],"confidence":cf,"price_target":round(tgt,2),"invalidation":round(inv,2),"bars_since":0}

def detect_chart_patterns(ohlcv):
    if len(ohlcv) < PATTERN_MIN_BARS * 3: return []
    pat = []; cl, hi, lo, vol = ohlcv["close"], ohlcv["high"], ohlcv["low"], ohlcv["volume"]
    cp = cl.iloc[-1]; av = _atr(ohlcv).iloc[-1] if len(ohlcv) >= 14 else cl.std()*0.1
    lb = min(120, len(ohlcv)); h,l,c,v = hi.iloc[-lb:],lo.iloc[-lb:],cl.iloc[-lb:],vol.iloc[-lb:]
    sh, _ = _find_swings(h, 5); _, sll = _find_swings(l, 5)
    if len(sh) >= 2:
        t1, t2 = sh.iloc[-2], sh.iloc[-1]
        if abs(t1-t2) < 0.02*t1:
            nl = sll.iloc[-1] if not sll.empty else l.min(); i1, i2 = sh.index[-2], sh.index[-1]
            vc = v.loc[i2] < v.loc[i1] if i1 in v.index and i2 in v.index else False
            cf = 0.6 + (0.2 if vc else 0) + (0.2 if cp < nl else 0)
            pat.append({"pattern":"double_top","direction":"bearish","confidence":round(min(1.0,cf),2),
                "price_target":round(cp-(t1-nl),2),"invalidation":round(max(t1,t2)*1.01,2),"bars_since":int(len(c)-list(c.index).index(i2)) if i2 in c.index else 0})
    if len(sll) >= 2:
        b1, b2 = sll.iloc[-2], sll.iloc[-1]
        if abs(b1-b2) < 0.02*b1:
            nl = sh.iloc[-1] if not sh.empty else h.max(); cf = 0.6 + (0.2 if cp > nl else 0)
            pat.append({"pattern":"double_bottom","direction":"bullish","confidence":round(min(1.0,cf),2),
                "price_target":round(cp+(nl-b1),2),"invalidation":round(min(b1,b2)*0.99,2),"bars_since":0})
    for args in [(sh, sll, "asc"), (sll, sh, "desc")]:
        tri = _detect_triangle(*args)
        if tri: pat.append(tri)
    for d in [1, -1]:
        fl = _detect_flag(c, v, av, d)
        if fl: pat.append(fl)
    return pat

def compute_support_resistance(ohlcv, n_levels=5):
    if len(ohlcv) < 50: return []
    cp, av = ohlcv["close"].iloc[-1], _atr(ohlcv).iloc[-1]
    if not av or av <= 0 or np.isnan(av): return []
    prices = pd.concat([ohlcv["high"], ohlcv["low"]]).dropna().values
    if len(prices) < 20: return []
    try: kde = gaussian_kde(prices, bw_method=PATTERN_SR_KDE_BANDWIDTH_ATR_MULT*av/prices.std())
    except Exception: return []
    pr = np.linspace(prices.min(), prices.max(), 500); pi = argrelextrema(kde(pr), np.greater, order=10)[0]
    if len(pi) == 0: return []
    tol = PATTERN_SR_TOUCH_TOLERANCE * cp; levels = []
    for idx in pi:
        lv = float(pr[idx]); tc = int(np.sum(np.abs(prices-lv)<tol))
        bp = np.where(np.abs(prices[:len(ohlcv)]-lv)<tol)[0]
        rec = sum(math.exp(-0.023*(len(ohlcv)-p)) for p in bp) if len(bp)>0 else 0
        levels.append({"level":round(lv,2),"type":"support" if lv<cp else "resistance","strength":round(min(100,tc*8+rec*15),1),"touch_count":tc})
    levels.sort(key=lambda x: x["strength"], reverse=True); return levels[:n_levels]

def compute_volume_profile(ohlcv):
    _d = {"poc":0,"value_area_high":0,"value_area_low":0,"current_vs_va":"unknown","volume_profile_score":50}
    if len(ohlcv) < 50: return _d
    lb = min(PATTERN_VOLUME_PROFILE_BINS*5, len(ohlcv)); data = ohlcv.iloc[-lb:]; cp = data["close"].iloc[-1]
    tp = (data["high"]+data["low"]+data["close"])/3; pn, px = tp.min(), tp.max()
    if px <= pn: return {"poc":float(cp),"value_area_high":float(cp),"value_area_low":float(cp),"current_vs_va":"at_poc","volume_profile_score":50}
    nb = PATTERN_VOLUME_PROFILE_BINS; bins = np.linspace(pn, px, nb+1); vpb = np.zeros(nb)
    for i in range(len(data)): vpb[min(int((tp.iloc[i]-pn)/(px-pn)*nb), nb-1)] += max(data["volume"].iloc[i], 1)
    pi = int(np.argmax(vpb)); poc = float((bins[pi]+bins[pi+1])/2)
    tv = 0.70*vpb.sum(); vl, vh, acc = pi, pi, vpb[pi]
    while acc < tv and (vl > 0 or vh < nb-1):
        lv = vpb[vl-1] if vl > 0 else 0; hv = vpb[vh+1] if vh < nb-1 else 0
        if lv >= hv and vl > 0: vl -= 1; acc += lv
        elif vh < nb-1: vh += 1; acc += hv
        else: vl -= 1; acc += lv
    va_l, va_h = float(bins[vl]), float(bins[min(vh+1, nb)])
    if cp > va_h: sc = 80 if data["volume"].iloc[-5:].mean() > data["volume"].mean()*1.2 else 60; vs = "above_va"
    elif cp < va_l: sc, vs = 35, "below_va"
    else: sc, vs = 50, "inside_va"
    return {"poc":round(poc,2),"value_area_high":round(va_h,2),"value_area_low":round(va_l,2),"current_vs_va":vs,"volume_profile_score":float(sc)}

def _hurst_exponent(series, max_lag=40):
    raw = series.dropna().values
    if len(raw) < HURST_MIN_OBSERVATIONS: return 0.5
    vals = np.diff(np.log(raw[raw > 0])); rsv = []
    for lag in range(2, min(max_lag, len(vals)//4)):
        n = len(vals)//lag
        if n < 1: continue
        rl = []
        for i in range(n):
            ch = vals[i*lag:(i+1)*lag]
            if len(ch)<2: continue
            dev = np.cumsum(ch-ch.mean()); S = ch.std(ddof=1)
            if S > 0: rl.append((dev.max()-dev.min())/S)
        if rl: rsv.append((np.log(lag), np.log(np.mean(rl))))
    if len(rsv) < 3: return 0.5
    try: return max(0.0, min(1.0, np.polyfit(*zip(*rsv), 1)[0]))
    except Exception: return 0.5

def detect_mean_reversion_setups(ohlcv):
    cl = ohlcv["close"]
    if len(cl) < 100: return {"hurst":0.5,"mr_score":0,"zscore_20d":0,"zscore_50d":0,"half_life":None}
    lp = np.log(cl); s20 = cl.rolling(20).std().iloc[-1]; s50 = cl.rolling(50).std().iloc[-1] if len(cl)>=50 else 0
    z20 = float((cl.iloc[-1]-cl.rolling(20).mean().iloc[-1])/s20) if s20>0 else 0
    z50 = float((cl.iloc[-1]-cl.rolling(50).mean().iloc[-1])/s50) if s50>0 else 0
    hu = _hurst_exponent(cl); hl = None
    try:
        m = OLS(np.diff(lp.values), add_constant(lp.values[:-1])).fit()
        if m.params[1]<0 and m.pvalues[1]<0.05: hl = -math.log(2)/math.log(1+m.params[1])
    except Exception: pass
    ms = (50*(1-hu)/0.5 if hu<0.5 else 0)+(25 if max(abs(z20),abs(z50))>=MR_ZSCORE_THRESHOLD else 0)+(25 if hl and MR_HALF_LIFE_MIN<=hl<=MR_HALF_LIFE_MAX else 0)
    return {"hurst":round(hu,4),"zscore_20d":round(z20,2),"zscore_50d":round(z50,2),"half_life":round(hl,1) if hl else None,"mr_score":round(_clamp(ms),1)}

def detect_momentum_persistence(ohlcv):
    cl = ohlcv["close"]
    if len(cl) < 60: return {"hurst":0.5,"momentum_score":0,"adx":0}
    rets = cl.pct_change().dropna()
    vr5 = (rets.rolling(5).sum().dropna().var()/(5*rets.var())) if len(rets)>=10 and rets.var()>0 else 1.0
    try:
        from ta.trend import ADXIndicator; adx = float(ADXIndicator(ohlcv["high"],ohlcv["low"],cl,window=14).adx().iloc[-1])
    except Exception: adx = 0
    hu = _hurst_exponent(cl)
    ms = (50*min(1.0,(hu-0.5)/0.5) if hu>0.5 else 0)+(25 if vr5>MOMENTUM_VR_THRESHOLD else 0)+(25 if adx>25 else 0)
    return {"hurst":round(hu,4),"adx":round(adx,1),"momentum_score":round(_clamp(ms),1)}

def detect_volatility_compression(ohlcv):
    cl = ohlcv["close"]
    _def = {"hv_20d":0,"hv_60d":0,"hv_ratio":1,"hv_percentile":50,"squeeze_active":False,"squeeze_duration":0,"compression_score":0}
    if len(cl) < 60: return _def
    lr = np.log(cl/cl.shift(1)).dropna(); sq252 = np.sqrt(252)
    hv20 = float(lr.iloc[-20:].std()*sq252) if len(lr)>=20 else 0; hv60 = float(lr.iloc[-60:].std()*sq252) if len(lr)>=60 else 0
    hvr = hv20/hv60 if hv60>0 else 1.0; rhv = (lr.rolling(20).std()*sq252).dropna()
    hvp = float(np.sum(rhv.values<hv20)/len(rhv)*100) if len(rhv)>20 else 50.0
    s20, st20, av = cl.rolling(20).mean(), cl.rolling(20).std(), _atr(ohlcv)
    sq = ((s20+2*st20)<(s20+1.5*av)) & ((s20-2*st20)>(s20-1.5*av)); sa = bool(sq.iloc[-1]) if not sq.empty else False
    sd = 0
    if sa:
        for i in range(len(sq)-1,-1,-1):
            if sq.iloc[i]: sd += 1
            else: break
    cs = (40*(1-hvp/100) if hvp<COMPRESSION_HV_PERCENTILE_LOW else 0) + (30 if sa and sd>=COMPRESSION_SQUEEZE_MIN_BARS else 0) + (30 if hvr<0.7 else 0)
    return {"hv_20d":round(hv20,4),"hv_60d":round(hv60,4),"hv_ratio":round(hvr,3),"hv_percentile":round(hvp,1),"squeeze_active":sa,"squeeze_duration":sd,"compression_score":round(_clamp(cs),1)}

def detect_wyckoff_phase(ohlcv):
    cl, vol = ohlcv["close"], ohlcv["volume"]
    if len(cl) < 60: return {"phase":"unknown","confidence":0,"duration_days":0,"progress_pct":0,"cycle_score":50}
    lb = min(252, len(cl)); lp = np.log(cl.iloc[-lb:].values); at = np.polyfit(np.arange(len(lp)), lp, 1)[0] * 252
    s50 = cl.rolling(50).mean().iloc[-1] if len(cl) >= 50 else cl.mean()
    s200 = cl.rolling(200).mean().iloc[-1] if len(cl) >= 200 else cl.rolling(100).mean().iloc[-1]; cur = cl.iloc[-1]
    obv = (vol * np.where(cl.diff() > 0, 1, -1)).cumsum()
    os_ = np.polyfit(range(min(30,len(obv))), obv.iloc[-30:].values, 1)[0] if len(obv) >= 5 else 0
    ats = _atr(ohlcv); asl = np.polyfit(range(30), ats.iloc[-30:].values, 1)[0] if len(ats.dropna()) >= 30 else 0
    rc = cl.iloc[-60:]; dd = ((rc-rc.cummax())/rc.cummax()).min()
    sc = {"accumulation":0,"markup":0,"distribution":0,"markdown":0}
    if dd < -0.15: sc["accumulation"] += 2
    if abs(at) < 0.15: sc["accumulation"] += 1; sc["distribution"] += 1
    if os_ > 0: sc["accumulation"] += 2; sc["markup"] += 1
    elif os_ < 0: sc["distribution"] += 2; sc["markdown"] += 1
    if asl < 0: sc["accumulation"] += 1
    elif asl > 0: sc["distribution"] += 1
    if cur > s50 > s200: sc["markup"] += 3
    elif cur < s50 < s200: sc["markdown"] += 3
    if at > 0.15: sc["markup"] += 2
    elif at < -0.15: sc["markdown"] += 2
    rl = ((rc-rc.cummin())/rc.cummin().replace(0,np.nan)).max()
    if rl > 0.20: sc["distribution"] += 2
    ph = max(sc, key=sc.get); cf = sc[ph]/max(sum(sc.values()), 1)
    return {"phase":ph,"confidence":round(cf,2),"duration_days":30,"progress_pct":50,
        "cycle_score":round(50+({"accumulation":80,"markup":70,"distribution":30,"markdown":15}.get(ph,50)-50)*cf,1)}

def compute_earnings_cycle(sym):
    td = date.today().isoformat()
    nr = query("SELECT date FROM earnings_calendar WHERE symbol=? AND date>=? ORDER BY date ASC LIMIT 1",[sym,td])
    lr = query("SELECT date FROM earnings_calendar WHERE symbol=? AND date<? ORDER BY date DESC LIMIT 1",[sym,td])
    return {"days_to_next":(pd.Timestamp(nr[0]["date"])-pd.Timestamp(td)).days if nr else None,
        "days_since_last":(pd.Timestamp(td)-pd.Timestamp(lr[0]["date"])).days if lr else None,"last_surprise_pct":None,"earnings_drift_score":50.0}

def detect_volatility_cycle(ohlcv):
    cl = ohlcv["close"]
    if len(cl) < 60: return {"vol_regime":"normal","regime_duration":0,"vol_cycle_score":50}
    lr = np.log(cl/cl.shift(1)).dropna(); sq252 = np.sqrt(252)
    h20 = float(lr.iloc[-20:].std()*sq252); h252 = float(lr.std()*sq252) if len(lr) >= 100 else h20
    r = h20/h252 if h252 > 0 else 1.0; vr, vs = ("low",70) if r < 0.75 else (("high",30) if r > 1.25 else ("normal",50))
    rhv = (lr.rolling(20).std()*sq252).dropna(); dur = 0
    for i in range(len(rhv)-1, -1, -1):
        rv = rhv.iloc[i]/h252 if h252 > 0 else 1
        if (vr=="low" and rv<0.75) or (vr=="high" and rv>1.25) or (vr=="normal" and 0.75<=rv<=1.25): dur += 1
        else: break
    return {"vol_regime":vr,"regime_duration":dur,"vol_cycle_score":vs}

def compute_pattern_composite(rs, rot, ps, sr, vp, mr, mom, comp, wyck, earn, vc, rctx):
    sq = max((l["strength"] for l in sr), default=0); ts = ps*0.50+min(100,sq)*0.20+vp.get("volume_profile_score",50)*0.30
    tf = rctx.get("trend_filter"); m_mr,m_mo,m_co = mr["mr_score"],mom["momentum_score"],comp["compression_score"]
    ss = m_mr*0.25+m_mo*0.50+m_co*0.25 if tf=="bullish" else (m_mr*0.50+m_mo*0.20+m_co*0.30 if tf=="bearish" else m_mr*0.33+m_mo*0.34+m_co*0.33)
    cy = wyck.get("cycle_score",50)*0.50+earn.get("earnings_drift_score",50)*0.25+vc.get("vol_cycle_score",50)*0.25
    ls = {"L1_regime":round(rs,1),"L2_rotation":round(rot,1),"L3_technical":round(ts,1),"L4_statistical":round(ss,1),"L4.5_cycles":round(cy,1)}
    w = PATTERN_LAYER_WEIGHTS
    return round(_clamp(w["regime"]*rs+w["rotation"]*rot+w["technical"]*ts+w["statistical"]*ss+w["cycles"]*cy),1), ls

def scan_all(symbols=None):
    print("  Loading price data...")
    pm = _load_price_matrix()
    if pm.empty: print("  No price data available"); return []
    sm = _load_sector_map(); rctx = compute_regime_context(); rsc = _regime_score(rctx)
    print(f"  Regime: {rctx['regime']} (score={rctx['regime_score']:.0f}), VIX={rctx['vix_level']:.1f} (pct={rctx['vix_percentile']:.0f}), trend={rctx['trend_filter']}")
    sr = compute_sector_rotation(pm, sm); td = date.today().isoformat()
    if sr:
        with get_conn() as conn:
            for s, d in sr.items():
                conn.execute("INSERT OR REPLACE INTO sector_rotation (sector,date,rs_ratio,rs_momentum,quadrant,rotation_score) VALUES (?,?,?,?,?,?)",
                    (s, td, d["rs_ratio"], d["rs_momentum"], d["quadrant"], d["rotation_score"]))
        print(f"  Sector rotation: {len(sr)} sectors | Leading: {[s for s,d in sr.items() if d['quadrant']=='leading'][:3]} | Lagging: {[s for s,d in sr.items() if d['quadrant']=='lagging'][:3]}")
    if symbols is None: symbols = list(pm.columns)
    symbols = [s for s in symbols if s in pm.columns]
    print(f"  Scanning {len(symbols)} symbols...")
    results, sqz, pc = [], 0, 0
    for i, sym in enumerate(symbols):
        if (i+1) % 100 == 0: print(f"    {i+1}/{len(symbols)} scanned...")
        try:
            oh = _load_ohlcv(sym)
            if oh.empty or len(oh) < PATTERN_MIN_BARS*2: continue
            srot = compute_stock_rotation(sym, pm, sm); rots = srot["rotation_score"]
            pats = detect_chart_patterns(oh)
            best = max(pats, key=lambda p: p["confidence"]) if pats else None
            pscore = min(100, 50+best["confidence"]*50) if best and best["direction"]=="bullish" else (max(0, 50-best["confidence"]*50) if best else 30)
            srl = compute_support_resistance(oh); vpr = compute_volume_profile(oh)
            if pats: pc += 1
            av = _atr(oh).iloc[-1] if len(oh) >= 14 else 0; sp = "between"
            if srl and av and av > 0:
                for lv in srl:
                    if abs(oh["close"].iloc[-1]-lv["level"]) < av*1.5: sp = f"near_{lv['type']}"; break
            mr = detect_mean_reversion_setups(oh); mo = detect_momentum_persistence(oh); co = detect_volatility_compression(oh)
            if co["squeeze_active"]: sqz += 1
            wy = detect_wyckoff_phase(oh); ea = compute_earnings_cycle(sym); vc = detect_volatility_cycle(oh)
            comp, ls = compute_pattern_composite(rsc, rots, pscore, srl, vpr, mr, mo, co, wy, ea, vc, rctx)
            results.append({"symbol":sym,"date":td,"regime":rctx["regime"],"regime_score":rctx["regime_score"],
                "vix_percentile":rctx["vix_percentile"],"sector_quadrant":srot["quadrant"],"rotation_score":rots,
                "rs_ratio":srot["rs_ratio"],"rs_momentum":srot["rs_momentum"],"patterns_detected":json.dumps(pats) if pats else None,
                "pattern_score":pscore,"sr_proximity":sp,"volume_profile_score":vpr["volume_profile_score"],
                "hurst_exponent":mr["hurst"],"mr_score":mr["mr_score"],"momentum_score":mo["momentum_score"],
                "compression_score":co["compression_score"],"squeeze_active":1 if co["squeeze_active"] else 0,
                "wyckoff_phase":wy["phase"],"wyckoff_confidence":wy["confidence"],"earnings_days_to_next":ea["days_to_next"],
                "vol_regime":vc["vol_regime"],"pattern_scan_score":comp,"layer_scores":json.dumps(ls)})
        except Exception as e: logger.warning(f"Pattern scan failed for {sym}: {e}")
    print(f"  Scan complete: {len(results)} scored, {pc} patterns, {sqz} squeeze"); return results
