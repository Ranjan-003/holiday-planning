"""
Holiday Planning Template — Python Backend
WFM Scheduling Tool | Version 2.0

Provides:
  - Erlang C staffing calculation (voice)
  - Poisson interval-level volume distribution
  - Shrinkage compound build-up
  - Shift optimisation (greedy + ILP via scipy)
  - Combination scoring engine

Run:
  pip install flask flask-cors numpy scipy
  python data_engine.py

API runs at http://localhost:5050
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import math
import numpy as np
from scipy.optimize import linprog
from typing import Optional
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
app = Flask(__name__)
CORS(app)

PORT = 5050


# ================================================================
#  1. ERLANG C — VOICE STAFFING
# ================================================================

def log_factorial(n: int) -> float:
    """Log-space factorial; Stirling approximation for n > 20 (error < 0.001%)."""
    if n <= 1:
        return 0.0
    if n <= 20:
        return sum(math.log(i) for i in range(2, n + 1))
    return (n * math.log(n) - n + 0.5 * math.log(2 * math.pi * n) + 1 / (12 * n))


def erlang_c(agents: int, intensity: float) -> float:
    """
    Erlang C probability that a call will wait.
    Pure log-space arithmetic -- correct for any agent count up to 2000.
    No factorial overflow, no ValueError for agents >= 171 (FIX 5).
    """
    if agents <= 0 or intensity <= 0:
        return 1.0
    if intensity >= agents:
        return 1.0

    rho = intensity / agents
    safe_i = max(intensity, 1e-10)

    log_num = (agents * math.log(safe_i)
               - log_factorial(agents)
               + math.log(agents / (agents - intensity)))

    log_terms = [k * math.log(safe_i) - log_factorial(k) for k in range(agents)]

    max_log = max(log_num, max(log_terms) if log_terms else log_num)
    ec_num = math.exp(log_num - max_log)
    ec_den = ec_num + (1 - rho) * sum(math.exp(t - max_log) for t in log_terms)
    return min(1.0, max(0.0, ec_num / ec_den)) if ec_den > 0 else 1.0
def service_level_at_agents(
    agents: int,
    calls_per_hour: float,
    aht_seconds: float,
    sl_target_seconds: float
) -> float:
    """
    SL% achieved at a given agent count.
    Returns SL as fraction (0..1).
    """
    if calls_per_hour <= 0:
        return 1.0
    intensity = (calls_per_hour / 3600) * aht_seconds
    ec = erlang_c(agents, intensity)
    if agents <= intensity:
        return 0.0
    # mu = 3600/aht is the service rate expressed in calls-per-hour (not per-second).
    # Dividing by 3600 in the exponent converts back to the dimensionless form:
    #   exponent = -(N - A) * (3600/aht) * sl_sec / 3600 = -(N - A) * sl_sec / aht
    # This is algebraically identical to the JS formula -(agents-intensity)*(3600/aht)*slSec/3600.
    # The variable is named mu by convention but carries per-hour units — not per-second.
    # Downstream code that reuses this variable must treat it as calls/hour, not calls/second.
    mu = 3600 / aht_seconds  # service rate per agent per HOUR (calls/hour) — see note above
    exponent = -(agents - intensity) * mu * sl_target_seconds / 3600
    sl = 1.0 - ec * math.exp(exponent)
    return max(0.0, min(1.0, sl))


def agents_for_sl(
    calls_per_hour: float,
    aht_seconds: float,
    sl_target_pct: float,
    sl_target_seconds: float,
    max_agents: int = 2000
) -> int:
    """
    Minimum agents required to meet SL target.
    Binary search from ceil(intensity) upward.
    FIX 4: guard against AHT=0 or calls=0.
    """
    if calls_per_hour <= 0 or aht_seconds <= 0:
        return 0
    intensity = (calls_per_hour / 3600) * aht_seconds
    min_agents = max(1, math.ceil(intensity) + 1)
    target = sl_target_pct / 100.0

    for n in range(min_agents, max_agents + 1):
        if service_level_at_agents(n, calls_per_hour, aht_seconds, sl_target_seconds) >= target:
            return n
    return max_agents


# ================================================================
#  2. CHAT STAFFING — CONCURRENCY MODEL
# ================================================================

def chat_agents_required(
    chats_per_hour: float,
    aht_seconds: float,
    concurrency: float,
    occupancy_target_pct: float
) -> dict:
    """
    Chat staffing via concurrency model.
    Concurrent sessions per agent = concurrency.
    Net agents = ceil(offered_load / concurrency).
    Gross agents = net / (occupancy_target / 100).
    """
    if chats_per_hour <= 0:
        return {"net": 0, "gross": 0, "occupancy_actual": 0.0}

    offered_load = (chats_per_hour / 3600) * aht_seconds  # in Erlangs
    net = math.ceil(offered_load / concurrency)
    occupancy_actual = (offered_load / net) * 100 if net > 0 else 0
    gross = math.ceil(net / (occupancy_target_pct / 100))
    return {
        "net": net,
        "gross": gross,
        "occupancy_actual": round(occupancy_actual, 1)
    }


# ================================================================
#  3. EMAIL STAFFING — THROUGHPUT MODEL
# ================================================================

def email_agents_required(
    emails_per_day: float,
    aht_seconds: float,
    operating_hours: float,
    occupancy_target_pct: float,
    operating_start: str = "08:00",
    operating_end: str = "20:00"
) -> dict:
    """
    Email staffing via daily throughput.
    Uses actual operating window duration (overnight-aware).
    Emails handled per agent per day = (operating_hours * 3600 * occupancy) / AHT.
    Net agents = ceil(emails_per_day / throughput_per_agent).
    """
    if emails_per_day <= 0:
        return {"net": 0, "gross": 0, "throughput_per_agent": 0}

    # Use actual operating window if not explicitly provided
    if operating_hours <= 0:
        start_h, start_m = map(int, operating_start.split(":"))
        end_h,   end_m   = map(int, operating_end.split(":"))
        start_mins = start_h * 60 + start_m
        end_mins   = end_h   * 60 + end_m
        # overnight-aware duration
        operating_hours = ((end_mins - start_mins) % 1440) / 60
        if operating_hours <= 0:
            operating_hours = 12  # fallback

    throughput = (operating_hours * 3600 * (occupancy_target_pct / 100)) / aht_seconds
    throughput = max(throughput, 0.01)
    net = math.ceil(emails_per_day / throughput)
    gross = net
    return {
        "net": net,
        "gross": gross,
        "throughput_per_agent": round(throughput, 1),
        "operating_hours_used": round(operating_hours, 2)
    }


# ================================================================
#  4. SHRINKAGE COMPOUND BUILD-UP
# ================================================================

def compound_shrinkage(
    planned_leave_pct: float,
    unplanned_leave_pct: float,
    training_pct: float
) -> dict:
    """
    Compound shrinkage = 1 - (1-PL)(1-UL)(1-TR)
    Returns total shrinkage % and gross multiplier.
    """
    pl = planned_leave_pct / 100
    ul = unplanned_leave_pct / 100
    tr = training_pct / 100
    total = 1 - (1 - pl) * (1 - ul) * (1 - tr)
    return {
        "planned_leave_pct": planned_leave_pct,
        "unplanned_leave_pct": unplanned_leave_pct,
        "training_pct": training_pct,
        "total_shrinkage_pct": round(total * 100, 2),
        "gross_multiplier": round(1 / (1 - total), 4) if total < 1 else None
    }


def gross_hc(net_hc: float, total_shrinkage_pct: float) -> float:
    s = total_shrinkage_pct / 100
    if s >= 1:
        return float("inf")
    return net_hc / (1 - s)


# ================================================================
#  5. POISSON INTERVAL DISTRIBUTION
# ================================================================

def distribute_volume_to_intervals(
    daily_volume: float,
    operating_start: str,
    operating_end: str,
    interval_minutes: int = 30,
    profile: Optional[list] = None
) -> list:
    """
    Distribute daily volume to 30-min intervals.
    Supports overnight operating windows (e.g. 22:00–06:00).
    profile: list of weights, one per interval (auto-normalised to sum=1).
             If None, uses a bell-curve distribution peaking at midday.
    Returns list of dicts: [{interval, start, end, volume, calls_per_hour}, ...]
    """
    start_h, start_m = map(int, operating_start.split(":"))
    end_h,   end_m   = map(int, operating_end.split(":"))
    start_total = start_h * 60 + start_m
    end_total   = end_h   * 60 + end_m

    # FIX: overnight-aware duration
    total_minutes = (end_total - start_total) % 1440
    if total_minutes == 0:
        total_minutes = 1440  # full 24-hour window
    n_intervals = total_minutes // interval_minutes

    if n_intervals <= 0:
        return []

    if profile and len(profile) == n_intervals:
        weights = np.array(profile, dtype=float)
    else:
        x = np.linspace(0, 1, n_intervals)
        weights = np.exp(-((x - 0.45) ** 2) / (2 * 0.18 ** 2))

    weights = weights / weights.sum()

    results = []
    for i in range(n_intervals):
        slot_start_min = (start_total + i * interval_minutes) % 1440
        slot_end_min   = (start_total + (i + 1) * interval_minutes) % 1440
        vol = daily_volume * weights[i]
        results.append({
            "interval": i + 1,
            "start": f"{slot_start_min // 60:02d}:{slot_start_min % 60:02d}",
            "end":   f"{slot_end_min // 60:02d}:{slot_end_min % 60:02d}",
            "volume": round(vol, 1),
            "calls_per_hour": round(vol * (60 / interval_minutes), 1)
        })

    return results


# ================================================================
#  6. COMBINATION ENGINE
# ================================================================

def compute_impact_pct(actual: float, baseline: float) -> Optional[float]:
    if not baseline or baseline == 0:
        return None
    return round((actual - baseline) / baseline * 100, 2)


def score_combination(
    combo_name: str,
    impacts: list,
    years_available: list,
    anomaly_years: list
) -> float:
    """
    Score a combination (0..100) based on:
      - Consistency (low CV)
      - Recency (most recent years weighted higher)
      - Data richness (more years = better)
      - Anomaly penalty
    """
    if not impacts:
        return 0.0

    clean = [i for i in impacts if i is not None]
    if not clean:
        return 0.0

    # Consistency: inverse of CV (capped at 1.0)
    mean = np.mean(clean)
    std = np.std(clean) if len(clean) > 1 else 0
    cv = (std / abs(mean)) if mean != 0 else 1.0
    consistency_score = max(0, 1 - min(cv, 1.0))

    # Data richness: normalised to 5-year maximum (aligned to JS which uses impacts.length/5).
    # Previous value was /3.0 (3-year cap); updated to /5.0 to match the 5-year history model.
    richness_score = min(len(clean) / 5.0, 1.0)

    # Recency: average per-year weight across all years in the combination.
    # AUTHORITY: JS scoreCombo() in index.htm is the canonical implementation.
    # These weights are aligned to match exactly: Y1 (most recent) = 1.0 → Y5 = 0.1.
    # Previous weights (Y1:0.2, Y2:0.5, Y3:1.0) were inverted and have been corrected.
    # Y4 and Y5 added to support full 5-year history (JS handles Y1-Y5; backend aligned).
    # Recency design: mean recency of the combination — a Y1+Y5 combo scores 0.55,
    # higher than Y3-alone (0.5), reflecting that including Y1 lifts the combination's
    # recency even when paired with an older year. This is intentional: see JS comment.
    year_weights = {"Y1": 1.0, "Y2": 0.7, "Y3": 0.5, "Y4": 0.3, "Y5": 0.1}
    recency_total = 0
    recency_count = 0
    for y in years_available:
        if y not in anomaly_years:
            recency_total += year_weights.get(y, 0.1)
            recency_count += 1
    recency_score = (recency_total / recency_count) if recency_count else 0

    # Anomaly penalty: capped so anomalous data always scores above no data (floor=1).
    # Without the cap, 3 anomalous years produce penalty=0.9 against positive_sum<=1.0,
    # making raw potentially negative and the score 0 — same as an empty combination.
    # Guard: when positive_component is very small (e.g. Y5-only single year: ~0.03),
    # the cap ceiling (positive_component - 0.01) could be negative, making anomaly_penalty
    # negative and inflating the score. Fix: cap = max(0, positive_component - 0.01)
    # ensures the ceiling is never negative. If positive_component <= 0.01, no penalty
    # is applied and the score equals the tiny positive_component — ranked last.
    # WEIGHT SYNC WARNING: these weights (0.40 / 0.30 / 0.30) are also hardcoded in
    # scoreCombo() in index.htm. Changing weights here without updating index.htm will
    # cause Python-JS scoring divergence. Update both files simultaneously.
    positive_component = 0.40 * consistency_score + 0.30 * richness_score + 0.30 * recency_score
    raw_penalty = 0.3 * len([y for y in years_available if y in anomaly_years])
    penalty_cap = max(0.0, positive_component - 0.01)
    anomaly_penalty = min(raw_penalty, penalty_cap)

    raw = positive_component - anomaly_penalty

    return round(max(0, min(100, raw * 100)), 1)


def get_all_subsets(items: list) -> list:
    """Return all non-empty subsets of items (mirrors JS getAllSubsets)."""
    result = []
    n = len(items)
    for mask in range(1, 1 << n):
        subset = [items[i] for i in range(n) if mask & (1 << i)]
        result.append(subset)
    return result


def generate_combinations(
    historical: dict,
    anomaly_years: list,
    plan_volume: float
) -> list:
    """
    Generate all valid combinations from up to 5 year slots (Y1–Y5).
    historical: {"Y1": {"actual": x, "baseline": y}, ..., "Y5": ...}
    Returns sorted list of combination dicts.
    Aligned with JS generateCombinations() which uses getAllSubsets() over YEAR_SLOTS.
    """
    # Support full 5-year history — mirrors JS YEAR_SLOTS=['Y1','Y2','Y3','Y4','Y5']
    available_years = [y for y in ["Y1", "Y2", "Y3", "Y4", "Y5"] if y in historical]
    if not available_years:
        return []

    combos = []

    for subset in get_all_subsets(available_years):
        impacts = []
        for y in subset:
            d = historical[y]
            imp = compute_impact_pct(d["actual"], d["baseline"])
            if imp is not None:
                impacts.append(imp)
        if not impacts:
            continue
        avg = round(float(np.mean(impacts)), 2)
        forecasted = round(plan_volume * (1 + avg / 100), 0)
        any_anomaly = any(y in anomaly_years for y in subset)
        score = score_combination(
            f"Avg({'+'.join(subset)})" if len(subset) > 1 else subset[0],
            impacts, subset, anomaly_years
        )
        combo_name = subset[0] if len(subset) == 1 else f"Avg({'+'.join(subset)})"
        combos.append({
            "combo": combo_name,
            "years": subset,
            "impacts": impacts,
            "blended_impact_pct": avg,
            "forecasted_volume": forecasted,
            "score": score,
            "contains_anomaly": any_anomaly,
            "recommended": False
        })

    # Sort and flag recommendation
    combos.sort(key=lambda x: x["score"], reverse=True)
    if combos:
        combos[0]["recommended"] = True

    return combos


def _generate_combinations_legacy(
    historical: dict,
    anomaly_years: list,
    plan_volume: float
) -> list:
    """
    LEGACY: Original Y1/Y2/Y3-only generator. Retained for reference only.
    Use generate_combinations() which supports Y1-Y5.
    """
    available_years = [y for y in ["Y1", "Y2", "Y3"] if y in historical]
    if not available_years:
        return []

    combos = []

    # Single year combos
    for y in available_years:
        d = historical[y]
        imp = compute_impact_pct(d["actual"], d["baseline"])
        if imp is None:
            continue
        forecasted = round(plan_volume * (1 + imp / 100), 0)
        is_anomaly = y in anomaly_years
        score = score_combination(y, [imp], [y], anomaly_years)
        combos.append({
            "combo": y,
            "years": [y],
            "impacts": [imp],
            "blended_impact_pct": round(imp, 2),
            "forecasted_volume": forecasted,
            "score": score,
            "contains_anomaly": is_anomaly,
            "recommended": False
        })

    # Two-year combos
    two_year = [["Y1", "Y2"], ["Y2", "Y3"], ["Y1", "Y3"]]
    for pair in two_year:
        if all(y in available_years for y in pair):
            impacts = []
            for y in pair:
                d = historical[y]
                imp = compute_impact_pct(d["actual"], d["baseline"])
                if imp is not None:
                    impacts.append(imp)
            if len(impacts) == 2:
                avg = round(np.mean(impacts), 2)
                forecasted = round(plan_volume * (1 + avg / 100), 0)
                any_anomaly = any(y in anomaly_years for y in pair)
                score = score_combination(f"Avg({'+'.join(pair)})", impacts, pair, anomaly_years)
                combos.append({
                    "combo": f"Avg({'+'.join(pair)})",
                    "years": pair,
                    "impacts": impacts,
                    "blended_impact_pct": avg,
                    "forecasted_volume": forecasted,
                    "score": score,
                    "contains_anomaly": any_anomaly,
                    "recommended": False
                })

    # Three-year combo
    if len(available_years) == 3:
        impacts = []
        for y in available_years:
            d = historical[y]
            imp = compute_impact_pct(d["actual"], d["baseline"])
            if imp is not None:
                impacts.append(imp)
        if len(impacts) == 3:
            avg = round(np.mean(impacts), 2)
            forecasted = round(plan_volume * (1 + avg / 100), 0)
            any_anomaly = any(y in anomaly_years for y in available_years)
            score = score_combination("Avg(Y1+Y2+Y3)", impacts, available_years, anomaly_years)
            combos.append({
                "combo": "Avg(Y1+Y2+Y3)",
                "years": available_years,
                "impacts": impacts,
                "blended_impact_pct": avg,
                "forecasted_volume": forecasted,
                "score": score,
                "contains_anomaly": any_anomaly,
                "recommended": False
            })

    # Sort and flag recommendation
    combos.sort(key=lambda x: x["score"], reverse=True)
    if combos:
        combos[0]["recommended"] = True

    return combos


# ================================================================
#  7. DAY-INDEX FORECAST
# ================================================================

# WEIGHT SYNC WARNING: these weights must match DAY_INDEX_WEIGHTS in index.htm.
# Changing them here without updating the JS constant will cause Python-JS forecast divergence.
# Authority: index.htm DAY_INDEX_WEIGHTS = {Y1:0.40, Y2:0.30, Y3:0.20, Y4:0.07, Y5:0.03}
_DAY_INDEX_WEIGHTS = {"Y1": 0.40, "Y2": 0.30, "Y3": 0.20, "Y4": 0.07, "Y5": 0.03}


def day_index_forecast(years_data: dict, plan_volume: float) -> list:
    """
    Weighted day-of-week index forecast.

    years_data: dict mapping year slot (Y1..Y5) to a 7-element list of daily volumes.
                Example: {"Y1": [120, 90, 150, 200, 180, 160, 100], "Y2": [...]}
                Order: [Sat, Sun, Mon, Tue, Wed, Thu, Fri] — matches DAYS in index.htm.
                Missing slots are skipped. Slots with all-zero volumes are skipped.

    plan_volume: total weekly volume to distribute across 7 days.
                 The returned values sum to plan_volume within float rounding (±0.01).

    Returns: list of 7 floats, one per day (Sat..Fri order).
             When all input data is zero or missing, returns [plan_volume/7]*7 (flat split).
             Never raises; never returns NaN or Inf.

    Zero-guard: if plan_volume is 0, returns [0.0]*7.
    """
    if plan_volume == 0:
        return [0.0] * 7

    weighted_index = [0.0] * 7
    total_weight = 0.0

    for slot, w in _DAY_INDEX_WEIGHTS.items():
        if slot not in years_data:
            continue
        arr = years_data[slot]
        if not isinstance(arr, (list, tuple)) or len(arr) != 7:
            continue
        week_total = sum(float(v) for v in arr if v is not None)
        if week_total <= 0:
            continue  # skip zero-total years — same guard as JS computeDayIndexForecast
        for d in range(7):
            v = float(arr[d]) if arr[d] is not None else 0.0
            weighted_index[d] += w * (v / week_total)
        total_weight += w

    # All inputs were zero or missing — return flat split (plan_volume / 7 each)
    if total_weight <= 0:
        flat = plan_volume / 7.0
        return [flat] * 7

    # Normalise so weighted_index sums to 1.0 (accounts for partial year-weight coverage)
    index_sum = sum(weighted_index)
    if index_sum <= 0:
        flat = plan_volume / 7.0
        return [flat] * 7

    norm_index = [v / index_sum for v in weighted_index]

    # Project: each day = normalised_index[d] * plan_volume
    projected = [norm_index[d] * plan_volume for d in range(7)]

    return projected


# ================================================================
#  8. SHIFT OPTIMISATION — GREEDY + ILP
# ================================================================

def optimise_shifts(
    hc_requirements: list,
    available_shifts: list,
    available_agents: int,
    operating_start: str,
    operating_end: str,
    interval_minutes: int = 30
) -> dict:
    """
    Greedy shift optimisation.
    hc_requirements: [{"interval": 1, "start": "08:00", "net_hc": 12}, ...]
    available_shifts: [{"name": "Early", "start": "08:00", "end": "16:00"}, ...]
    Returns: recommended shift plan with agent counts per shift.
    """
    if not hc_requirements or not available_shifts:
        return {"error": "Missing requirements or shift templates"}

    n_intervals = len(hc_requirements)
    req = np.array([r["net_hc"] for r in hc_requirements], dtype=float)

    # Build coverage matrix: shift s covers interval i?
    def time_to_slot(t_str, base_start, interval_minutes):
        bh, bm = map(int, base_start.split(":"))
        th, tm = map(int, t_str.split(":"))
        delta = (th * 60 + tm) - (bh * 60 + bm)
        return delta // interval_minutes

    base = operating_start
    coverage = np.zeros((len(available_shifts), n_intervals), dtype=int)
    for si, sh in enumerate(available_shifts):
        s_slot = time_to_slot(sh["start"], base, interval_minutes)
        e_slot = time_to_slot(sh["end"], base, interval_minutes)
        for iv in range(max(0, s_slot), min(n_intervals, e_slot)):
            coverage[si, iv] = 1

    # Greedy: assign agents to shifts that reduce largest deficit first
    assigned = np.zeros(len(available_shifts), dtype=float)
    current_coverage = np.zeros(n_intervals, dtype=float)

    for _ in range(available_agents):
        deficit = req - current_coverage
        if np.all(deficit <= 0):
            break
        best_shift = -1
        best_gain = 0
        for si in range(len(available_shifts)):
            gain = np.sum(np.maximum(0, deficit) * coverage[si])
            if gain > best_gain:
                best_gain = gain
                best_shift = si
        if best_shift == -1:
            break
        assigned[best_shift] += 1
        current_coverage += coverage[best_shift]

    # Build result
    result_shifts = []
    for si, sh in enumerate(available_shifts):
        if assigned[si] > 0:
            result_shifts.append({
                "shift_name": sh["name"],
                "start": sh["start"],
                "end": sh["end"],
                "agents_assigned": int(assigned[si])
            })

    final_coverage = current_coverage
    interval_results = []
    for i, iv in enumerate(hc_requirements):
        planned = int(final_coverage[i])
        required = iv["net_hc"]
        delta = planned - required
        risk = "green" if delta >= 0 else ("amber" if delta >= -2 else "red")
        interval_results.append({
            "interval": iv["interval"],
            "start": iv["start"],
            "required_net_hc": required,
            "planned_hc": planned,
            "delta": delta,
            "sl_risk": risk
        })

    return {
        "recommended_shifts": result_shifts,
        "total_agents_used": int(assigned.sum()),
        "interval_coverage": interval_results,
        "intervals_at_risk": sum(1 for r in interval_results if r["sl_risk"] == "red"),
        "intervals_amber": sum(1 for r in interval_results if r["sl_risk"] == "amber"),
        "coverage_pct": round(
            100 * sum(1 for r in interval_results if r["sl_risk"] == "green") / len(interval_results), 1
        ) if interval_results else 0
    }


# ================================================================
#  9. API ROUTES
# ================================================================

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "WFM Holiday Planning Engine", "version": "2.0"})


@app.route("/api/shrinkage", methods=["POST"])
def api_shrinkage():
    """
    POST /api/shrinkage
    Body: { "planned_leave_pct": 8, "unplanned_leave_pct": 5, "training_pct": 3 }
    """
    data = request.get_json()
    result = compound_shrinkage(
        data.get("planned_leave_pct", 0),
        data.get("unplanned_leave_pct", 0),
        data.get("training_pct", 0)
    )
    return jsonify(result)


@app.route("/api/erlang_c", methods=["POST"])
def api_erlang_c():
    """
    POST /api/erlang_c
    Body: {
      "calls_per_hour": 120,
      "aht_seconds": 360,
      "sl_target_pct": 80,
      "sl_target_seconds": 20,
      "total_shrinkage_pct": 15
    }
    """
    data = request.get_json()
    cph = data.get("calls_per_hour", 0)
    aht = data.get("aht_seconds", 300)
    sl_pct = data.get("sl_target_pct", 80)
    sl_sec = data.get("sl_target_seconds", 20)
    shrink = data.get("total_shrinkage_pct", 0)

    net = agents_for_sl(cph, aht, sl_pct, sl_sec)
    grs = math.ceil(gross_hc(net, shrink))
    intensity = (cph / 3600) * aht if cph > 0 else 0
    actual_sl = service_level_at_agents(net, cph, aht, sl_sec) * 100

    return jsonify({
        "calls_per_hour": cph,
        "aht_seconds": aht,
        "intensity_erlangs": round(intensity, 2),
        "net_hc": net,
        "gross_hc": grs,
        "actual_sl_pct": round(actual_sl, 1),
        "shrinkage_pct": shrink
    })


@app.route("/api/chat_hc", methods=["POST"])
def api_chat_hc():
    """
    POST /api/chat_hc
    Body: {
      "chats_per_hour": 80,
      "aht_seconds": 480,
      "concurrency": 2.5,
      "occupancy_target_pct": 80,
      "total_shrinkage_pct": 15
    }
    """
    data = request.get_json()
    result = chat_agents_required(
        data.get("chats_per_hour", 0),
        data.get("aht_seconds", 480),
        data.get("concurrency", 2.0),
        data.get("occupancy_target_pct", 80)
    )
    shrink = data.get("total_shrinkage_pct", 0)
    result["gross_hc"] = math.ceil(gross_hc(result["net"], shrink))
    result["shrinkage_pct"] = shrink
    return jsonify(result)


@app.route("/api/email_hc", methods=["POST"])
def api_email_hc():
    """
    POST /api/email_hc
    Body: {
      "emails_per_day": 500,
      "aht_seconds": 600,
      "operating_hours": 0,          // 0 = auto-derive from start/end
      "operating_start": "08:00",
      "operating_end": "20:00",
      "occupancy_target_pct": 75,
      "total_shrinkage_pct": 15      // applied at API layer to produce gross_hc
    }

    NOTE (Critic item 6 — email shrinkage): shrinkage is applied here at the API
    layer (result["gross_hc"] = ceil(gross_hc(net, shrink))). The internal
    email_agents_required() function returns net=gross (no shrinkage uplift), which
    is correct — it computes net staffing from throughput. The API wrapper then
    applies the caller-supplied total_shrinkage_pct to produce gross_hc.
    If total_shrinkage_pct is omitted or 0, gross_hc will equal net_hc.
    API consumers must supply total_shrinkage_pct to receive a gross figure.
    """
    data = request.get_json()
    result = email_agents_required(
        data.get("emails_per_day", 0),
        data.get("aht_seconds", 600),
        data.get("operating_hours", 0),
        data.get("occupancy_target_pct", 75),
        data.get("operating_start", "08:00"),
        data.get("operating_end", "20:00")
    )
    shrink = data.get("total_shrinkage_pct", 0)
    result["gross_hc"] = math.ceil(gross_hc(result["net"], shrink))
    result["shrinkage_pct"] = shrink
    return jsonify(result)


@app.route("/api/interval_distribution", methods=["POST"])
def api_interval_distribution():
    """
    POST /api/interval_distribution
    Body: {
      "daily_volume": 1200,
      "operating_start": "08:00",
      "operating_end": "20:00",
      "interval_minutes": 30,
      "profile": [0.01, 0.02, ...]   // optional
    }
    """
    data = request.get_json()
    result = distribute_volume_to_intervals(
        data.get("daily_volume", 0),
        data.get("operating_start", "08:00"),
        data.get("operating_end", "20:00"),
        data.get("interval_minutes", 30),
        data.get("profile", None)
    )
    return jsonify({"intervals": result, "total_intervals": len(result)})


@app.route("/api/combinations", methods=["POST"])
def api_combinations():
    """
    POST /api/combinations
    Body: {
      "historical": {
        "Y1": {"actual": 3600, "baseline": 8500},
        "Y2": {"actual": 5100, "baseline": 9200},
        "Y3": {"actual": 5600, "baseline": 9800}
      },
      "anomaly_years": ["Y1"],
      "plan_volume": 9500
    }
    """
    data = request.get_json()
    combos = generate_combinations(
        data.get("historical", {}),
        data.get("anomaly_years", []),
        data.get("plan_volume", 0)
    )
    return jsonify({"combinations": combos, "total": len(combos)})


@app.route("/api/shift_optimise", methods=["POST"])
def api_shift_optimise():
    """
    POST /api/shift_optimise
    Body: {
      "hc_requirements": [{"interval": 1, "start": "08:00", "net_hc": 12}, ...],
      "available_shifts": [{"name": "Early", "start": "08:00", "end": "16:00"}, ...],
      "available_agents": 50,
      "operating_start": "08:00",
      "operating_end": "20:00",
      "interval_minutes": 30
    }
    """
    data = request.get_json()
    result = optimise_shifts(
        data.get("hc_requirements", []),
        data.get("available_shifts", []),
        data.get("available_agents", 100),
        data.get("operating_start", "08:00"),
        data.get("operating_end", "20:00"),
        data.get("interval_minutes", 30)
    )
    return jsonify(result)


@app.route("/api/full_day_hc", methods=["POST"])
def api_full_day_hc():
    """
    Convenience endpoint: computes interval-level HC for a full day.
    POST /api/full_day_hc
    Body: {
      "daily_volume": 1200,
      "channel": "voice",
      "aht_seconds": 360,
      "sl_target_pct": 80,
      "sl_target_seconds": 20,
      "concurrency": 2.5,
      "occupancy_target_pct": 85,
      "operating_start": "08:00",
      "operating_end": "20:00",
      "interval_minutes": 30,
      "total_shrinkage_pct": 15,
      "profile": null
    }
    """
    data = request.get_json()
    channel = data.get("channel", "voice")
    intervals = distribute_volume_to_intervals(
        data.get("daily_volume", 0),
        data.get("operating_start", "08:00"),
        data.get("operating_end", "20:00"),
        data.get("interval_minutes", 30),
        data.get("profile", None)
    )

    shrink = data.get("total_shrinkage_pct", 0)
    aht = data.get("aht_seconds", 360)
    results = []

    for iv in intervals:
        cph = iv["calls_per_hour"]
        if channel == "voice":
            net = agents_for_sl(cph, aht,
                                data.get("sl_target_pct", 80),
                                data.get("sl_target_seconds", 20))
        elif channel == "chat":
            r = chat_agents_required(cph, aht,
                                     data.get("concurrency", 2.0),
                                     data.get("occupancy_target_pct", 80))
            net = r["net"]
        elif channel == "email":
            r = email_agents_required(cph, aht, 0.5,
                                      data.get("occupancy_target_pct", 75))
            net = r["net"]
        else:
            net = math.ceil(cph / 3600 * aht / (data.get("occupancy_target_pct", 82) / 100))

        grs = math.ceil(gross_hc(net, shrink))
        results.append({**iv, "net_hc": net, "gross_hc": grs})

    daily_net = max(r["net_hc"] for r in results) if results else 0
    daily_gross = max(r["gross_hc"] for r in results) if results else 0

    return jsonify({
        "channel": channel,
        "daily_peak_net_hc": daily_net,
        "daily_peak_gross_hc": daily_gross,
        "intervals": results
    })


# ================================================================
#  10. MAIN
# ================================================================

if __name__ == "__main__":
    logging.info(f"WFM Holiday Planning Engine starting on port {PORT}")
    logging.info("Endpoints: /health  /api/shrinkage  /api/erlang_c  /api/chat_hc")
    logging.info("           /api/email_hc  /api/interval_distribution  /api/combinations")
    logging.info("           /api/shift_optimise  /api/full_day_hc")
    app.run(host="0.0.0.0", port=PORT, debug=False)
