#!/usr/bin/env python3
"""BTC 15m shadow challenger. No orders, no Supabase writes, no model promotion.

'once' captures one paired prediction per market stage (first 90 seconds).
'loop' repeats 'once' every 30s. 'report' scores only VERIFIED US outcomes.
Store the JSONL file on persistent storage, not ephemeral Streamlit storage.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import random
import statistics
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

VERSION = "Shadow Momentum V1 (untrained)"
BASELINE = "Pixel V13.5 Headless Baseline (reproduced)"
STAGES = (0, 5, 10)
DEFAULT_LOG = "btc_shadow_predictions.jsonl"

def iso(t):
    return datetime.fromtimestamp(int(t), timezone.utc).isoformat()

def get_json(url, headers=None):
    with urlopen(Request(url, headers=headers or {}, method="GET"), timeout=20) as r:
        return json.load(r)

def db_get(table, params):
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_KEY", "")
    if not base.startswith("https://") or not key:
        raise RuntimeError("Set SUPABASE_URL and a SELECT-only SUPABASE_KEY")
    return get_json(base + "/rest/v1/" + table + "?" + urlencode(params),
                    {"apikey": key, "Authorization": "Bearer " + key})

def completed_kraken():
    obj = get_json("https://api.kraken.com/0/public/OHLC?" +
                   urlencode({"pair": "XBTUSD", "interval": 1}))
    if obj.get("error"):
        raise RuntimeError("Kraken returned an error")
    rows = next(v for k, v in obj["result"].items() if k != "last")
    # Kraken's last row is the still-open candle.
    return [(int(r[0]), float(r[4])) for r in rows[:-1]]

def ema(values, period):
    a = 2 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(a*v + (1-a)*out[-1])
    return out

def rsi_last(closes, period=14):
    diffs = [b-a for a,b in zip(closes, closes[1:])]
    if len(diffs) < period:
        raise ValueError("Insufficient RSI history")
    gains = [max(d, 0.0) for d in diffs]
    losses = [max(-d, 0.0) for d in diffs]
    avg_gain = gains[0]
    avg_loss = losses[0]
    alpha = 1/period
    for g, l in zip(gains[1:], losses[1:]):
        avg_gain = alpha*g + (1-alpha)*avg_gain
        avg_loss = alpha*l + (1-alpha)*avg_loss
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    return 100 - 100/(1 + avg_gain/avg_loss)

def probabilities(candles, target, remaining):
    if len(candles) < 125 or not math.isfinite(target) or target <= 0:
        raise ValueError("Need 125 complete candles and a valid official target")
    closes = [c for _, c in candles]
    if any(c <= 0 or not math.isfinite(c) for c in closes):
        raise ValueError("Invalid Kraken candles")
    returns = [math.log(b/a) for a,b in zip(closes, closes[1:])]
    vol = statistics.stdev(returns[-120:])
    sigma = max(vol, 0.00005) * math.sqrt(max(remaining/60, 1))
    z = math.log(closes[-1]/target)/sigma
    champion = min(0.995, max(0.005, 0.5*(1+math.erf(z/math.sqrt(2)))))
    e9, e21 = ema(closes, 9), ema(closes, 21)
    rsi = rsi_last(closes)
    votes = [
        1 if e9[-1] > e21[-1] else -1 if e9[-1] < e21[-1] else 0,
        1 if e9[-1] > e9[-4] else -1 if e9[-1] < e9[-4] else 0,
        1 if closes[-1] > closes[-4] else -1 if closes[-1] < closes[-4] else 0,
        1 if rsi > 50 else -1 if rsi < 50 else 0,
        1 if closes[-1] > closes[-6] else -1 if closes[-1] < closes[-6] else 0,
    ]
    score = sum(votes)
    # Fixed, deliberately modest log-odds adjustment; NOT trained or validated.
    log_odds = math.log(champion/(1-champion))
    adjusted = max(-20, min(20, log_odds + 0.45 * score / 5))
    challenger = 1/(1+math.exp(-adjusted))
    return {"champion_up": champion, "challenger_up": challenger,
            "momentum_votes": score, "rsi": round(rsi, 2),
            "spot": closes[-1], "minute_volatility": vol}

def read_log(path):
    p = Path(path)
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows

def capture(path, now=None):
    now = int(time.time()) if now is None else int(now)
    start = now//900*900
    elapsed = now-start
    stage = elapsed//300
    if stage not in (0,1,2) or elapsed%300 >= 90:
        return "Outside stage capture window; no sample"
    slug = "btc-updown-15m-" + datetime.fromtimestamp(start, timezone.utc).strftime("%Y-%m-%d-%H%M") + "z"
    if any(r.get("market_slug") == slug and r.get("stage") == stage for r in read_log(path)):
        return "Already captured this market/stage"
    markets = db_get("btc_markets", {"select":"market_slug,price_to_beat,window_start",
                                     "market_slug":"eq."+slug, "limit":1})
    if not markets:
        return "Official market row not available yet; skipped"
    try:
        target = float(markets[0]["price_to_beat"])
    except (ValueError, TypeError, KeyError):
        return "Official price to beat not available yet; skipped"
    candles = completed_kraken()
    if not candles or not 0 <= now-(candles[-1][0]+60) < 120:
        return "Latest complete Kraken candle is stale; skipped"
    model = probabilities(candles, target, start+900-now)
    record = {"market_slug": slug, "window_start": iso(start),
              "captured_at": iso(now), "stage": stage,
              "candle_start": iso(candles[-1][0]), "price_to_beat": target,
              "champion_version": BASELINE, "challenger_version": VERSION,
              **model}
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Append-only research records. Run one instance per log file.
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, separators=(",", ":"))+"\n")
    return "Captured paired shadow predictions for " + slug + " stage " + str(stage)

def summarize(pairs):
    n = len(pairs)
    if not n:
        return {"markets": 0, "champion_accuracy": None, "challenger_accuracy": None,
                "champion_brier": None, "challenger_brier": None, "brier_improvement": None}
    def brier(row, key):
        return (float(row[key])-row["actual_up"])**2
    c = [brier(r, "champion_up") for r in pairs]
    q = [brier(r, "challenger_up") for r in pairs]
    diffs = [a-b for a,b in zip(c,q)]
    rng = random.Random(20261105)
    boot = []
    if n >= 2:
        for _ in range(1000):
            boot.append(sum(diffs[rng.randrange(n)] for _ in range(n))/n)
        boot.sort()
    return {"markets": n,
            "champion_accuracy": round(sum((r["champion_up"]>=.5)==bool(r["actual_up"]) for r in pairs)/n,4),
            "challenger_accuracy": round(sum((r["challenger_up"]>=.5)==bool(r["actual_up"]) for r in pairs)/n,4),
            "champion_brier": round(sum(c)/n,5),
            "challenger_brier": round(sum(q)/n,5),
            "brier_improvement": round(sum(diffs)/n,5),
            "paired_bootstrap_95_brier_improvement": [round(boot[25],5), round(boot[974],5)] if boot else None,
            "interpretation": "Positive Brier improvement favors challenger; interval excludes zero only if supported by data."}

def report(path):
    rows = read_log(path)
    if not rows:
        return {"status":"NO_SHADOW_SAMPLES", "note":"Shadow collection has not run on a persistent host."}
    verified = {}
    # Paginate without relying on the default PostgREST 1000-row limit.
    for offset in range(0, 100000, 1000):
        batch = db_get("btc_markets", {
            "select":"market_slug,official_winner,settlement_status",
            "settlement_status":"eq.VERIFIED", "official_winner":"in.(UP,DOWN)",
            "order":"window_start.asc", "limit":1000, "offset":offset})
        for m in batch:
            verified[m["market_slug"]] = m["official_winner"]
        if len(batch)<1000:
            break
    groups = defaultdict(list)
    seen = set()
    for r in rows:
        slug, stage = r.get("market_slug"), r.get("stage")
        if slug not in verified or stage not in (0,1,2) or (slug,stage) in seen:
            continue
        seen.add((slug,stage))
        try:
            p, q = float(r["champion_up"]), float(r["challenger_up"])
            if not (math.isfinite(p) and math.isfinite(q) and 0 <= p <= 1 and 0 <= q <= 1):
                continue
        except (ValueError, KeyError, TypeError):
            continue
        groups[stage].append({"champion_up":p, "challenger_up":q,
                              "actual_up":int(verified[slug]=="UP")})
    return {"status":"RESEARCH_ONLY_NO_AUTOMATIC_PROMOTION",
            "saved_samples":len(rows), "verified_markets_available":len(verified),
            "by_stage":{f"{s*5}-{(s+1)*5}m":summarize(groups[s]) for s in (0,1,2)},
            "promotion_gate":"Do not consider promotion before >=300 independent paired markets in a predeclared primary stage, positive out-of-sample Brier improvement with uncertainty assessed, and realistic positive paper-trading net returns.",
            "caveat":"Stages are correlated within each market; never pool them as independent observations."}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["once","loop","report"])
    p.add_argument("--log", default=DEFAULT_LOG)
    p.add_argument("--interval", type=int, default=30)
    args = p.parse_args()
    if args.command == "report":
        print(json.dumps(report(args.log), indent=2))
    elif args.command == "once":
        print(capture(args.log))
    else:
        if args.interval < 20:
            p.error("Interval must be at least 20 seconds")
        while True:
            try:
                print(iso(time.time()), capture(args.log), flush=True)
            except Exception as e:
                print(iso(time.time()), "Capture failed:", type(e).__name__, flush=True)
            time.sleep(args.interval)

if __name__ == "__main__":
    main()
