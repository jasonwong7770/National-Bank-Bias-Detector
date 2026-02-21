'''
CALL: overtrader(file_name, sensitivity=1.5, max_gap=2, reactive_window_s=300)

Returns a dict of anomaly periods per behavior type:
{
  "time_clustering":   ["2025-03-01 09:30:00;2025-03-01 10:00:00", ...],
  "reactive_trading":  [...]
}
Each entry = "start_timestamp;end_timestamp" of an anomaly window.
'''

from dataclasses import dataclass


@dataclass
class Timestamp:
    year: int
    month: int
    day: int
    hour: int
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


# ── helpers ────────────────────────────────────────────────────────────────────

def chunk_average(chunk_timestamps):
    gaps = []
    for i in range(1, len(chunk_timestamps)):
        diff = chunk_timestamps[i].to_seconds() - chunk_timestamps[i - 1].to_seconds()
        gaps.append(diff)
    avg = sum(gaps) / len(gaps)
    return {
        "avg_seconds": avg,
        "formatted":   f"{int(avg//3600):02}:{int((avg%3600)//60):02}:{int(avg%60):02}"
    }


def robust_threshold(values, sensitivity, low=True):
    s      = sorted(values)
    n      = len(s)
    median = s[n // 2] if n % 2 != 0 else (s[n//2 - 1] + s[n//2]) / 2
    devs   = sorted(abs(v - median) for v in values)
    mad    = devs[n // 2] if n % 2 != 0 else (devs[n//2 - 1] + devs[n//2]) / 2
    scaled = sensitivity * 1.4826 * mad
    return (median - scaled) if low else (median + scaled)


def fill_gaps(flags, max_gap):
    filled = flags[:]
    n = len(filled)
    i = 0
    while i < n:
        if filled[i]:
            j = i
            while j < n and filled[j]:
                j += 1
            k, gap = j, 0
            while k < n and not filled[k] and gap < max_gap:
                gap += 1
                k   += 1
            if k < n and filled[k]:
                for g in range(j, k):
                    filled[g] = True
            i = j
        else:
            i += 1
    return filled


def periods_from_flags(chunks, flags):
    def get_ts(item):
        return item.timestamp.to_string() if hasattr(item, "timestamp") else item.to_string()

    results       = []
    anomaly_start = None
    anomaly_end   = None
    for chunk, flag in zip(chunks, flags):
        if flag:
            if anomaly_start is None:
                anomaly_start = chunk[0]
            anomaly_end = chunk[-1]
        else:
            if anomaly_start is not None:
                results.append(f"{get_ts(anomaly_start)};{get_ts(anomaly_end)}")
                anomaly_start = None
                anomaly_end   = None
    if anomaly_start is not None:
        results.append(f"{get_ts(anomaly_start)};{get_ts(anomaly_end)}")
    return results


# ── detectors ─────────────────────────────────────────────────────────────────

def detect_time_clustering(trades, sensitivity, max_gap):
    """Flag windows where trades arrive unusually fast."""
    timestamps   = [t.timestamp for t in trades]
    raw_chunks   = [timestamps[i:i+10] for i in range(0, len(timestamps), 10)]
    valid_chunks = [c for c in raw_chunks if len(c) >= 2]
    trade_chunks = [trades[i*10 : i*10 + len(c)]
                    for i, c in enumerate(valid_chunks)]

    averages  = [chunk_average(c) for c in valid_chunks]
    threshold = robust_threshold([r["avg_seconds"] for r in averages],
                                 sensitivity, low=True)
    print(f"[time_clustering]  threshold: below {threshold:.1f}s")

    flags = fill_gaps([r["avg_seconds"] < threshold for r in averages], max_gap)

    for idx, (result, flag) in enumerate(zip(averages, flags)):
        label = " *** ANOMALY" if flag else ""
        print(f"  Chunk {idx+1}: avg = {result['formatted']} ({result['avg_seconds']:.1f}s){label}")

    return periods_from_flags(trade_chunks, flags)


def detect_reactive_trading(trades, sensitivity, max_gap, reactive_window_s):
    """
    Flag windows where the trader re-enters the market quickly after a
    large P&L event (win or loss).

    Logic:
    1. Identify 'trigger' trades whose abs(profit_loss) is unusually large
       (detected dynamically via median+MAD — no hardcoded threshold).
    2. For every trade that follows a trigger within `reactive_window_s`
       seconds, mark it as reactive.
    3. Chunk those reactive flags and flag windows with an unusually high
       reactive rate.
    """
    # Step 1 — find large P&L events dynamically
    pl_values = [abs(t.profit_loss) for t in trades]
    pl_thresh = robust_threshold(pl_values, sensitivity, low=False)
    print(f"[reactive_trading] large P&L threshold: above {pl_thresh:.2f}")
    print(f"[reactive_trading] re-entry window: within {reactive_window_s}s of trigger")

    # Step 2 — mark reactive trades
    reactive = [False] * len(trades)
    for i in range(1, len(trades)):
        prev = trades[i - 1]
        curr = trades[i]
        if abs(prev.profit_loss) > pl_thresh:
            time_gap = curr.timestamp.to_seconds() - prev.timestamp.to_seconds()
            if time_gap <= reactive_window_s:
                reactive[i] = True

    # Step 3 — chunk and measure reactive rate per window
    raw_chunks = [trades[i:i+10] for i in range(0, len(trades), 10)]
    chunks     = [c for c in raw_chunks if len(c) >= 2]

    reactive_rates = []
    for idx, chunk in enumerate(chunks):
        start = idx * 10
        rate  = sum(reactive[start : start + len(chunk)]) / len(chunk)
        reactive_rates.append(rate)

    threshold = robust_threshold(reactive_rates, sensitivity, low=False)
    print(f"[reactive_trading] chunk reactive-rate threshold: above {threshold:.2f}")

    flags = fill_gaps([r > threshold for r in reactive_rates], max_gap)

    for idx, (rate, flag) in enumerate(zip(reactive_rates, flags)):
        if flag:
            print(f"  Chunk {idx+1}: reactive rate = {rate:.2f} *** ANOMALY")

    return periods_from_flags(chunks, flags)


# ── entry point ────────────────────────────────────────────────────────────────

def overtrader(file_name, sensitivity=1.5, max_gap=2, reactive_window_s=300):
    trades = []

    with open(file_name, "r") as file:
        next(file)
        for line in file:
            parts = line.strip().split(",")
            if len(parts) < 8:
                continue
            raw = parts[0].strip()
            if " " not in raw:
                continue
            date_part, time_part = raw.split(" ")
            y, mo, d = date_part.split("-")
            h, mi, s = time_part.split(":")
            ts = Timestamp(int(y), int(mo), int(d), int(h), int(mi), int(s))
            trades.append(Trade(
                timestamp   = ts,
                asset       = parts[1].strip(),
                side        = parts[2].strip(),
                quantity    = float(parts[3]),
                entry_price = float(parts[4]),
                exit_price  = float(parts[5]),
                profit_loss = float(parts[6]),
                balance     = float(parts[7])
            ))

    print(f"\nLoaded {len(trades)} trades from {file_name}\n")

    results = {
        "time_clustering":  detect_time_clustering(trades, sensitivity, max_gap),
        "reactive_trading": detect_reactive_trading(trades, sensitivity, max_gap, reactive_window_s),
    }

    print("\n--- Overtrading Periods ---")
    for behavior, periods in results.items():
        print(f"\n{behavior} ({len(periods)} period(s)):")
        for p in periods:
            print(f"  {p}")

    return results

overtrader("uploads/mixed_trader.csv")

def main():
    file_name = "uploads/mixed_trader.csv"
    overtrader(file_name)

if __name__ == "__main__":
    main()