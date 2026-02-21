'''
CALL: revenge_trader(file_name, sensitivity=1.5, max_gap=2)
Returns a dict of anomaly periods per behavior type:
{
  "size_increase_after_loss":    ["2025-03-01 09:30:00;2025-03-01 10:00:00", ...],
  "escalation_after_loss_streak":[...]
}
Each entry = "start_timestamp;end_timestamp" of an anomaly window.

Revenge trader: opens larger trades immediately after a loss, and increases
risk-taking following negative P/L streaks, impulsively trying to "win back"
losses rather than following a disciplined strategy.
'''

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Timestamp:
    year:   int
    month:  int
    day:    int
    hour:   int
    minute: int
    second: int

    def to_seconds(self):
        return (
            self.year  * 365 * 24 * 3600 +
            self.month * 30  * 24 * 3600 +
            self.day   * 24  * 3600      +
            self.hour        * 3600      +
            self.minute      * 60        +
            self.second
        )

    def to_string(self):
        return (f"{self.year:04}-{self.month:02}-{self.day:02} "
                f"{self.hour:02}:{self.minute:02}:{self.second:02}")


@dataclass
class Trade:
    timestamp: Timestamp
    pnl:       float
    quantity:  float


# ---------------------------------------------------------------------------
# File parsing
# ---------------------------------------------------------------------------

def parse_trades(file_name: str) -> list[Trade]:
    '''Read CSV, build Trade objects.'''
    trades = []

    with open(file_name, "r") as f:
        next(f)                                     # skip header
        for line in f:
            parts = line.strip().split(",")
            if len(parts) < 7:
                continue

            raw_ts = parts[0].strip()
            if " " not in raw_ts:
                continue

            date_part, time_part = raw_ts.split(" ")
            year, month, day     = date_part.split("-")
            hour, minute, second = time_part.split(":")

            ts = Timestamp(
                year=int(year), month=int(month), day=int(day),
                hour=int(hour), minute=int(minute), second=int(second)
            )

            try:
                pnl      = float(parts[6].strip())   # profit_loss column
                quantity = float(parts[3].strip())   # quantity column
            except ValueError:
                continue

            trades.append(Trade(timestamp=ts, pnl=pnl, quantity=quantity))

    return trades


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

def calculate_threshold(scores: list[float], sensitivity: float, above: bool = True):
    '''
    Median + MAD-based threshold.
    above=True  → flag values ABOVE  median + sensitivity * 1.4826 * MAD
    above=False → flag values BELOW  median - sensitivity * 1.4826 * MAD
    '''
    sorted_vals = sorted(scores)
    n = len(sorted_vals)
    median = (sorted_vals[n // 2] if n % 2 != 0
              else (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2)

    deviations = sorted([abs(v - median) for v in scores])
    mad = (deviations[n // 2] if n % 2 != 0
           else (deviations[n // 2 - 1] + deviations[n // 2]) / 2)

    spread = sensitivity * 1.4826 * mad
    threshold = median + spread if above else median - spread
    direction = "above" if above else "below"
    # print(f"    Median: {median:.3f} | MAD: {mad:.3f} | "
    #       f"Anomaly threshold: {direction} {threshold:.3f}")
    return threshold


def fill_gaps(flags: list[bool], max_gap: int = 2) -> list[bool]:
    '''Bridge anomaly regions separated by <= max_gap normal chunks.'''
    filled = flags[:]
    n = len(filled)
    i = 0
    while i < n:
        if filled[i]:
            j = i
            while j < n and filled[j]:
                j += 1
            gap = 0
            k = j
            while k < n and not filled[k] and gap < max_gap:
                gap += 1
                k += 1
            if k < n and filled[k]:
                for g in range(j, k):
                    filled[g] = True
            i = j
        else:
            i += 1
    return filled


def group_anomaly_periods(chunks: list[list[Trade]], flags: list[bool]) -> list[str]:
    '''Collapse consecutive flagged chunks into "start;end" strings.'''
    periods = []
    start = end = None
    for chunk, flag in zip(chunks, flags):
        if flag:
            if start is None:
                start = chunk[0].timestamp
            end = chunk[-1].timestamp
        else:
            if start is not None:
                periods.append(f"{start.to_string()};{end.to_string()}")
                start = end = None
    if start is not None:
        periods.append(f"{start.to_string()};{end.to_string()}")
    return periods


# ---------------------------------------------------------------------------
# Chunk scoring functions — one per revenge-trading behavior
# ---------------------------------------------------------------------------

def score_size_increase_after_loss(chunk: list[Trade]) -> float | None:
    '''
    For every trade that follows a loss, compute the ratio of its quantity
    to the losing trade's quantity.  Average that ratio over the chunk.

    Ratio > 1 on average → the trader consistently opens a larger position
    right after a loss (classic revenge-trading escalation).

    Returns None when the chunk contains no loss-followed-by-trade pairs.
    '''
    ratios = []
    for i in range(1, len(chunk)):
        prev = chunk[i - 1]
        curr = chunk[i]
        if prev.pnl < 0 and prev.quantity > 0:
            ratios.append(curr.quantity / (prev.quantity + 1e-9))
    if not ratios:
        return None
    return sum(ratios) / len(ratios)


def score_escalation_after_loss_streak(chunk: list[Trade]) -> float | None:
    '''
    Look for sub-sequences of 2+ consecutive losses ("loss streaks") and
    measure whether the trade immediately following the streak uses a larger
    position than the average quantity within the streak.

    Score = avg( post_streak_qty / avg_streak_qty ) across all streaks.
    High score → the trader routinely ramps up size after a run of losses.

    Returns None when the chunk contains no complete loss streaks.
    '''
    ratios = []
    i = 0
    while i < len(chunk):
        # Find start of a loss streak (>= 2 consecutive losses)
        if chunk[i].pnl < 0:
            j = i
            while j < len(chunk) and chunk[j].pnl < 0:
                j += 1
            streak_len = j - i
            if streak_len >= 2 and j < len(chunk):
                streak_qty = [chunk[k].quantity for k in range(i, j)]
                avg_streak_qty = sum(streak_qty) / len(streak_qty)
                post_qty = chunk[j].quantity
                if avg_streak_qty > 0:
                    ratios.append(post_qty / avg_streak_qty)
            i = j
        else:
            i += 1

    if not ratios:
        return None
    return sum(ratios) / len(ratios)


# ---------------------------------------------------------------------------
# Single-behavior detection pipeline
# ---------------------------------------------------------------------------

def detect_behavior(
    label:        str,
    valid_chunks: list[list[Trade]],
    scores:       list[float],
    indices:      list[int],
    above:        bool,
    sensitivity:  float,
    max_gap:      int,
) -> list[str]:
    '''
    Generic pipeline used by every behavior:
      1. compute threshold via median/MAD
      2. flag chunks
      3. fill gaps
      4. group into periods
      5. print results
    '''
    # print(f"\n{'=' * 60}")
    # print(f"  {label.upper().replace('_', ' ')}")
    # print(f"{'=' * 60}")

    threshold = calculate_threshold(scores, sensitivity, above=above)

    flags = [False] * len(valid_chunks)
    for score, idx in zip(scores, indices):
        if above:
            flags[idx] = score > threshold
        else:
            flags[idx] = score < threshold

    chunk_lines = []
    for i, (chunk, flag) in enumerate(zip(valid_chunks, flags)):
        score_val = scores[indices.index(i)] if i in indices else None
        score_str = f"{score_val:.4f}" if score_val is not None else "  N/A "
        marker    = True if flag else False
        chunk_lines.append((i, marker))

    flags   = fill_gaps(flags, max_gap=max_gap)
    periods = group_anomaly_periods(valid_chunks, flags)

    # print(f"\n  --- {label.replace('_', ' ').title()} Anomaly Periods ---")
    # if periods:
    #     for p in periods:
    #         print(f"  {p}")
    # else:
    #     print("  No anomalies detected.")

    return periods, chunk_lines


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def revenge_trader(file_name: str, sensitivity: float = 1.5, max_gap: int = 2) -> dict:
    trades = parse_trades(file_name)
    # print(f"[+] Loaded {len(trades)} trades from '{file_name}'")

    # Split into chunks of 10 (mirrors loss_aversion.py / overtrader.py)
    raw_chunks   = [trades[i:i + 10] for i in range(0, len(trades), 10)]
    valid_chunks = [c for c in raw_chunks if len(c) >= 2]
    # print(f"[+] Chunks: {len(valid_chunks)} (of size ~10 each)\n")

    results     = {}
    chunk_lines = {}

    # ------------------------------------------------------------------ #
    # 1. Position size increase immediately after a loss                  #
    # ------------------------------------------------------------------ #
    scores1, idx1 = [], []
    for i, chunk in enumerate(valid_chunks):
        s = score_size_increase_after_loss(chunk)
        if s is not None:
            scores1.append(s)
            idx1.append(i)

    results["size_increase_after_loss"], chunk_lines = detect_behavior(
        label        = "size_increase_after_loss",
        valid_chunks = valid_chunks,
        scores       = scores1,
        indices      = idx1,
        above        = True,      # anomaly = ratio is too HIGH
        sensitivity  = sensitivity,
        max_gap      = max_gap,
    )

    # ------------------------------------------------------------------ #
    # 2. Escalation after a negative P/L streak (>= 2 losses in a row)   #
    # ------------------------------------------------------------------ #
    scores2, idx2 = [], []
    for i, chunk in enumerate(valid_chunks):
        s = score_escalation_after_loss_streak(chunk)
        if s is not None:
            scores2.append(s)
            idx2.append(i)

    results["escalation_after_loss_streak"], chunk_lines = detect_behavior(
        label        = "escalation_after_loss_streak",
        valid_chunks = valid_chunks,
        scores       = scores2,
        indices      = idx2,
        above        = True,      # anomaly = ratio is too HIGH
        sensitivity  = sensitivity,
        max_gap      = max_gap,
    )

    # ------------------------------------------------------------------ #
    # Final summary                                                       #
    # ------------------------------------------------------------------ #
    # print(f"\n{'=' * 60}")
    # print("  REVENGE TRADER — SUMMARY")
    # print(f"{'=' * 60}")
    # for behavior, periods in results.items():
    #     print(f"  {behavior:<40} {len(periods):>4} anomaly period(s)")

    return results, chunk_lines


def _mad_threshold(scores: list[float], sensitivity: float, above: bool) -> float:
    sv = sorted(scores)
    n  = len(sv)
    median = sv[n // 2] if n % 2 != 0 else (sv[n // 2 - 1] + sv[n // 2]) / 2
    devs   = sorted(abs(v - median) for v in scores)
    mad    = devs[n // 2] if n % 2 != 0 else (devs[n // 2 - 1] + devs[n // 2]) / 2
    spread = sensitivity * 1.4826 * mad
    return median + spread if above else median - spread


def _flags_for(score_map: dict[int, float], n: int, sensitivity: float,
               above: bool, max_gap: int) -> list[bool]:
    if not score_map:
        return [False] * n
    threshold = _mad_threshold(list(score_map.values()), sensitivity, above)
    flags = [False] * n
    for idx, s in score_map.items():
        flags[idx] = s > threshold if above else s < threshold
    return fill_gaps(flags, max_gap)


def get_flags(valid_chunks: list, sensitivity: float = 1.5, max_gap: int = 2):
    '''
    Silent version: accepts pre-parsed chunks (each chunk is a list of Trade),
    returns flags_dict without any printing:
    {
        "size_increase_after_loss":    list[bool],
        "escalation_after_loss_streak":list[bool],
    }
    '''
    n = len(valid_chunks)

    sal_map = {i: s for i in range(n) if (s := score_size_increase_after_loss(valid_chunks[i]))     is not None}
    esc_map = {i: s for i in range(n) if (s := score_escalation_after_loss_streak(valid_chunks[i])) is not None}

    return {
        "size_increase_after_loss":    _flags_for(sal_map, n, sensitivity, above=True, max_gap=max_gap),
        "escalation_after_loss_streak":_flags_for(esc_map, n, sensitivity, above=True, max_gap=max_gap),
    }


def main():
    file_name = "uploads/mixed_trader.csv"
    _, chunk_lines = revenge_trader(file_name)
    for behavior, lines in chunk_lines.items():
        print(f"\n--- {behavior} ---")
        for line in lines:
            print(line)


if __name__ == "__main__":
    main()
