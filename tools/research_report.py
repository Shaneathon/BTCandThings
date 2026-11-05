#!/usr/bin/env python3
"""Read-only BTCandThings performance audit. Python standard library only.

Uses SUPABASE_URL and SUPABASE_KEY from the environment. Every request is GET.
No live orders, DB writes, secret logging, or changes to the collector.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

def utc(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError, AttributeError):
        return None

def wilson(wins, total):
    if not total:
        return None
    z = 1.96
    p = wins / total
    d = 1 + z*z/total
    c = (p + z*z/(2*total))/d
    h = z * math.sqrt(p*(1-p)/total + z*z/(4*total*total))/d
    return [round(c-h, 4), round(c+h, 4)]

def fetch_table(table, columns, *, optional=False, max_pages=100):
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_KEY", "")
    if not base.startswith("https://") or not key:
        raise RuntimeError("Set SUPABASE_URL and a read-only SUPABASE_KEY securely")
    rows = []
    for page in range(max_pages):
        query = urlencode({"select": columns, "order": "id.asc" if table == "btc_lean_forecasts" else
                           ("recorded_at.asc" if table == "btc_predictions" else "window_start.asc"),
                           "limit": 1000, "offset": page*1000})
        req = Request(base + "/rest/v1/" + table + "?" + query,
                      headers={"apikey": key, "Authorization": "Bearer " + key,
                               "Accept": "application/json"}, method="GET")
        try:
            with urlopen(req, timeout=25) as response:
                batch = json.load(response)
        except Exception as exc:
            if optional:
                return [], "Optional table " + table + " unavailable (" + type(exc).__name__ + ")"
            raise RuntimeError("Could not read " + table + " (" + type(exc).__name__ + ")") from None
        if not isinstance(batch, list):
            raise RuntimeError("Unexpected response shape for " + table)
        rows.extend(batch)
        if len(batch) < 1000:
            return rows, None
    return rows, "WARNING: " + table + " reached pagination cap; audit may be incomplete"

def evaluate(markets, predictions, forecasts=None):
    forecasts = forecasts or []
    verified = {m["market_slug"]: m for m in markets
                if m.get("settlement_status") == "VERIFIED"
                and m.get("official_winner") in ("UP", "DOWN")
                and m.get("market_slug")}
    first = {}
    valid_preds = 0
    for p in predictions:
        slug = p.get("market_slug")
        if slug not in verified:
            continue
        try:
            prob = float(p.get("predicted_up_probability"))
        except (ValueError, TypeError):
            continue
        if not math.isfinite(prob) or not 0 <= prob <= 1:
            continue
        t = utc(p.get("recorded_at"))
        if t is None:
            continue
        valid_preds += 1
        if slug not in first or t < first[slug][0]:
            first[slug] = (t, prob, p)
    samples = []
    for slug, (t, p, row) in first.items():
        market = verified[slug]
        y = int(market["official_winner"] == "UP")
        start = utc(market.get("window_start"))
        elapsed = (t-start).total_seconds() if start else None
        samples.append({"slug": slug, "p": p, "y": y,
                        "correct": int((p >= .5) == bool(y)),
                        "model": row.get("model_version") or "unknown",
                        "elapsed_s": elapsed})
    n = len(samples)
    wins = sum(s["correct"] for s in samples)
    up = sum(s["y"] for s in samples)
    brier = sum((s["p"]-s["y"])**2 for s in samples)/n if n else None
    majority = max(up, n-up)/n if n else None
    groups = defaultdict(list)
    bins = defaultdict(list)
    for s in samples:
        groups[s["model"]].append(s)
        bins[min(4, int(s["p"]*5))].append(s)
    model_breakdown = {name: {"markets": len(a), "accuracy": round(sum(x["correct"] for x in a)/len(a), 4),
                              "brier": round(sum((x["p"]-x["y"])**2 for x in a)/len(a), 4)}
                       for name, a in sorted(groups.items())}
    stage_breakdown = {}
    for name, lower, upper in (("0-5m", 0, 300), ("5-10m", 300, 600),
                               ("10-15m", 600, 900)):
        subset = [x for x in samples if x["elapsed_s"] is not None
                  and lower <= x["elapsed_s"] < upper]
        stage_breakdown[name] = {
            "markets": len(subset),
            "accuracy": round(sum(x["correct"] for x in subset)/len(subset), 4) if subset else None,
            "brier": round(sum((x["p"]-x["y"])**2 for x in subset)/len(subset), 4) if subset else None}

    calibration = [{"p_range": f"{i*20}-{(i+1)*20}%", "markets": len(a),
                    "mean_predicted_up": round(sum(x["p"] for x in a)/len(a), 4),
                    "observed_up": round(sum(x["y"] for x in a)/len(a), 4)}
                   for i, a in sorted(bins.items())]
    late = sum(s["elapsed_s"] is None or s["elapsed_s"] >= 300 or s["elapsed_s"] < 0 for s in samples)
    horizon = {}
    for h in (3, 5):
        group = [f for f in forecasts if str(f.get("horizon_minutes")) == str(h)]
        scored = [f for f in group if f.get("evaluated_at") and
                  f.get("predicted_direction") in ("UP", "DOWN") and
                  isinstance(f.get("direction_correct"), bool)]
        horizon[str(h)] = {"saved": len(group), "scored_non_neutral": len(scored),
                           "accuracy": round(sum(f["direction_correct"] for f in scored)/len(scored), 4)
                           if scored else None,
                           "note": "Forecasts from overlapping windows are not independent."}
    times = [utc(m.get("window_start")) for m in markets]
    times = [t for t in times if t]
    expected = (int((max(times)-min(times)).total_seconds()//900)+1) if times else None
    return {
        "scope": "BTC 15-minute markets only; historical read-only audit",
        "tracked_markets": len(markets),
        "expected_windows_between_first_and_last": expected,
        "distinct_tracked_windows": len({m.get("window_start") for m in markets if m.get("window_start")}),
        "prediction_rows": len(predictions),
        "verified_markets": len(verified),
        "verified_markets_with_valid_predictions": n,
        "verified_markets_without_valid_predictions": len(verified)-n,
        "usable_prediction_rows_for_verified_markets": valid_preds,
        "accuracy": round(wins/n, 4) if n else None,
        "correct": wins,
        "incorrect": n-wins,
        "accuracy_wilson_95": wilson(wins, n),
        "majority_class_baseline_accuracy": round(majority, 4) if n else None,
        "up_outcome_share": round(up/n, 4) if n else None,
        "brier": round(brier, 4) if n else None,
        "constant_50pct_brier": 0.25,
        "first_predictions_at_or_after_5m_or_bad_timing": late,
        "by_first_prediction_stage": stage_breakdown,
        "by_model_version": model_breakdown,
        "calibration_bins": calibration,
        "lean_forecast_horizons": horizon,
        "profitability": "NOT MEASURABLE: no verified executions, complete entry/exit quotes, fees, or slippage",
        "method": "One earliest valid timestamped prediction per verified market; no repeated refreshes counted as independent tests."
    }

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", help="Optional output JSON file (local only)")
    args = parser.parse_args()
    markets, warn1 = fetch_table("btc_markets",
        "market_slug,window_start,window_end,settlement_status,official_winner")
    preds, warn2 = fetch_table("btc_predictions",
        "market_slug,recorded_at,predicted_up_probability,model_version")
    leans, warn3 = fetch_table("btc_lean_forecasts",
        "id,predicted_at,horizon_minutes,predicted_direction,direction_correct,evaluated_at",
        optional=True)
    report = evaluate(markets, preds, leans)
    report["warnings"] = [x for x in (warn1, warn2, warn3) if x]
    result = json.dumps(report, indent=2)
    if args.out:
        Path(args.out).write_text(result + "\n", encoding="utf-8")
        print("Saved read-only audit to " + args.out)
    else:
        print(result)

if __name__ == "__main__":
    main()
