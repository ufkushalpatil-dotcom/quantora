from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Optional
from pathlib import Path
import os, math, statistics, time
import httpx
import feedparser

BASE = "https://data-api.binance.vision"
app = FastAPI(title="Quantora API", version="1.0.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=False,
    allow_methods=["GET", "POST"], allow_headers=["*"]
)

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"

async def binance(path: str, params: dict):
    async with httpx.AsyncClient(timeout=12) as client:
        try:
            r = await client.get(BASE + path, params=params)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=502, detail=f"Market-data provider returned HTTP {e.response.status_code}")
        except httpx.RequestError:
            raise HTTPException(status_code=503, detail="Market-data provider is temporarily unreachable")

@app.get("/api/health")
def health():
    return {"status":"ok", "service":"quantora-api", "mode":"read-only market data + educational simulation"}

@app.get("/api/ticker")
async def ticker(symbols: str = Query("BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT")):
    wanted = [s.upper().strip() for s in symbols.split(",") if s.strip()]
    if len(wanted) > 20 or any(not s.isalnum() for s in wanted):
        raise HTTPException(400, "Use up to 20 alphanumeric exchange symbols.")
    data = await binance("/api/v3/ticker/24hr", {})
    by_symbol = {x["symbol"]: x for x in data}
    return {"source":"Binance public spot market data", "updated_at":int(time.time()),
            "data":[by_symbol[s] for s in wanted if s in by_symbol]}

@app.get("/api/klines")
async def klines(symbol: str="BTCUSDT", interval: str="1h", limit: int=300):
    symbol=symbol.upper()
    if not symbol.isalnum(): raise HTTPException(400,"Invalid symbol")
    if interval not in {"1m","3m","5m","15m","30m","1h","2h","4h","6h","8h","12h","1d","3d","1w","1M"}:
        raise HTTPException(400,"Unsupported interval")
    limit=max(20,min(limit,1000))
    rows=await binance("/api/v3/klines",{"symbol":symbol,"interval":interval,"limit":limit})
    return {"source":"Binance public spot market data","symbol":symbol,"interval":interval,
            "data":[{"time":int(x[0]/1000),"open":float(x[1]),"high":float(x[2]),
                     "low":float(x[3]),"close":float(x[4]),"volume":float(x[5])} for x in rows]}

def ema(values, period):
    if len(values)<period: return None
    k=2/(period+1); out=sum(values[:period])/period
    for v in values[period:]: out=v*k+out*(1-k)
    return out

def rsi(values, period=14):
    if len(values)<=period: return None
    gains=[]; losses=[]
    for i in range(1,len(values)):
        d=values[i]-values[i-1]; gains.append(max(d,0)); losses.append(max(-d,0))
    ag=sum(gains[:period])/period; al=sum(losses[:period])/period
    for i in range(period,len(gains)):
        ag=(ag*(period-1)+gains[i])/period; al=(al*(period-1)+losses[i])/period
    if al==0: return 100.0
    return 100-(100/(1+ag/al))

@app.get("/api/analyze")
async def analyze(symbol: str="BTCUSDT", interval: str="1h"):
    result=await klines(symbol,interval,300)
    rows=result["data"]; closes=[x["close"] for x in rows]; volumes=[x["volume"] for x in rows]
    last=closes[-1]; e20=ema(closes,20); e50=ema(closes,50); rv=rsi(closes)
    avgvol=sum(volumes[-21:-1])/20 if len(volumes)>=21 else 0
    volratio=(volumes[-1]/avgvol) if avgvol else None
    pct=((last/closes[-2])-1)*100 if len(closes)>1 else 0
    technical = ("Close is above both EMA20 and EMA50." if e20 and e50 and last>e20>e50 else
                 "Close is below both EMA20 and EMA50." if e20 and e50 and last<e20<e50 else
                 "Moving-average structure is mixed.")
    flow = (f"Latest candle volume is {volratio:.2f}× the prior 20-candle average." if volratio else "Not enough volume history.")
    momentum = f"RSI(14): {rv:.1f}" if rv is not None else "RSI unavailable."
    return {"source":result["source"],"symbol":symbol.upper(),"interval":interval,
            "as_of":rows[-1]["time"],"price":last,"change_pct":pct,
            "lanes":{"technical":technical+" "+momentum,
                     "flow":flow,
                     "news":"News context is not inferred from price data. Connect and review current headlines separately.",
                     "macro":"Macro context is not inferred from candles. Check current economic releases separately."},
            "indicators":{"ema20":e20,"ema50":e50,"rsi14":rv,"volume_ratio":volratio},
            "disclaimer":"Educational indicator summary only; not a prediction, recommendation, or trade signal."}

class BacktestRequest(BaseModel):
    symbol: str = Field(default="BTCUSDT", pattern=r"^[A-Za-z0-9]{3,20}$")
    interval: str = "1h"
    limit: int = Field(default=500, ge=100, le=1000)
    fast: int = Field(default=20, ge=2, le=100)
    slow: int = Field(default=50, ge=3, le=200)
    fee_bps: float = Field(default=10, ge=0, le=100)

@app.post("/api/backtest")
async def backtest(req: BacktestRequest):
    if req.fast >= req.slow: raise HTTPException(400,"Fast average must be shorter than slow average.")
    data=(await klines(req.symbol,req.interval,req.limit))["data"]
    closes=[x["close"] for x in data]
    if len(closes)<req.slow+5: raise HTTPException(400,"Not enough candles for these settings.")
    cash=10000.0; units=0.0; equity=[]; trades=0; fee=req.fee_bps/10000
    def sma(vals,end,p): return sum(vals[end-p+1:end+1])/p
    for i in range(req.slow, len(closes)):
        fast=sma(closes,i,req.fast); slow=sma(closes,i,req.slow)
        prevfast=sma(closes,i-1,req.fast); prevslow=sma(closes,i-1,req.slow)
        price=closes[i]
        # Long-only educational simulation; no leverage or real orders.
        if units==0 and prevfast<=prevslow and fast>slow:
            units=(cash*(1-fee))/price; cash=0; trades+=1
        elif units>0 and prevfast>=prevslow and fast<slow:
            cash=units*price*(1-fee); units=0; trades+=1
        equity.append(cash+units*price)
    final=equity[-1]; ret=(final/10000-1)*100
    peak=equity[0]; maxdd=0
    for v in equity:
        peak=max(peak,v); maxdd=min(maxdd,(v/peak-1)*100)
    return {"source":"Binance historical public candles","symbol":req.symbol.upper(),"interval":req.interval,
            "candles_tested":len(closes),"fast_sma":req.fast,"slow_sma":req.slow,"fee_bps":req.fee_bps,
            "starting_balance":10000,"ending_equity":round(final,2),"return_pct":round(ret,2),
            "max_drawdown_pct":round(maxdd,2),"closed_and_open_events":trades,
            "method":"Long-only SMA crossover; full-balance exposure; fee applied per simulated entry/exit; no slippage or spread model.",
            "disclaimer":"Historical simulation is not a forecast. Past performance does not predict future outcomes. This does not place orders."}

@app.get("/api/news")
async def news():
    feeds=["https://www.coindesk.com/arc/outboundfeeds/rss/","https://cointelegraph.com/rss"]
    items=[]
    async with httpx.AsyncClient(timeout=10,headers={"User-Agent":"QuantoraEducational/1.0"}) as client:
        for url in feeds:
            try:
                r=await client.get(url); r.raise_for_status()
                parsed=feedparser.parse(r.text)
                for entry in parsed.entries[:8]:
                    items.append({"title":entry.get("title","Untitled"),"url":entry.get("link",""),
                                  "published":entry.get("published",""),"source":parsed.feed.get("title",url)})
            except Exception:
                continue
    return {"items":items[:16],"note":"Headlines are provided by third-party publishers. Verify details at the source."}

class AIRequest(BaseModel):
    prompt: str = Field(min_length=10, max_length=2000)
    symbol: str = "BTCUSDT"
    interval: str = "1h"

@app.post("/api/ai")
async def ai(req: AIRequest):
    # Optional local Ollama integration. No API key or paid service is required,
    # but the user must install Ollama and download a model on their own machine.
    base=os.getenv("OLLAMA_URL","http://localhost:11434").rstrip("/")
    model=os.getenv("OLLAMA_MODEL","qwen2.5:3b")
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            r=await client.post(base+"/api/generate",json={
                "model":model,"stream":False,
                "prompt":("You are an educational financial-literacy assistant. Do not give buy/sell instructions, price targets, "
                          "personalized investment advice, or encourage real-money trading. Explain uncertainty and risks. "
                          "Use concise language. User question: "+req.prompt)})
            r.raise_for_status()
            return {"mode":"local-ollama","model":model,"answer":r.json().get("response","")}
    except Exception:
        raise HTTPException(503,detail="Local AI is not connected. Install Ollama, download a model, and set OLLAMA_URL / OLLAMA_MODEL. Market data and backtesting work without AI.")

if FRONTEND.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND), name="assets")
    @app.get("/")
    def home(): return FileResponse(FRONTEND/"index.html")
