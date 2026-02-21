"""
revengetrading.py
-----------------
Detects revenge trading behaviour in a chronological trade dataset.

Revenge trading is defined as reactive, emotionally-driven escalation in
position size and/or trading frequency that occurs shortly after one or more
losing trades.

Detection logic
---------------
1. Trigger  – one or more consecutive losing trades (loss streak ≥ 1) OR a
              sharp negative cumulative P/L drop within a lookback window.
2. Escalation (within the next N=3 trades after the trigger):
              – position size > 1.5× rolling-10-trade mean size, OR
              – risk proxy (size × |price_move|) increases > 1.5×.
3. Persistence – escalated behaviour lasts ≥ 2 trades OR inter-trade gap
                 shrinks below 50 % of the rolling baseline frequency.

Usage
-----
    python revengetrading.py --file mixed_trader.csv

Optional flags
    --window        look-ahead trades after trigger (default 3)
    --size-ratio    escalation threshold for position size (default 1.5)
    --freq-ratio    frequency escalation threshold as fraction of baseline (default 0.5)
    --roll-size     rolling window for average size / frequency (default 10)
    --pnl-drop      cumulative P/L drop (absolute) to count as trigger (default 0, uses loss streak only)
"""

import argparse
import glob
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

UPLOADS_DIR = "uploads"
SUMMARIES_DIR = "summaries"
SUMMARY_FILENAME = "revenge_trading_summary.csv"

# ---------------------------------------------------------------------------
# Column mapping
# Allows the script to work with varying column names. Adjust as needed.
# ---------------------------------------------------------------------------
COLUMN_MAP = {
    "timestamp": ["timestamp", "time", "date", "datetime", "trade_time"],
    "trade_id": ["trade_id", "id", "index", "trade_no"],
    "quantity": ["quantity", "position_size", "size", "qty", "vol", "volume"],
    "entry_price": ["entry_price", "entry", "open_price", "open"],
    "exit_price": ["exit_price", "exit", "close_price", "close"],
    "pnl": ["profit_loss", "pnl", "pl", "p_l", "return", "net_pnl"],
    "cumulative_pnl": ["balance", "cumulative_pnl", "cum_pnl", "equity", "cumulative_pl"],
    "direction": ["side", "trade_direction", "direction", "type"],
}


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def resolve_column(df: pd.DataFrame, canonical: str) -> str | None:
    """Return the first matching actual column name for a canonical field name.

    Parameters
    ----------
    df : pd.DataFrame
        The loaded dataframe.
    canonical : str
        The internal field name (key in COLUMN_MAP).

    Returns
    -------
    str | None
        Actual column name found in df, or None if not found.
    """
    candidates = COLUMN_MAP.get(canonical, [canonical])
    for c in candidates:
        if c in df.columns:
            return c
    return None


def load_and_sort(filepath: str) -> tuple[pd.DataFrame, dict[str, str]]:
    """Load the CSV, resolve columns, sort chronologically and return a
    normalised DataFrame alongside a column-name mapping dict.

    Parameters
    ----------
    filepath : str
        Path to the trade CSV file.

    Returns
    -------
    df : pd.DataFrame
        Sorted dataframe with a guaranteed integer ``trade_idx`` column.
    cols : dict
        Mapping of canonical name → actual column name (None if absent).
    """
    df = pd.read_csv(filepath)

    cols = {canon: resolve_column(df, canon) for canon in COLUMN_MAP}

    # Timestamp
    ts_col = cols["timestamp"]
    if ts_col is None:
        raise ValueError("No timestamp-like column found in the dataset.")
    df[ts_col] = pd.to_datetime(df[ts_col])
    df = df.sort_values(ts_col).reset_index(drop=True)

    # Synthetic trade_id if absent
    if cols["trade_id"] is None:
        df["trade_id"] = df.index
        cols["trade_id"] = "trade_id"

    # Synthetic cumulative P/L if absent but PnL is present
    pnl_col = cols["pnl"]
    cum_col = cols["cumulative_pnl"]
    if cum_col is None and pnl_col is not None:
        df["cumulative_pnl"] = df[pnl_col].cumsum()
        cols["cumulative_pnl"] = "cumulative_pnl"

    # Risk proxy: size × |price move|
    qty_col = cols["quantity"]
    ep_col = cols["entry_price"]
    xp_col = cols["exit_price"]
    if qty_col and ep_col and xp_col:
        df["_risk_proxy"] = df[qty_col] * (df[xp_col] - df[ep_col]).abs()
    elif qty_col and pnl_col:
        df["_risk_proxy"] = df[qty_col]  # fallback
    else:
        df["_risk_proxy"] = 1.0  # no sizing info at all

    # Inter-trade gap in seconds
    df["_gap_seconds"] = df[ts_col].diff().dt.total_seconds().fillna(0)

    df["trade_idx"] = df.index
    return df, cols


# ---------------------------------------------------------------------------
# Rolling metric computation
# ---------------------------------------------------------------------------

def compute_rolling_metrics(
    df: pd.DataFrame,
    cols: dict[str, str],
    roll: int = 10,
) -> pd.DataFrame:
    """Attach rolling position-size mean, rolling frequency baseline, loss
    streak length, and cumulative P/L slope to the dataframe.

    Parameters
    ----------
    df : pd.DataFrame
        The normalised trade dataframe.
    cols : dict
        Canonical-to-actual column mapping.
    roll : int
        Window size for rolling calculations (default 10).

    Returns
    -------
    pd.DataFrame
        The same dataframe with new ``_*`` helper columns appended.
    """
    qty_col = cols["quantity"]
    pnl_col = cols["pnl"]

    # Rolling mean position size (exclusive of current row → shift(1))
    if qty_col:
        df["_roll_size_mean"] = (
            df[qty_col].shift(1).rolling(roll, min_periods=1).mean()
        )
        df["_roll_risk_mean"] = (
            df["_risk_proxy"].shift(1).rolling(roll, min_periods=1).mean()
        )
    else:
        df["_roll_size_mean"] = 1.0
        df["_roll_risk_mean"] = 1.0

    # Rolling mean inter-trade gap
    df["_roll_gap_mean"] = (
        df["_gap_seconds"].shift(1).rolling(roll, min_periods=1).mean()
    )

    # Loss flag and loss streak
    if pnl_col:
        df["_is_loss"] = df[pnl_col] < 0
        streaks = []
        streak = 0
        for loss in df["_is_loss"]:
            streak = streak + 1 if loss else 0
            streaks.append(streak)
        df["_loss_streak"] = streaks
    else:
        df["_is_loss"] = False
        df["_loss_streak"] = 0

    # Cumulative P/L slope over rolling window (linear regression slope)
    cum_col = cols["cumulative_pnl"]
    if cum_col:
        slopes = [np.nan] * len(df)
        for i in range(roll, len(df)):
            y = df[cum_col].iloc[i - roll: i].values
            x = np.arange(roll)
            slopes[i] = float(np.polyfit(x, y, 1)[0])
        df["_cum_pnl_slope"] = slopes
    else:
        df["_cum_pnl_slope"] = np.nan

    return df


# ---------------------------------------------------------------------------
# Core detection
# ---------------------------------------------------------------------------

def detect_revenge_windows(
    df: pd.DataFrame,
    cols: dict[str, str],
    window: int = 3,
    size_ratio: float = 1.5,
    freq_ratio: float = 0.5,
    pnl_drop_threshold: float = 0.0,
) -> list[dict]:
    """Scan the dataframe for revenge trading windows.

    A window is opened when a trigger event (consecutive loss OR sharp P/L
    drop) is followed within ``window`` trades by escalated position sizing
    or increased trading frequency, persisting for ≥ 2 trades.

    Parameters
    ----------
    df : pd.DataFrame
        Dataframe with rolling metrics already computed.
    cols : dict
        Canonical-to-actual column mapping.
    window : int
        Number of look-ahead trades after the trigger.
    size_ratio : float
        Minimum ratio of current size vs rolling mean to count as escalation.
    freq_ratio : float
        Maximum fraction of rolling gap mean to count as frequency escalation.
    pnl_drop_threshold : float
        Absolute cumulative P/L drop to count as trigger (0 = disabled).

    Returns
    -------
    list[dict]
        List of detected revenge windows as dictionaries.
    """
    qty_col = cols["quantity"]
    pnl_col = cols["pnl"]
    ts_col = cols["timestamp"]
    tid_col = cols["trade_id"]
    cum_col = cols["cumulative_pnl"]

    episodes = []
    skip_until = -1  # avoid double-counting overlapping windows

    for i, row in df.iterrows():
        if i <= skip_until:
            continue

        # --- Trigger check ---
        triggered = False
        trigger_reason = []

        if row["_loss_streak"] >= 1:
            triggered = True
            trigger_reason.append(f"loss_streak={int(row['_loss_streak'])}")

        if pnl_drop_threshold > 0 and cum_col and not np.isnan(row.get("_cum_pnl_slope", np.nan)):
            if row["_cum_pnl_slope"] < -pnl_drop_threshold:
                triggered = True
                trigger_reason.append(f"pnl_slope={row['_cum_pnl_slope']:.2f}")

        if not triggered:
            continue

        # --- Look-ahead window ---
        lookahead = df.iloc[i + 1: i + 1 + window]
        if lookahead.empty:
            continue

        escalated_indices = []
        escalation_notes = []

        for j, la_row in lookahead.iterrows():
            size_esc = False
            freq_esc = False
            note_parts = []

            # Size escalation
            if qty_col and row["_roll_size_mean"] > 0:
                ratio = la_row[qty_col] / la_row["_roll_size_mean"]
                if ratio >= size_ratio:
                    size_esc = True
                    note_parts.append(f"size_ratio={ratio:.2f}x")

            # Risk proxy escalation (backup when size alone is ambiguous)
            if la_row["_roll_risk_mean"] > 0:
                risk_ratio = la_row["_risk_proxy"] / la_row["_roll_risk_mean"]
                if risk_ratio >= size_ratio and not size_esc:
                    size_esc = True
                    note_parts.append(f"risk_ratio={risk_ratio:.2f}x")

            # Frequency escalation
            if la_row["_roll_gap_mean"] > 0:
                gap_frac = la_row["_gap_seconds"] / la_row["_roll_gap_mean"]
                if gap_frac <= freq_ratio:
                    freq_esc = True
                    note_parts.append(f"freq_gap={gap_frac:.2f}x_baseline")

            if size_esc or freq_esc:
                escalated_indices.append(j)
                escalation_notes.append("; ".join(note_parts))

        # --- Persistence check: ≥ 2 escalated trades ---
        if len(escalated_indices) < 2:
            continue

        # Build episode record
        esc_slice = df.loc[escalated_indices]
        start_time = esc_slice[ts_col].iloc[0]
        end_time = esc_slice[ts_col].iloc[-1]
        trigger_trade_id = row[tid_col]
        loss_streak = int(row["_loss_streak"])

        avg_size_before = row["_roll_size_mean"] if qty_col else np.nan
        avg_size_during = esc_slice[qty_col].mean() if qty_col else np.nan
        escalation_ratio = (
            avg_size_during / avg_size_before
            if avg_size_before and avg_size_before > 0
            else np.nan
        )

        notes_combined = (
            f"Trigger: {', '.join(trigger_reason)}. "
            f"Escalation details: {' | '.join(escalation_notes[:3])}"
        )

        episodes.append(
            {
                "start_time": start_time,
                "end_time": end_time,
                "triggering_loss_trade_id": trigger_trade_id,
                "loss_streak_length": loss_streak,
                "avg_size_before": round(avg_size_before, 4) if not np.isnan(avg_size_before) else np.nan,
                "avg_size_during": round(avg_size_during, 4) if not np.isnan(avg_size_during) else np.nan,
                "escalation_ratio": round(escalation_ratio, 4) if not np.isnan(escalation_ratio) else np.nan,
                "notes": notes_combined,
            }
        )

        # Skip forward past this episode to avoid duplicate detection
        skip_until = escalated_indices[-1]

    return episodes


# ---------------------------------------------------------------------------
# Merge overlapping windows
# ---------------------------------------------------------------------------

def merge_overlapping_episodes(episodes: list[dict]) -> list[dict]:
    """Merge revenge trading episodes whose time ranges overlap or are
    contiguous, producing a single continuous event record.

    Parameters
    ----------
    episodes : list[dict]
        Raw detected episodes (may overlap).

    Returns
    -------
    list[dict]
        De-overlapped, merged episode list.
    """
    if not episodes:
        return []

    # Sort by start time
    episodes = sorted(episodes, key=lambda e: e["start_time"])
    merged = [episodes[0].copy()]

    for ep in episodes[1:]:
        last = merged[-1]
        if ep["start_time"] <= last["end_time"]:
            # Extend the window
            last["end_time"] = max(last["end_time"], ep["end_time"])
            last["loss_streak_length"] = max(
                last["loss_streak_length"], ep["loss_streak_length"]
            )
            if not np.isnan(ep.get("escalation_ratio", np.nan)) and (
                np.isnan(last.get("escalation_ratio", np.nan))
                or ep["escalation_ratio"] > last["escalation_ratio"]
            ):
                last["escalation_ratio"] = ep["escalation_ratio"]
                last["avg_size_during"] = ep["avg_size_during"]
            last["notes"] += " [merged with overlapping window]"
        else:
            merged.append(ep.copy())

    return merged


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def build_output_table(episodes: list[dict]) -> pd.DataFrame:
    """Convert the list of episode dicts into a structured DataFrame.

    Parameters
    ----------
    episodes : list[dict]
        Merged episode records.

    Returns
    -------
    pd.DataFrame
        Formatted output table.
    """
    cols = ["start_time", "end_time", "loss_streak_length"]
    if not episodes:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(episodes)[cols]


def print_summary(table: pd.DataFrame) -> None:
    """Print a human-readable console summary of all detected revenge trading
    episodes.

    Parameters
    ----------
    table : pd.DataFrame
        Output table from ``build_output_table``.
    """
    sep = "=" * 72
    print(sep)
    print("  REVENGE TRADING DETECTION REPORT")
    print(sep)

    total = len(table)
    print(f"\n  Total revenge trading episodes detected : {total}")

    if total == 0:
        print("  No revenge trading behaviour detected.\n")
        print(sep)
        return

    durations = (
        pd.to_datetime(table["end_time"]) - pd.to_datetime(table["start_time"])
    ).dt.total_seconds() / 60.0  # minutes

    print(f"  Average episode duration                : {durations.mean():.1f} min")
    print(f"  Longest episode duration                : {durations.max():.1f} min")
    print(f"  Shortest episode duration               : {durations.min():.1f} min")
    print(f"\n  Max loss streak within any episode      : {table['loss_streak_length'].max()}")

    print(f"\n{sep}")
    print("  EPISODE TABLE")
    print(sep)

    pd.set_option("display.max_colwidth", 60)
    pd.set_option("display.width", 120)
    print(table.to_string(index=True))
    print(sep)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect revenge trading behaviour in a trade history CSV."
    )
    parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="Path to the trade CSV file (default: first CSV found in uploads/)",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=3,
        help="Look-ahead trades after trigger event (default: 3)",
    )
    parser.add_argument(
        "--size-ratio",
        type=float,
        default=1.5,
        help="Position size escalation threshold vs rolling mean (default: 1.5)",
    )
    parser.add_argument(
        "--freq-ratio",
        type=float,
        default=0.5,
        help="Frequency escalation: max fraction of baseline gap (default: 0.5)",
    )
    parser.add_argument(
        "--roll-size",
        type=int,
        default=10,
        help="Rolling window for average size / frequency (default: 10)",
    )
    parser.add_argument(
        "--pnl-drop",
        type=float,
        default=0.0,
        help="Abs cumulative P/L slope drop to use as trigger (default: 0 = disabled)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Optional path to save the output table as CSV",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.file is None:
        csv_files = glob.glob(os.path.join(UPLOADS_DIR, "surprise_200k_trades.csv"))
        if not csv_files:
            print(f"[ERROR] No CSV files found in '{UPLOADS_DIR}/' directory.", file=sys.stderr)
            sys.exit(1)
        filepath = Path(csv_files[0])
    else:
        filepath = Path(args.file)

    if not filepath.exists():
        print(f"[ERROR] File not found: {filepath}", file=sys.stderr)
        sys.exit(1)

    print(f"[+] Loading dataset: {filepath}")
    df, cols = load_and_sort(str(filepath))
    print(f"    Rows loaded: {len(df)}")
    print(f"    Columns resolved: { {k: v for k, v in cols.items() if v} }")

    print("[+] Computing rolling metrics …")
    df = compute_rolling_metrics(df, cols, roll=args.roll_size)

    print("[+] Detecting revenge trading windows …")
    raw_episodes = detect_revenge_windows(
        df,
        cols,
        window=args.window,
        size_ratio=args.size_ratio,
        freq_ratio=args.freq_ratio,
        pnl_drop_threshold=args.pnl_drop,
    )

    print("[+] Merging overlapping detections …")
    merged = merge_overlapping_episodes(raw_episodes)

    table = build_output_table(merged)

    print_summary(table)

    summaries_path = Path(SUMMARIES_DIR)
    summaries_path.mkdir(exist_ok=True)
    out_path = summaries_path / SUMMARY_FILENAME
    table.to_csv(out_path, index=False)
    print(f"\n[+] Summary saved to: {out_path}")


if __name__ == "__main__":
    main()