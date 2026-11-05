#!/usr/bin/env python3
"""Offline, read-only BTC champion-vs-challenger research.

The incumbent's archived probability is the champion. Fixed momentum/reversal
alternatives are challengers. Selection uses an earlier chronological segment;
a later untouched holdout measures whether the selected alternative generalizes.
This script NEVER modifies the live model, collector, database or trades.
"""
import argparse
from bisect import bisect_right
from collections import defaultdict
from datetime import timedelta
import json
import math
import random
from pathlib import Path

from research_report import fetch_table, utc

VARIANTS = {"momentum_mild": 0.20, "momentum_strong": 0.40,
            "reversal_mild": -0.20}
MIN_MARKETS = 250
MIN_HOLDOUT = 100


def clamp(x, lo, hi):
    return min(hi, max(lo, x))


def shifted_probability(base, return_3m, coefficient):
    """Bounded log-odds adjustment; no fitted parameters or future prices."""
    p = clamp(float(base), 0.005, 0.995)
    score = clamp(return_3m / 0.001, -2.0, 2.0)
    logit = math.log(p / (1.0 - p)) + coefficient * score
    return 1.0 / (1.0 + math.exp(-logit))


def build_rows(markets, predictions):
    """One early-window observation per market; historical spot lookup is causal."""
    verified = {m.get("market_slug"): m for m in markets
                if m.get("settlement_status") == "VERIFIED"
                and m.get("official_winner") in ("UP", "DOWN")}
    spots = []
    candidates = defaultdict(list)
    for p in predictions:
        t = utc(p.get("recorded_at"))
        try:
            spot = float(p.get("kraken_spot"))
            prob = float(p.get("predicted_up_probability"))
        except (ValueError, TypeError):
            continue
        if t is None or not all(map(math.isfinite, (spot, prob))) or spot <= 0 or not 0 <= prob <= 1:
            continue
        spots.append((t, spot))
        slug = p.get("market_slug")
        market = verified.get(slug)
        if not market:
            continue
        start = utc(market.get("window_start"))
        end = utc(market.get("window_end"))
        if start is None or end is None or not start < end:
            continue
        # Predeclared 0-5 minute checkpoint; do not cherry-pick a later signal.
        if start <= t < start + timedelta(minutes=5):
            candidates[slug].append((t, prob, spot, market, p.get("model_version") or "unknown"))
    spots.sort(key=lambda x: x[0])
    times = [t for t, _ in spots]
    rows = []
    no_lag = 0
    for slug, observations in candidates.items():
        t, prob, spot, market, version = min(observations, key=lambda x: x[0])
        target = t - timedelta(minutes=3)
        index = bisect_right(times, target) - 1
        # Require a completed observation close to the exact 3m lookback.
        if index < 0 or (target - times[index]).total_seconds() > 90:
            no_lag += 1
            continue
        past = spots[index][1]
        if past <= 0:
            no_lag += 1
            continue
        y = int(market["official_winner"] == "UP")
        ret = spot / past - 1.0
        rows.append({"market_slug": slug, "time": t, "window_end": utc(market["window_end"]),
                     "model_version": version, "actual": y, "champion": prob,
                     "challengers": {name: shifted_probability(prob, ret, coef)
                                     for name, coef in VARIANTS.items()}})
    rows.sort(key=lambda r: (r["time"], r["market_slug"]))
    return rows, {"verified_markets": len(verified), "markets_with_early_forecast": len(candidates),
                  "missing_3m_lookback": no_lag, "eligible_markets": len(rows)}


def brier(rows, key):
    if not rows:
        return None
    return sum((r["champion"] if key == "champion" else r["challengers"][key] - r["actual"])**2
               if key != "champion" else (r["champion"]-r["actual"])**2
               for r in rows) / len(rows)


def score(rows, key):
    if not rows:
        return {"markets": 0, "brier": None, "accuracy": None}
    probs = [(r["champion"] if key == "champion" else r["challengers"][key], r["actual"])
             for r in rows]
    return {"markets": len(rows),
            "brier": round(sum((p-y)**2 for p,y in probs)/len(rows), 5),
            "accuracy": round(sum((p >= .5) == bool(y) for p,y in probs)/len(rows), 4)}


def bootstrap_delta_interval(rows, candidate, reps=2000, seed=17):
    """Paired resampling by independent 15-minute market window."""
    rng = random.Random(seed)
    diffs = [(r["challengers"][candidate]-r["actual"])**2 -
             (r["champion"]-r["actual"])**2 for r in rows]
    n = len(diffs)
    if not n:
        return None
    values = sorted(sum(diffs[rng.randrange(n)] for _ in range(n))/n
                    for _ in range(reps))
    return [round(values[int(0.025*reps)], 5),
            round(values[int(0.975*reps)-1], 5)]


def compare(rows, coverage, warnings=None):
    """Chronological train/holdout split. No retraining on holdout labels."""
    warnings = warnings or []
    output = {"status": "insufficient_data", "coverage": coverage,
              "warnings": warnings,
              "design": "One first 0-5m prediction per verified BTC 15m market; 3m lag uses past prices only; chronological 60/40 split; challenger selected on training Brier; held-out comparison is not a live profit test.",
              "live_model_changed": False, "orders_placed": False}
    if len(rows) < MIN_MARKETS or warnings:
        output["reason"] = ("Incomplete data/pagination warnings" if warnings else
                            f"Need {MIN_MARKETS} eligible markets; currently {len(rows)}")
        return output
    cut = int(len(rows)*0.60)
    training, holdout = rows[:cut], rows[cut:]
    if len(holdout) < MIN_HOLDOUT:
        output["reason"] = "Holdout too small"
        return output
    train_scores = {"champion": score(training, "champion")}
    train_scores.update({name: score(training, name) for name in VARIANTS})
    # Choose one challenger using training labels only; not holdout results.
    selected = min(VARIANTS, key=lambda name: train_scores[name]["brier"])
    holdout_scores = {"champion": score(holdout, "champion")}
    holdout_scores.update({name: score(holdout, name) for name in VARIANTS})
    delta = holdout_scores[selected]["brier"]-holdout_scores["champion"]["brier"]
    ci = bootstrap_delta_interval(holdout, selected)
    promising = (delta < -0.005 and ci[1] < 0)
    output.update({
        "status": "evaluated",
        "train_markets": len(training), "holdout_markets": len(holdout),
        "train_scores": train_scores, "holdout_scores": holdout_scores,
        "selected_challenger": selected,
        "selected_holdout_brier_delta_vs_champion": round(delta, 5),
        "paired_bootstrap_95pct_delta_interval": ci,
        "next_step": ("Candidate for separate prospective shadow test; NOT approved for live deployment"
                      if promising else "Keep champion; continue collecting data and testing prospectively"),
        "promising_for_prospective_test": promising,
        "profitability": "Unknown: executable quotes, fees, slippage and paper fills not evaluated"
    })
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", help="Write local JSON report (no data uploaded)")
    args = parser.parse_args()
    markets, w1 = fetch_table("btc_markets",
        "market_slug,window_start,window_end,settlement_status,official_winner")
    predictions, w2 = fetch_table("btc_predictions",
        "market_slug,recorded_at,kraken_spot,predicted_up_probability,model_version")
    rows, coverage = build_rows(markets, predictions)
    result = compare(rows, coverage, [w for w in (w1, w2) if w])
    result["source"] = "Supabase read-only GET, using existing environment credentials"
    serialized = json.dumps(result, indent=2)
    if args.out:
        Path(args.out).write_text(serialized + "\n", encoding="utf-8")
        print("Saved research report to " + args.out)
    else:
        print(serialized)


if __name__ == "__main__":
    main()
