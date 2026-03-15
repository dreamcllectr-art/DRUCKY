"""Alternative Data Ingestion — physical-world signals that lead price."""
import sys, json, math, time
from datetime import date, datetime
from pathlib import Path
_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path: sys.path.insert(0, _project_root)
import requests
from tools.config import (
    NASA_FIRMS_API_KEY, USDA_API_KEY, ENSO_MODERATE_THRESHOLD, ENSO_STRONG_THRESHOLD,
    ENSO_MODERATE_STRENGTH, ENSO_STRONG_STRENGTH, NDVI_ZSCORE_THRESHOLD,
    NDVI_STRESS_BASE_STRENGTH, NDVI_QUERY_DELAY,
)
from tools.db import init_db, get_conn, query

ST = {
    "energy":["OXY","COP","XOM","CVX","DVN","FANG","EOG","PXD","MPC","VLO","PSX"],
    "insurance":["ALL","TRV","CB","PGR","MET","AIG"],
    "agriculture":["ADM","BG","DE","MOS","CF","NTR","CTVA","FMC"],
    "shipping":["ZIM","SBLK","GOGL","DAC","MATX"],
    "materials":["BHP","RIO","FCX","VALE","NEM","SCCO","CLF","X"],
    "industrials":["CAT","CMI","GE","HON","ETN","ROK"],
    "utilities_power":["VST","CEG","NRG","NEE","SO","DUK"],
    "retail":["WMT","AMZN","COST","TGT","HD","LOW"],
    "tech_consumer":["AAPL","GOOGL","META","MSFT","NFLX","CRM"],
    "fertilizer":["CF","MOS","NTR","CTVA","FMC"],
    "grain_processors":["ADM","BG"],"farm_equipment":["DE","AGCO","CNHI"],
}
EMAP = {
    "hurricane":(["energy","insurance"],"mixed",80),"tropical":(["energy","insurance"],"mixed",70),
    "tornado":(["insurance"],"bearish",60),"drought":(["agriculture"],"bullish",65),
    "freeze":(["energy","agriculture"],"bullish",60),"winter":(["energy"],"bullish",55),
    "flood":(["agriculture","insurance"],"mixed",60),"fire":(["insurance","utilities_power"],"bearish",65),
    "heat":(["energy","utilities_power"],"bullish",55),
}
ZONES = [
    (29.75,-95.35,150,"Gulf Coast Refining",["energy"]),(30.0,-90.0,100,"Louisiana Petrochemical",["energy"]),
    (36.0,-119.0,200,"California Central Valley",["agriculture"]),
    (34.0,-118.5,100,"Southern California",["insurance","utilities_power"]),
    (37.5,-122.0,80,"San Francisco Bay",["insurance","tech_consumer"]),
    (41.0,-90.0,200,"Midwest Corn Belt",["agriculture"]),(32.0,-100.0,200,"Texas Permian Basin",["energy"]),
]
AG = [
    (41.0,-89.5,"Corn Belt","corn",{"sb":["fertilizer"],"se":["farm_equipment"]}),
    (38.0,-99.0,"Great Plains","wheat",{"sb":["fertilizer"],"se":["farm_equipment"]}),
    (36.0,-119.0,"Central Valley","mixed",{"sb":["fertilizer"],"se":["agriculture"]}),
    (33.0,-90.5,"Delta","soybeans",{"sb":["fertilizer","grain_processors"],"se":["farm_equipment"]}),
    (47.0,-118.0,"PNW","wheat",{"sb":["fertilizer"],"se":["farm_equipment"]}),
]

def _tf(secs):
    t = []
    for s in secs: t.extend(ST.get(s,[]))
    return t

def _sig(src,ind,val,d,st,secs,tks,narr,z=None):
    s = {"source":src,"indicator":ind,"value":val,"signal_direction":d,"signal_strength":st,
         "affected_sectors":json.dumps(secs),"affected_tickers":json.dumps(tks),"narrative":narr}
    if z is not None: s["value_zscore"] = z
    return s

def fetch_noaa_weather():
    signals = []
    try:
        resp = requests.get("https://api.weather.gov/alerts/active",
            headers={"User-Agent":"DruckenmillerAlpha/1.0"},
            params={"status":"actual","severity":"Extreme,Severe"}, timeout=15)
        resp.raise_for_status()
        ec = {}
        for a in resp.json().get("features",[]):
            p = a.get("properties",{})
            ev,sev = p.get("event","").lower(), p.get("severity","")
            if sev not in ("Extreme","Severe"): continue
            k = ev.split()[0] if ev else "unknown"
            if k not in ec: ec[k] = {"c":0,"a":set()}
            ec[k]["c"] += 1
            if len(ec[k]["a"])<3: ec[k]["a"].add(p.get("areaDesc","")[:50])
        for ek,d in ec.items():
            m = next(((s,dr,bs) for p,(s,dr,bs) in EMAP.items() if p in ek), None)
            if not m: continue
            s,dr,bs = m
            signals.append(_sig("noaa_weather",f"weather_{ek}",d["c"],dr,
                min(100,bs*min(1.5,1.0+d["c"]/20)),s,_tf(s),
                f"{d['c']} {ek} alerts ({', '.join(list(d['a'])[:3])}). Impacts {', '.join(s)}."))
        print(f"    NOAA: {len(ec)} event types -> {len(signals)} signals")
    except Exception as e: print(f"    NOAA: Failed — {e}")
    return signals

def fetch_nasa_firms():
    signals = []
    if not NASA_FIRMS_API_KEY: print("    FIRMS: Skipped (no key)"); return signals
    try:
        resp = requests.get(f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{NASA_FIRMS_API_KEY}/VIIRS_SNPP_NRT/world/2", timeout=30)
        if resp.status_code!=200: print(f"    FIRMS: {resp.status_code}"); return signals
        lines = resp.text.strip().split("\n")
        if len(lines)<2: return signals
        for zlat,zlon,rad,zn,zs in ZONES:
            fc = sum(1 for line in lines[1:] for parts in [line.split(",")]
                if len(parts)>=3 and _near(parts,zlat,zlon,rad))
            if fc>=5:
                signals.append(_sig("nasa_firms",f"fires_{zn.lower().replace(' ','_')}",fc,
                    "bearish" if "insurance" in zs else "bullish",min(100,40+fc*2),zs,_tf(zs),
                    f"{fc} fire hotspots near {zn} (48h). Impact on {', '.join(zs)}."))
        print(f"    FIRMS: {len(lines)-1} hotspots -> {len(signals)} alerts")
    except Exception as e: print(f"    FIRMS: Failed — {e}")
    return signals

def _near(parts,zlat,zlon,rad):
    try:
        lat,lon = float(parts[0]),float(parts[1])
        dx,dy = abs(lat-zlat)*111, abs(lon-zlon)*111*math.cos(math.radians(zlat))
        return math.sqrt(dx**2+dy**2)<=rad
    except ValueError: return False

def fetch_google_trends():
    signals = []
    try:
        from pytrends.request import TrendReq
    except ImportError: print("    Trends: Skipped (pytrends)"); return signals
    TQ = [(["layoffs","unemployment"],["industrials"],"bearish","labor_distress"),
        (["recession"],["retail","industrials"],"bearish","recession_fear"),
        (["buy iPhone","buy laptop"],["tech_consumer"],"bullish","consumer_tech_demand"),
        (["buy house","mortgage rates"],[],"mixed","housing_demand")]
    try:
        pt = TrendReq(hl="en-US",tz=300,timeout=(10,25))
        for kws,secs,dr,ind in TQ:
            try:
                pt.build_payload(kws, timeframe="now 7-d", geo="US")
                interest = pt.interest_over_time()
                if interest.empty: continue
                recent,earlier = interest.iloc[-2:].mean(), interest.iloc[:-2].mean()
                for kw in kws:
                    if kw not in recent or kw not in earlier or earlier[kw]<=0: continue
                    chg = (recent[kw]-earlier[kw])/earlier[kw]*100
                    if abs(chg)<20: continue
                    d = dr if chg>0 else ("bullish" if dr=="bearish" else "bearish")
                    signals.append(_sig("google_trends",f"trends_{ind}_{kw.replace(' ','_')}",
                        recent[kw],d,min(100,30+abs(chg)*0.5),secs,_tf(secs),
                        f"Trends '{kw}': {chg:+.0f}% vs prior week.",z=chg/20))
                time.sleep(2)
            except Exception as e: print(f"    Trends: '{kws}' failed — {e}"); time.sleep(3)
        print(f"    Trends: {len(signals)} signals")
    except Exception as e: print(f"    Trends: Failed — {e}")
    return signals

def fetch_usda_data():
    signals = []
    if not USDA_API_KEY: print("    USDA: Skipped (no key)"); return signals
    for commodity,tickers,avg in [("CORN",["ADM","BG","DE","CF"],60),("SOYBEANS",["ADM","BG","MOS","DE"],58),("WHEAT",["ADM","BG"],48)]:
        try:
            resp = requests.get("https://quickstats.nass.usda.gov/api/api_GET/",
                params={"key":USDA_API_KEY,"commodity_desc":commodity,"statisticcat_desc":"CONDITION",
                    "unit_desc":"PCT GOOD","year":datetime.now().year,"freq_desc":"WEEKLY","format":"JSON"}, timeout=15)
            if resp.status_code!=200: continue
            data = resp.json().get("data",[])
            if not data: continue
            gp = float(max(data,key=lambda x:x.get("week_ending","")).get("Value",0))
            dev = gp-avg
            if abs(dev)<5: continue
            signals.append(_sig("usda_crop",f"crop_{commodity.lower()}",gp,
                "bullish" if dev<0 else "bearish",min(100,30+abs(dev)*2),["agriculture"],tickers,
                f"{commodity}: {gp:.0f}% good (avg:{avg}%, dev:{dev:+.0f}pp).",z=dev/10))
        except Exception as e: print(f"    USDA {commodity}: Failed — {e}")
    print(f"    USDA: {len(signals)} signals"); return signals

def fetch_china_activity_proxy():
    signals = []
    try:
        import yfinance as yf
        data = yf.download(["HG=F","GC=F"],period="3mo",interval="1d",progress=False)
        if data.empty: print("    China: No data"); return signals
        cl, moms = data["Close"], {}
        for tk,nm in [("HG=F","Copper"),("GC=F","Gold")]:
            if tk not in cl.columns: continue
            s = cl[tk].dropna()
            if len(s)<30: continue
            r7,p30 = s.iloc[-7:].mean(), s.iloc[-30:-7].mean()
            if p30>0: moms[nm] = (r7-p30)/p30*100
        if not moms: return signals
        cu,au = moms.get("Copper",0), moms.get("Gold",0)
        sc = cu-au*0.5
        if abs(sc)<2: return signals
        d = "bullish" if sc>0 else "bearish"
        signals.append(_sig("china_activity","china_composite",round(sc,2),d,
            min(100,30+abs(sc)*5),["materials","industrials"],ST["materials"]+ST["industrials"],
            f"China proxy: {sc:+.1f} (Cu:{cu:+.1f}%,Au:{au:+.1f}%). {'Accel' if sc>0 else 'Decel'} demand.",z=sc/5))
        print(f"    China: {sc:+.1f} ({d})")
    except Exception as e: print(f"    China: Failed — {e}")
    return signals

def fetch_baltic_dry():
    signals = []
    try:
        import yfinance as yf
        data = yf.download("SBLK",period="3mo",interval="1d",progress=False)
        if data.empty or len(data)<30: print("    Baltic: Insufficient data"); return signals
        cl = data["Close"]
        if hasattr(cl,'columns'): cl = cl.iloc[:,0]
        r7,ma30,ma90 = cl.iloc[-7:].mean(), cl.iloc[-30:].mean(), cl.mean()
        m30 = (r7-ma30)/ma30*100 if ma30>0 else 0
        m90 = (r7-ma90)/ma90*100 if ma90>0 else 0
        if abs(m30)<3: return signals
        d = "bullish" if m30>0 else "bearish"
        signals.append(_sig("baltic_dry","shipping_proxy",round(float(r7),2),d,
            min(100,30+abs(m30)*2),["shipping","industrials"],ST["shipping"]+ST["industrials"][:3],
            f"SBLK: {m30:+.1f}% vs 30d, {m90:+.1f}% vs 90d. Trade {'up' if d=='bullish' else 'down'}.",z=m30/10))
        print(f"    Baltic: {m30:+.1f}% ({d})")
    except Exception as e: print(f"    Baltic: Failed — {e}")
    return signals

def fetch_enso_index():
    signals = []
    try:
        resp = requests.get("https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt", timeout=15)
        resp.raise_for_status()
        recs = []
        for line in resp.text.strip().split("\n")[1:]:
            p = line.split()
            if len(p)>=4:
                try: recs.append(float(p[3]))
                except ValueError: pass
        if len(recs)<4: return signals
        oni, pa = recs[-1], sum(recs[-4:-1])/3
        trend, stren = oni-pa, abs(oni)>abs(pa)
        if abs(oni)<ENSO_MODERATE_THRESHOLD: print(f"    ENSO: ONI {oni:+.2f} (neutral)"); return signals
        en = oni>0; phase = "el_nino" if en else "la_nina"
        strong = abs(oni)>=ENSO_STRONG_THRESHOLD
        lbl = "Strong" if strong else "Moderate"
        st = min(100,(ENSO_STRONG_STRENGTH if strong else ENSO_MODERATE_STRENGTH)+(10 if stren else 0))
        ts = f"{'strengthening' if stren else 'weakening'} {trend:+.2f}"
        if en:
            signals.append(_sig("noaa_enso",f"enso_{phase}_energy",oni,"bullish",st,
                ["energy"],ST["energy"],f"ENSO ONI {oni:+.1f} ({lbl} El Nino, {ts}). Bullish energy.",z=oni/0.5))
            signals.append(_sig("noaa_enso",f"enso_{phase}_ag",oni,"bearish",st,
                ["agriculture"],ST["agriculture"],f"ENSO ONI {oni:+.1f} ({lbl} El Nino). Crop stress.",z=oni/0.5))
        else:
            signals.append(_sig("noaa_enso",f"enso_{phase}_fert",oni,"bullish",st,
                ["fertilizer"],ST["fertilizer"],f"ENSO ONI {oni:+.1f} ({lbl} La Nina, {ts}). Drought risk.",z=oni/-0.5))
            signals.append(_sig("noaa_enso",f"enso_{phase}_ins",oni,"mixed",max(40,st-15),
                ["insurance"],ST["insurance"],f"ENSO ONI {oni:+.1f} ({lbl} La Nina). Mixed impact.",z=oni/-0.5))
        print(f"    ENSO: ONI {oni:+.2f} ({lbl} {'El Nino' if en else 'La Nina'}) -> {len(signals)} signals")
    except Exception as e: print(f"    ENSO: Failed — {e}")
    return signals

def fetch_ndvi_crop_health():
    signals = []
    try:
        td = date.today(); doy,yr = td.timetuple().tm_yday, td.year
        for lat,lon,rname,crop,smap in AG:
            try:
                resp = requests.get("https://modis.ornl.gov/rst/api/v1/MOD13Q1/subset",
                    params={"latitude":lat,"longitude":lon,"band":"250m_16_days_NDVI",
                        "startDate":f"A{yr}{max(1,doy-64):03d}","endDate":f"A{yr}{doy:03d}",
                        "kmAboveBelow":0,"kmLeftRight":0}, timeout=30)
                if resp.status_code!=200: time.sleep(NDVI_QUERY_DELAY); continue
                subsets = resp.json().get("subset",[])
                if not subsets: time.sleep(NDVI_QUERY_DELAY); continue
                vals = [r.get("data",[])[0]*0.0001 for r in subsets if r.get("data") and -2000<=r["data"][0]<=10000]
                if len(vals)<2: time.sleep(NDVI_QUERY_DELAY); continue
                cur,hist = vals[-1], vals[:-1]
                hm = sum(hist)/len(hist)
                hs = max(0.01,(sum((v-hm)**2 for v in hist)/len(hist))**0.5 if len(hist)>=2 else 0.05)
                z = (cur-hm)/hs
                if abs(z)<NDVI_ZSCORE_THRESHOLD: time.sleep(NDVI_QUERY_DELAY); continue
                st = min(100, NDVI_STRESS_BASE_STRENGTH+abs(z)*10)
                rn = rname.lower().replace(' ','_')
                if z<0:
                    signals.append(_sig("nasa_ndvi",f"ndvi_stress_{rn}",round(cur,4),"bullish",st,
                        smap["sb"],_tf(smap["sb"]),f"{rname} NDVI z={z:.1f}. {crop} stress. Bullish fert.",z=round(z,2)))
                    bt = _tf(smap["se"])
                    if bt:
                        signals.append(_sig("nasa_ndvi",f"ndvi_stress_{rn}_bear",round(cur,4),"bearish",
                            max(40,st-15),smap["se"],bt,f"{rname} NDVI z={z:.1f}. {crop} acreage risk.",z=round(z,2)))
                else:
                    signals.append(_sig("nasa_ndvi",f"ndvi_surplus_{rn}",round(cur,4),"bearish",
                        max(40,st-10),["fertilizer"],ST.get("fertilizer",[]),
                        f"{rname} NDVI z=+{z:.1f}. Bumper {crop}. Bearish fert.",z=round(z,2)))
                time.sleep(NDVI_QUERY_DELAY)
            except Exception as e: print(f"    NDVI {rname}: Failed — {e}"); time.sleep(NDVI_QUERY_DELAY)
        print(f"    NDVI: {len(AG)} regions -> {len(signals)} signals")
    except Exception as e: print(f"    NDVI: Failed — {e}")
    return signals

def _score_symbols(today):
    sigs = query("SELECT source,indicator,signal_strength,affected_sectors,affected_tickers,date "
        "FROM alternative_data WHERE date>=date('now','-7 days')")
    if not sigs: return
    ss = {r["symbol"]:r["sector"] for r in query("SELECT symbol,sector FROM stock_universe")}
    sc = {}
    for s in sigs:
        try: tks=json.loads(s["affected_tickers"] or "[]"); secs=json.loads(s["affected_sectors"] or "[]")
        except (json.JSONDecodeError,TypeError): continue
        w = (s["signal_strength"] or 0)*max(0.3,1.0-(date.today()-date.fromisoformat(s["date"])).days*0.1)
        for tk in tks:
            sc.setdefault(tk,{"t":0,"s":[]}); sc[tk]["t"]+=w; sc[tk]["s"].append(f"{s['source']}:{s['indicator']}")
        for sym,sec in ss.items():
            if sec and any(x in sec.lower() for x in secs):
                sc.setdefault(sym,{"t":0,"s":[]}); sc[sym]["t"]+=w*0.3
    if not sc: return
    mx = max(d["t"] for d in sc.values()) or 1
    rows = [(sym,today,min(100,d["t"]/mx*100),json.dumps(list(set(d["s"]))[:5]))
            for sym,d in sc.items() if d["t"]/mx*100>=10]
    if rows:
        with get_conn() as conn:
            conn.executemany("INSERT OR REPLACE INTO alt_data_scores (symbol,date,alt_data_score,contributing_signals) VALUES (?,?,?,?)",rows)
    print(f"  Scored {len(rows)} symbols")

def run():
    init_db(); today = date.today().isoformat()
    print("\n"+"="*60+"\n  ALTERNATIVE DATA INGESTION\n"+"="*60)
    all_sigs = []
    print("  Fetching alternative data...")
    for fn in [fetch_noaa_weather,fetch_nasa_firms,fetch_google_trends,
               fetch_usda_data,fetch_china_activity_proxy,fetch_baltic_dry]:
        all_sigs.extend(fn())
    print("  Fetching satellite data...")
    all_sigs.extend(fetch_enso_index()); all_sigs.extend(fetch_ndvi_crop_health())
    if all_sigs:
        rows = [(today,s["source"],s["indicator"],s.get("value"),s.get("value_zscore"),
                 s.get("affected_sectors","[]"),s.get("affected_tickers","[]"),
                 s.get("signal_direction","neutral"),s.get("signal_strength",0),
                 s.get("narrative",""),json.dumps(s)) for s in all_sigs]
        with get_conn() as conn:
            conn.executemany("INSERT OR REPLACE INTO alternative_data "
                "(date,source,indicator,value,value_zscore,affected_sectors,"
                "affected_tickers,signal_direction,signal_strength,narrative,raw_data) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",rows)
    print("  Computing scores..."); _score_symbols(today)
    print(f"\n  Alt data: {len(all_sigs)} signals from {len(set(s['source'] for s in all_sigs))} sources\n"+"="*60)

if __name__ == "__main__": run()
