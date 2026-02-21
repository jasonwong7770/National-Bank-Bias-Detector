'''
CALL: loss_aversion(file_name, sensitivity=1.5, max_gap=2)
Returns a dict of anomaly periods per behavior type:
{
  "holding_losers_too_long":   ["2025-03-01 09:30:00;2025-03-01 10:00:00", ...],
  "closing_winners_early":     [...],
  "risk_reward_imbalance":     [...],
  "loss_size_exceeds_win_size":[...]
}
Each entry = "start_timestamp;end_timestamp" of an anomaly window.
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
    timestamp:        Timestamp
    pnl:              float
    quantity:         float
    duration_seconds: float = field(default=0.0)   # filled after parsing


# ---------------------------------------------------------------------------
# File parsing
# ---------------------------------------------------------------------------

def parse_trades(file_name: str) -> list[Trade]:
    '''Read CSV, build Trade objects. Duration is gap to the next trade's open.'''
    trades = []

    with open(file_name, "r") as f:
        next(f)                                     # skip header
        for line in f:
            parts = line.strip().split(",")
            if len(parts) < 7:
                continue

            raw_ts   = parts[0].strip()
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

    # Derive duration as gap to the next trade's open time
    for i in range(len(trades) - 1):
        trades[i].duration_seconds = max(
            0.0,
            trades[i + 1].timestamp.to_seconds() - trades[i].timestamp.to_seconds()
        )
    # Last trade gets the average of all other durations
    if len(trades) > 1:
        avg_dur = sum(t.duration_seconds for t in trades[:-1]) / (len(trades) - 1)
        trades[-1].duration_seconds = avg_dur

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
    print(f"    Median: {median:.3f} | MAD: {mad:.3f} | "
          f"Anomaly threshold: {direction} {threshold:.3f}")
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
# Chunk scoring functions — one per loss-aversion behavior
# ---------------------------------------------------------------------------

def score_holding_losers(chunk: list[Trade]) -> float | None:
    '''
    Ratio of avg losing-trade duration to avg winning-trade duration.
    High ratio → losers are being held much longer than winners (anomalous).
    Returns None when chunk has no winners or no losers.
    '''
    win_durs  = [t.duration_seconds for t in chunk if t.pnl > 0]
    loss_durs = [t.duration_seconds for t in chunk if t.pnl <= 0]
    if not win_durs or not loss_durs:
        return None
    avg_win  = sum(win_durs)  / len(win_durs)
    avg_loss = sum(loss_durs) / len(loss_durs)
    return avg_loss / (avg_win + 1e-9)


def score_closing_winners_early(chunk: list[Trade]) -> float | None:
    '''
    Average winning-trade duration within the chunk (seconds).
    Low value → winners are being closed unusually fast (anomalous).
    Returns None when chunk has no winners.
    '''
    win_durs = [t.duration_seconds for t in chunk if t.pnl > 0]
    if not win_durs:
        return None
    return sum(win_durs) / len(win_durs)


def score_risk_reward(chunk: list[Trade]) -> float | None:
    '''
    Ratio of avg absolute loss PnL to avg win PnL.
    High ratio → losses are larger than gains (poor risk/reward).
    Returns None when chunk has no winners or no losers.
    '''
    win_pnls  = [t.pnl          for t in chunk if t.pnl > 0]
    loss_pnls = [abs(t.pnl)     for t in chunk if t.pnl <= 0]
    if not win_pnls or not loss_pnls:
        return None
    avg_win  = sum(win_pnls)  / len(win_pnls)
    avg_loss = sum(loss_pnls) / len(loss_pnls)
    return avg_loss / (avg_win + 1e-9)


def score_loss_size(chunk: list[Trade]) -> float | None:
    '''
    Ratio of avg losing-trade quantity to avg winning-trade quantity.
    Ratio > 1 → trader is using larger positions on trades that end up losing.
    Returns None when chunk has no winners or no losers.
    '''
    win_qty  = [t.quantity for t in chunk if t.pnl > 0]
    loss_qty = [t.quantity for t in chunk if t.pnl <= 0]
    if not win_qty or not loss_qty:
        return None
    avg_win  = sum(win_qty)  / len(win_qty)
    avg_loss = sum(loss_qty) / len(loss_qty)
    return avg_loss / (avg_win + 1e-9)


# ---------------------------------------------------------------------------
# Single-behavior detection pipeline
# ---------------------------------------------------------------------------

def detect_behavior(
    label:       str,
    valid_chunks: list[list[Trade]],
    scores:      list[float],
    indices:     list[int],        # positions in valid_chunks that have a score
    above:       bool,
    sensitivity: float,
    max_gap:     int,
) -> list[str]:
    '''
    Generic pipeline used by every behavior:
      1. compute threshold via median/MAD
      2. flag chunks
      3. fill gaps
      4. group into periods
      5. print results
    '''
    print(f"\n{'=' * 60}")
    print(f"  {label.upper().replace('_', ' ')}")
    print(f"{'=' * 60}")

    threshold = calculate_threshold(scores, sensitivity, above=above)

    # Build a flags list aligned with valid_chunks (default non-anomaly)
    flags = [False] * len(valid_chunks)
    for score, idx in zip(scores, indices):
        if above:
            flags[idx] = score > threshold
        else:
            flags[idx] = score < threshold

    # Print all chunks
    for i, (chunk, flag) in enumerate(zip(valid_chunks, flags)):
        score_val = scores[indices.index(i)] if i in indices else None
        score_str = f"{score_val:.4f}" if score_val is not None else "  N/A "
        marker    = " *** ANOMALY" if flag else ""
        print(f"  Chunk {i + 1:4d}: score = {score_str}{marker}")

    flags    = fill_gaps(flags, max_gap=max_gap)
    periods  = group_anomaly_periods(valid_chunks, flags)

    print(f"\n  --- {label.replace('_', ' ').title()} Anomaly Periods ---")
    if periods:
        for p in periods:
            print(f"  {p}")
    else:
        print("  No anomalies detected.")

    return periods


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def loss_aversion(file_name: str, sensitivity: float = 1.5, max_gap: int = 2) -> dict:
    trades = parse_trades(file_name)
    print(f"[+] Loaded {len(trades)} trades from '{file_name}'")

    # Split into chunks of 10 (mirrors overtrader.py)
    raw_chunks   = [trades[i:i + 10] for i in range(0, len(trades), 10)]
    valid_chunks = [c for c in raw_chunks if len(c) >= 2]
    print(f"[+] Chunks: {len(valid_chunks)} (of size ~10 each)\n")

    results = {}

    # ------------------------------------------------------------------ #
    # 1. Holding losers too long                                          #
    # ------------------------------------------------------------------ #
    scores1, idx1 = [], []
    for i, chunk in enumerate(valid_chunks):
        s = score_holding_losers(chunk)
        if s is not None:
            scores1.append(s)
            idx1.append(i)

    results["holding_losers_too_long"] = detect_behavior(
        label        = "holding_losers_too_long",
        valid_chunks = valid_chunks,
        scores       = scores1,
        indices      = idx1,
        above        = True,      # anomaly = ratio is too HIGH
        sensitivity  = sensitivity,
        max_gap      = max_gap,
    )

    # ------------------------------------------------------------------ #
    # 2. Closing winners too early                                        #
    # ------------------------------------------------------------------ #
    scores2, idx2 = [], []
    for i, chunk in enumerate(valid_chunks):
        s = score_closing_winners_early(chunk)
        if s is not None:
            scores2.append(s)
            idx2.append(i)

    results["closing_winners_early"] = detect_behavior(
        label        = "closing_winners_early",
        valid_chunks = valid_chunks,
        scores       = scores2,
        indices      = idx2,
        above        = False,     # anomaly = duration is too LOW
        sensitivity  = sensitivity,
        max_gap      = max_gap,
    )

    # ------------------------------------------------------------------ #
    # 3. Risk/reward imbalance                                            #
    # ------------------------------------------------------------------ #
    scores3, idx3 = [], []
    for i, chunk in enumerate(valid_chunks):
        s = score_risk_reward(chunk)
        if s is not None:
            scores3.append(s)
            idx3.append(i)

    results["risk_reward_imbalance"] = detect_behavior(
        label        = "risk_reward_imbalance",
        valid_chunks = valid_chunks,
        scores       = scores3,
        indices      = idx3,
        above        = True,      # anomaly = losses dwarf gains
        sensitivity  = sensitivity,
        max_gap      = max_gap,
    )

    # ------------------------------------------------------------------ #
    # 4. Avg loss size > avg win size                                     #
    # ------------------------------------------------------------------ #
    scores4, idx4 = [], []
    for i, chunk in enumerate(valid_chunks):
        s = score_loss_size(chunk)
        if s is not None:
            scores4.append(s)
            idx4.append(i)

    results["loss_size_exceeds_win_size"] = detect_behavior(
        label        = "loss_size_exceeds_win_size",
        valid_chunks = valid_chunks,
        scores       = scores4,
        indices      = idx4,
        above        = True,      # anomaly = loss qty ratio is too HIGH
        sensitivity  = sensitivity,
        max_gap      = max_gap,
    )

    # ------------------------------------------------------------------ #
    # Final summary                                                       #
    # ------------------------------------------------------------------ #
    print(f"\n{'=' * 60}")
    print("  LOSS AVERSION — SUMMARY")
    print(f"{'=' * 60}")
    for behavior, periods in results.items():
        print(f"  {behavior:<35} {len(periods):>4} anomaly period(s)")

    return results


def main():
    file_name = "uploads/surprise_200k_trades.csv"
    loss_aversion(file_name)


if __name__ == "__main__":
    main()
