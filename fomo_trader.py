'''
SIMPLY CALL THE FUNCTION fomo_trader(file_name, sensitivity=1.5, max_gap=2)
IT SHOULD RETURN AN ARRAY OF ANOMALIES LIKE THIS
ex: 2025-03-02 23:54:50;2025-03-03 00:15:50
'''


from dataclasses import dataclass


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
    timestamp:   Timestamp
    asset:       str
    side:        str
    quantity:    float
    entry_price: float
    exit_price:  float
    profit_loss: float
    balance:     float


def chunk_fomo_score(chunk, prior_chunk=None):
    """
    Compute the average FOMO score across all trades in a chunk.

    Three signals are averaged per trade:
      1. Late re-entry   — chasing price on the same asset already traded
      2. Burst frequency — how densely packed trades are in a 120s window
      3. Qty escalation  — position size growing vs the prior chunk's average

    Returns a dict with "avg_score" and "formatted" keys (mirrors chunk_average).
    """
    # Pre-compute prior chunk average quantity for signal 3
    if prior_chunk:
        prior_avg_qty = sum(t.quantity for t in prior_chunk) / len(prior_chunk)
    else:
        prior_avg_qty = None

    trade_scores = []

    for i, trade in enumerate(chunk):

        # ------------------------------------------------------------------
        # Signal 1 — Late re-entry score
        # Scan backwards in the same chunk for the most recent trade on the
        # same asset.  If this trade's entry chased price (BUY higher / SELL
        # lower than the prior exit), score the percentage gap.
        # ------------------------------------------------------------------
        late_reentry_score = 0.0
        for j in range(i - 1, -1, -1):
            prior = chunk[j]
            if prior.asset == trade.asset:
                if trade.side == "BUY" and trade.entry_price > prior.exit_price:
                    late_reentry_score = (
                        abs(trade.entry_price - prior.exit_price)
                        / prior.exit_price * 100
                    )
                elif trade.side == "SELL" and trade.entry_price < prior.exit_price:
                    late_reentry_score = (
                        abs(trade.entry_price - prior.exit_price)
                        / prior.exit_price * 100
                    )
                break   # only the most recent prior trade on the same asset

        # ------------------------------------------------------------------
        # Signal 2 — Burst frequency score
        # Count how many other trades in the chunk fall within a ±120s window
        # around this trade, then scale to 0-100.
        # ------------------------------------------------------------------
        trade_ts   = trade.timestamp.to_seconds()
        in_window  = sum(
            1 for t in chunk
            if abs(t.timestamp.to_seconds() - trade_ts) <= 120
        )
        burst_score = (in_window / 10) * 100

        # ------------------------------------------------------------------
        # Signal 3 — Quantity escalation score
        # How much larger is this trade's quantity vs the prior chunk mean?
        # Zero if there is no prior chunk or quantity did not increase.
        # ------------------------------------------------------------------
        if prior_avg_qty is not None and prior_avg_qty > 0:
            qty_escalation_score = max(
                0.0,
                (trade.quantity - prior_avg_qty) / prior_avg_qty * 100
            )
        else:
            qty_escalation_score = 0.0

        per_trade_score = (late_reentry_score + burst_score + qty_escalation_score) / 3
        trade_scores.append(per_trade_score)

    avg_score = sum(trade_scores) / len(trade_scores)

    # Format avg_score as HH:MM:SS-style string so the print output stays
    # consistent with overtrader.py's "formatted" field convention.
    int_score  = int(avg_score)
    frac_score = avg_score - int_score
    formatted  = f"{int_score:06.2f}"          # e.g. "042.37"

    return {
        "avg_score": avg_score,
        "formatted": f"{avg_score:.2f}"
    }


def calculate_threshold(averages, sensitivity=1.5):
    values = [r["avg_score"] for r in averages]

    # Median is robust — unaffected by extreme FOMO outlier chunks
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    median = (sorted_vals[n // 2] if n % 2 != 0
              else (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2)

    # MAD = median of absolute deviations from the median
    deviations = sorted([abs(v - median) for v in values])
    n = len(deviations)
    mad = (deviations[n // 2] if n % 2 != 0
           else (deviations[n // 2 - 1] + deviations[n // 2]) / 2)

    # Scale factor 1.4826 makes MAD comparable to std dev for normal distributions
    # FOMO anomalies are ABOVE the threshold (inverse of overtrader's below-check)
    threshold = median + sensitivity * (1.4826 * mad)

    print(f"Median: {median:.2f} | MAD: {mad:.2f} | Anomaly threshold: above {threshold:.2f}\n")
    return threshold


def fill_gaps(is_anomaly_flags, max_gap=2):
    """
    If two anomaly regions are separated by `max_gap` or fewer normal chunks,
    treat those normal chunks as part of the anomaly (bridge the gap).
    """
    filled = is_anomaly_flags[:]
    n = len(filled)

    i = 0
    while i < n:
        if filled[i]:                        # found start of an anomaly region
            # find where this anomaly ends
            j = i
            while j < n and filled[j]:
                j += 1
            # j is now the first non-anomaly after the region
            # look ahead for the next anomaly start within max_gap
            gap = 0
            k = j
            while k < n and not filled[k] and gap < max_gap:
                gap += 1
                k  += 1
            if k < n and filled[k]:          # there IS another anomaly within the gap
                for g in range(j, k):        # fill the gap chunks as anomaly
                    filled[g] = True
            i = j                            # continue scanning from end of this region
        else:
            i += 1

    return filled


def fomo_trader(file_name, sensitivity=1.5, max_gap=2):
    trades = []

    with open(file_name, "r") as file:
        next(file)                           # skip header
        for line in file:
            parts = line.strip().split(",")
            if len(parts) < 8:
                continue

            raw = parts[0].strip()
            if " " not in raw:
                continue

            date_part, time_part = raw.split(" ")
            year, month, day     = date_part.split("-")
            hour, minute, second = time_part.split(":")

            timestamp = Timestamp(
                year=int(year), month=int(month), day=int(day),
                hour=int(hour), minute=int(minute), second=int(second)
            )

            try:
                trade = Trade(
                    timestamp   = timestamp,
                    asset       = parts[1].strip(),
                    side        = parts[2].strip(),
                    quantity    = float(parts[3].strip()),
                    entry_price = float(parts[4].strip()),
                    exit_price  = float(parts[5].strip()),
                    profit_loss = float(parts[6].strip()),
                    balance     = float(parts[7].strip()),
                )
            except ValueError:
                continue

            trades.append(trade)

    # Split into chunks of 10
    chunks = [trades[i:i + 10] for i in range(0, len(trades), 10)]

    # First pass — compute all chunk FOMO scores, threading prior chunk context
    averages     = []
    valid_chunks = []
    prior_chunk  = None

    for chunk in chunks:
        if len(chunk) < 2:
            continue
        averages.append(chunk_fomo_score(chunk, prior_chunk=prior_chunk))
        valid_chunks.append(chunk)
        prior_chunk = chunk

    # Dynamically determine anomaly threshold
    threshold = calculate_threshold(averages, sensitivity)

    # Second pass — flag each chunk where score is ABOVE threshold
    is_anomaly = [r["avg_score"] > threshold for r in averages]

    # Third pass — fill small gaps so nearby anomaly regions merge
    is_anomaly = fill_gaps(is_anomaly, max_gap=max_gap)

    # Print all chunks
    for idx, (chunk, result, anomaly) in enumerate(zip(valid_chunks, averages, is_anomaly)):
        flag = " *** ANOMALY" if anomaly else ""
        print(f"Chunk {idx + 1}: avg_score = {result['formatted']}{flag}")

    # Final pass — group consecutive anomaly chunks into periods
    fomo_periods  = []
    anomaly_start = None
    anomaly_end   = None

    for chunk, anomaly in zip(valid_chunks, is_anomaly):
        if anomaly:
            if anomaly_start is None:
                anomaly_start = chunk[0].timestamp
            anomaly_end = chunk[-1].timestamp
        else:
            if anomaly_start is not None:
                fomo_periods.append(f"{anomaly_start.to_string()};{anomaly_end.to_string()}")
                anomaly_start = None
                anomaly_end   = None

    if anomaly_start is not None:
        fomo_periods.append(f"{anomaly_start.to_string()};{anomaly_end.to_string()}")

    print("\n--- FOMO Periods ---")
    for period in fomo_periods:
        print(period)

    return fomo_periods


def main():
    file_name = "uploads/mixed_trader.csv"
    fomo_trader(file_name)


if __name__ == "__main__":
    main()
