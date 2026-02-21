import pandas as pd

from overtrader     import overtrader
from loss_aversion  import loss_aversion, parse_trades
from revenge_trader import revenge_trader
from fomo_trader    import fomo_trader

CHUNK_SIZE = 10


def run_all(file_name: str, sensitivity: float = 1.5, max_gap: int = 2) -> dict:
    _, ot_chunk_lines, ot_results = overtrader(file_name, sensitivity, max_gap)
    la_results, la_chunk_lines = loss_aversion(file_name, sensitivity, max_gap)
    rt_results, rt_chunk_lines = revenge_trader(file_name, sensitivity, max_gap)
    fomo_periods, ft_chunk_lines = fomo_trader(file_name, sensitivity, max_gap)

    # Load trade-level balance data for the equity curve
    df = pd.read_csv(file_name)
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    # Map sub-behavior labels to human-readable descriptions
    REASON_LABELS = {
        "time_clustering":            "Trades clustered too closely in time",
        "reactive_trading":           "Spike in trading after recent activity",
        "holding_losers_too_long":    "Holding losing positions too long",
        "closing_winners_early":      "Closing winning positions too early",
        "risk_reward_imbalance":      "Average losses far exceed average gains",
        "loss_size_exceeds_win_size": "Loss sizes consistently larger than wins",
        "size_increase_after_loss":   "Position size increased after a loss",
        "escalation_after_loss_streak":"Risk escalation after consecutive losses",
    }

    def _parse_range(s):
        """Parse 'start;end' timestamp string into (start, end) datetimes."""
        parts = s.split(";")
        return pd.Timestamp(parts[0].strip()), pd.Timestamp(parts[1].strip())

    def _overlaps(chunk_range_str, period_str):
        """Check if a chunk time range overlaps with a detail period."""
        c_start, c_end = _parse_range(chunk_range_str)
        p_start, p_end = _parse_range(period_str)
        return c_start <= p_end and p_start <= c_end

    def _extract_periods(val):
        """Extract list of period strings from a detail value (may be list or tuple)."""
        if isinstance(val, tuple):
            return val[0] if isinstance(val[0], list) else list(val)
        if isinstance(val, list):
            return val
        return []

    def _get_reasons(chunk_range_str, ot_flag, la_flag, rt_flag, ft_flag):
        """Find which specific sub-behaviors triggered each bias for this chunk."""
        reasons = []

        if ot_flag:
            for key in ("time_clustering", "reactive_trading"):
                periods = _extract_periods(ot_results.get(key, []))
                for period in periods:
                    if isinstance(period, str) and _overlaps(chunk_range_str, period):
                        reasons.append(REASON_LABELS[key])
                        break

        if la_flag:
            for key in ("holding_losers_too_long", "closing_winners_early",
                        "risk_reward_imbalance", "loss_size_exceeds_win_size"):
                periods = _extract_periods(la_results.get(key, []))
                for period in periods:
                    if isinstance(period, str) and _overlaps(chunk_range_str, period):
                        reasons.append(REASON_LABELS[key])
                        break

        if rt_flag:
            for key in ("size_increase_after_loss", "escalation_after_loss_streak"):
                periods = _extract_periods(rt_results.get(key, []))
                for period in periods:
                    if isinstance(period, str) and _overlaps(chunk_range_str, period):
                        reasons.append(REASON_LABELS[key])
                        break

        if ft_flag:
            reasons.append("Excessive buying after price surge (FOMO)")

        return reasons

    chunks = []
    for i in range(len(ot_chunk_lines)):
        time_range, ot_flag = ot_chunk_lines[i]
        _, la_flag = la_chunk_lines[i]
        _, rt_flag = rt_chunk_lines[i]
        _, ft_flag = ft_chunk_lines[i]

        biases = []
        if ot_flag:
            biases.append("Overtrading")
        if la_flag:
            biases.append("Loss Aversion")
        if rt_flag:
            biases.append("Revenge Trading")
        if ft_flag:
            biases.append("FOMO")
        if not biases:
            biases.append("Calm")

        reasons = _get_reasons(str(time_range), ot_flag, la_flag, rt_flag, ft_flag)

        chunks.append({
            "chunk": i,
            "time_range": str(time_range),
            "overtrading": ot_flag,
            "loss_aversion": la_flag,
            "revenge_trading": rt_flag,
            "fomo": ft_flag,
            "biases": biases,
            "reasons": reasons,
        })

    total = len(chunks)
    bias_counts = {
        "Overtrading": sum(1 for c in chunks if c["overtrading"]),
        "Loss Aversion": sum(1 for c in chunks if c["loss_aversion"]),
        "Revenge Trading": sum(1 for c in chunks if c["revenge_trading"]),
        "FOMO": sum(1 for c in chunks if c["fomo"]),
        "Calm": sum(1 for c in chunks if c["biases"] == ["Calm"]),
    }

    # Build per-trade balance curve with chunk/bias info
    balance_curve = []
    for idx, row in df.iterrows():
        chunk_idx = min(idx // CHUNK_SIZE, total - 1)
        chunk_info = chunks[chunk_idx]
        balance_curve.append({
            "trade": int(idx),
            "timestamp": str(row["timestamp"]),
            "balance": round(float(row["balance"]), 2),
            "chunk": chunk_idx,
            "primary_bias": chunk_info["biases"][0],
        })

    return {
        "total_chunks": total,
        "bias_counts": bias_counts,
        "chunks": chunks,
        "balance_curve": balance_curve,
        "details": {
            "overtrading": ot_results,
            "loss_aversion": la_results,
            "revenge_trading": rt_results,
            "fomo": fomo_periods,
        },
    }


def main():
    file_name = "uploads/mixed_trader.csv"
    result = run_all(file_name)
    for c in result["chunks"]:
        print(f"Chunk {c['chunk']:>3} | {' | '.join(c['biases'])}")


if __name__ == "__main__":
    main()
