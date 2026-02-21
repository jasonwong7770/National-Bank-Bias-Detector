from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


WINDOW_TRADES = 20
TIME_AGG_FREQ = "60min"
EPS = 1e-9

DATASET_PATHS = {
    "calm": ["./trading_datasets/calm_trader.csv"],
    "loss_averse": ["./trading_datasets/loss_averse_trader.csv"],
    "overtrader": ["./trading_datasets/overtrader.csv"],
    "revenge": ["./trading_datasets/revenge_trader.csv"],
    "mixed": ["./trading_datasets/mixed_trader.csv", "./mixed_trader.csv"],
}

FEATURE_COLUMNS = [
    "time_diff_s",
    "trade_rate_per_min",
    "trades_last_15m",
    "trades_last_60m",
    "loss_streak",
    "loss_win_ratio_20",
    "hold_asymmetry_20",
    "size_after_loss_ratio_20",
    "notional_after_loss_ratio_20",
    "qty_volatility_20",
    "pnl_volatility_20",
    "tail_loss_share_50",
]

ARCHETYPE_TRADERS = ["calm", "loss_averse", "overtrader", "revenge"]


def resolve_existing_path(candidates: list[str]) -> Path:
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return path
    raise FileNotFoundError(f"Could not find any of these files: {candidates}")


def compute_loss_streak(series: pd.Series) -> pd.Series:
    streaks = []
    streak = 0
    for pnl in series:
        streak = streak + 1 if pnl < 0 else 0
        streaks.append(streak)
    return pd.Series(streaks, index=series.index, dtype=float)


def tail_loss_share(values: np.ndarray) -> float:
    losses = values[values < 0]
    if losses.size < 5:
        return 0.0
    count_worst = max(1, int(np.ceil(losses.size * 0.10)))
    worst_losses = np.sort(losses)[:count_worst]
    return float(np.abs(worst_losses.sum()) / (np.abs(losses.sum()) + EPS))


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy().sort_values("timestamp").reset_index(drop=True)
    out["timestamp"] = pd.to_datetime(out["timestamp"])

    out["is_win"] = (out["profit_loss"] > 0).astype(int)
    out["price_move_pct"] = (
        (out["exit_price"] - out["entry_price"]).abs() / (out["entry_price"].abs() + EPS) * 100
    )
    out["notional"] = out["quantity"] * out["entry_price"]

    out["time_diff_s"] = out["timestamp"].diff().dt.total_seconds()
    fallback_gap = out["time_diff_s"].dropna().median()
    if pd.isna(fallback_gap):
        fallback_gap = 60.0
    out["time_diff_s"] = out["time_diff_s"].fillna(fallback_gap).clip(lower=1.0)
    out["trade_rate_per_min"] = 60.0 / out["time_diff_s"]

    out["prev_pl"] = out["profit_loss"].shift(1).fillna(0.0)
    out["loss_streak"] = compute_loss_streak(out["profit_loss"])

    roll_win = out["profit_loss"].where(out["is_win"] == 1).rolling(WINDOW_TRADES, min_periods=1).mean()
    roll_loss = (
        out["profit_loss"].where(out["is_win"] == 0).abs().rolling(WINDOW_TRADES, min_periods=1).mean()
    )
    out["loss_win_ratio_20"] = roll_loss / (roll_win.abs() + EPS)
    out["loss_win_ratio_20"] = out["loss_win_ratio_20"].replace([np.inf, -np.inf], np.nan).fillna(1.0)

    win_move = (
        out["price_move_pct"].where(out["is_win"] == 1).rolling(WINDOW_TRADES, min_periods=1).mean()
    )
    loss_move = (
        out["price_move_pct"].where(out["is_win"] == 0).rolling(WINDOW_TRADES, min_periods=1).mean()
    )
    out["hold_asymmetry_20"] = loss_move / (win_move + EPS)
    out["hold_asymmetry_20"] = (
        out["hold_asymmetry_20"].replace([np.inf, -np.inf], np.nan).fillna(1.0)
    )

    qty_after_loss = (
        out["quantity"].where(out["prev_pl"] < 0).rolling(WINDOW_TRADES, min_periods=1).mean()
    )
    qty_after_win = (
        out["quantity"].where(out["prev_pl"] > 0).rolling(WINDOW_TRADES, min_periods=1).mean()
    )
    out["size_after_loss_ratio_20"] = qty_after_loss / (qty_after_win + EPS)
    out["size_after_loss_ratio_20"] = (
        out["size_after_loss_ratio_20"].replace([np.inf, -np.inf], np.nan).fillna(1.0)
    )

    notional_after_loss = (
        out["notional"].where(out["prev_pl"] < 0).rolling(WINDOW_TRADES, min_periods=1).mean()
    )
    notional_after_win = (
        out["notional"].where(out["prev_pl"] > 0).rolling(WINDOW_TRADES, min_periods=1).mean()
    )
    out["notional_after_loss_ratio_20"] = notional_after_loss / (notional_after_win + EPS)
    out["notional_after_loss_ratio_20"] = (
        out["notional_after_loss_ratio_20"].replace([np.inf, -np.inf], np.nan).fillna(1.0)
    )

    roll_qty_mean = out["quantity"].rolling(WINDOW_TRADES, min_periods=1).mean()
    roll_qty_std = out["quantity"].rolling(WINDOW_TRADES, min_periods=1).std().fillna(0.0)
    out["qty_volatility_20"] = roll_qty_std / (roll_qty_mean.abs() + EPS)

    roll_pl_mean = out["profit_loss"].rolling(WINDOW_TRADES, min_periods=1).mean()
    roll_pl_std = out["profit_loss"].rolling(WINDOW_TRADES, min_periods=1).std().fillna(0.0)
    out["pnl_volatility_20"] = roll_pl_std / (roll_pl_mean.abs() + EPS)

    out["tail_loss_share_50"] = (
        out["profit_loss"].rolling(50, min_periods=5).apply(tail_loss_share, raw=True).fillna(0.0)
    )

    out = out.set_index("timestamp")
    trade_counter = pd.Series(1.0, index=out.index)
    out["trades_last_15m"] = trade_counter.rolling("15min").sum().to_numpy()
    out["trades_last_60m"] = trade_counter.rolling("60min").sum().to_numpy()
    out = out.reset_index()

    return out


def load_all_datasets() -> dict[str, pd.DataFrame]:
    datasets = {}
    for trader_name, candidate_paths in DATASET_PATHS.items():
        csv_path = resolve_existing_path(candidate_paths)
        df = pd.read_csv(csv_path)
        datasets[trader_name] = df
    return datasets


def aggregate_features_over_time(features_df: pd.DataFrame, freq: str = TIME_AGG_FREQ) -> pd.DataFrame:
    parts = []
    for trader_name, trader_df in features_df.groupby("trader", sort=False):
        block = (
            trader_df.set_index("timestamp")[FEATURE_COLUMNS]
            .resample(freq)
            .mean()
            .reset_index()
            .assign(trader=trader_name)
        )
        parts.append(block)
    return pd.concat(parts, ignore_index=True)


def print_feature_comparison(hourly_df: pd.DataFrame) -> None:
    features_to_show = [
        "trade_rate_per_min",
        "trades_last_15m",
        "loss_win_ratio_20",
        "hold_asymmetry_20",
        "size_after_loss_ratio_20",
        "loss_streak",
        "qty_volatility_20",
    ]

    print("\n=== Absolute-Time Comparison (overlap only, no NaN) ===")
    for feature in features_to_show:
        pivot = hourly_df.pivot(index="timestamp", columns="trader", values=feature).sort_index()
        overlap = pivot.dropna(how="any")
        if overlap.empty:
            print(f"\n=== {feature} ===")
            print("No timestamps where all traders overlap.")
            continue
        print(f"\n=== {feature} (last 8 overlapping hourly buckets) ===")
        print(overlap.tail(8).round(3).to_string())

    print("\n=== Relative-Time Comparison (from each trader start, no NaN) ===")
    relative = hourly_df.copy()
    relative["relative_hour"] = relative.groupby("trader")["timestamp"].transform(
        lambda s: ((s - s.min()).dt.total_seconds() // 3600).astype(int)
    )

    for feature in features_to_show:
        rel_pivot = (
            relative.pivot_table(
                index="relative_hour",
                columns="trader",
                values=feature,
                aggfunc="mean",
            )
            .sort_index()
            .dropna(how="any")
        )
        if rel_pivot.empty:
            print(f"\n=== {feature} ===")
            print("No shared relative-hour buckets for all traders.")
            continue
        print(f"\n=== {feature} (first 8 shared relative-hour buckets) ===")
        print(rel_pivot.head(8).round(3).to_string())


def select_scoring_features(df: pd.DataFrame) -> list[str]:
    numeric_features = [c for c in FEATURE_COLUMNS if c in df.columns and pd.api.types.is_numeric_dtype(df[c])]
    return [c for c in numeric_features if df[c].notna().any()]


def fit_archetype_baselines(
    all_features: pd.DataFrame,
) -> tuple[dict[str, dict[str, np.ndarray | float]], pd.DataFrame, list[str]]:
    train = all_features[all_features["trader"].isin(ARCHETYPE_TRADERS)].copy()
    scoring_features = select_scoring_features(train)
    if not scoring_features:
        raise ValueError("No numeric scoring features available for baseline fitting.")

    prior_by_trader = train["trader"].value_counts(normalize=True)
    global_std = train[scoring_features].std(ddof=0).replace(0.0, np.nan).fillna(1.0)

    baselines: dict[str, dict[str, np.ndarray | float]] = {}
    baseline_rows = []
    for trader in ARCHETYPE_TRADERS:
        block = train[train["trader"] == trader][scoring_features]
        mean = block.mean()
        std = block.std(ddof=0).replace(0.0, np.nan).fillna(global_std)
        std_values = np.maximum(std.to_numpy(dtype=float), EPS)
        prior = float(prior_by_trader.get(trader, 1.0 / len(ARCHETYPE_TRADERS)))

        baselines[trader] = {
            "mean": mean.to_numpy(dtype=float),
            "std": std_values,
            "prior": prior,
        }

        row = {"trader": trader, "prior": prior}
        for i, feature in enumerate(scoring_features):
            row[f"{feature}_mean"] = float(mean[feature])
            row[f"{feature}_std"] = float(std_values[i])
        baseline_rows.append(row)

    baseline_df = pd.DataFrame(baseline_rows)
    return baselines, baseline_df, scoring_features


def compute_trader_probabilities(
    x: np.ndarray,
    baselines: dict[str, dict[str, np.ndarray | float]],
    traders: list[str],
) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    logp_by_trader: dict[str, float] = {}
    z_rms_by_trader: dict[str, float] = {}

    for trader in traders:
        mean = np.asarray(baselines[trader]["mean"], dtype=float)
        std = np.asarray(baselines[trader]["std"], dtype=float)
        prior = float(baselines[trader]["prior"])

        x_safe = np.where(np.isfinite(x), x, mean)
        z = (x_safe - mean) / (std + EPS)
        z_rms = float(np.sqrt(np.mean(z**2)))

        log_likelihood = float(-0.5 * np.sum(np.log(2.0 * np.pi * (std**2)) + z**2))
        log_posterior_unnorm = float(np.log(prior + EPS) + log_likelihood)

        z_rms_by_trader[trader] = z_rms
        logp_by_trader[trader] = log_posterior_unnorm

    max_logp = max(logp_by_trader.values())
    exp_scores = {trader: float(np.exp(logp - max_logp)) for trader, logp in logp_by_trader.items()}
    total = sum(exp_scores.values()) + EPS
    prob_by_trader = {trader: score / total for trader, score in exp_scores.items()}

    return prob_by_trader, z_rms_by_trader, logp_by_trader


def infer_mixed_states(
    mixed_features: pd.DataFrame,
    baselines: dict[str, dict[str, np.ndarray | float]],
    scoring_features: list[str],
) -> pd.DataFrame:
    traders = ARCHETYPE_TRADERS

    ordered = mixed_features.sort_values("timestamp").reset_index(drop=True).copy()
    ordered["trade_idx"] = np.arange(len(ordered), dtype=int)
    x_mat = ordered[scoring_features].to_numpy(dtype=float)

    records = []

    for i in range(len(ordered)):
        probs, z_rms, logps = compute_trader_probabilities(
            x=x_mat[i],
            baselines=baselines,
            traders=traders,
        )
        pred_state = max(probs, key=probs.get)

        row = {
            "pred_state": pred_state,
            "confidence": float(probs[pred_state]),
            "state_probability": float(probs[pred_state]),
        }
        for trader in traders:
            row[f"p_{trader}"] = float(probs[trader])
            row[f"z_rms_{trader}"] = float(z_rms[trader])
            row[f"logp_{trader}"] = float(logps[trader])
        records.append(row)

    infer_df = pd.DataFrame(records)
    return pd.concat([ordered, infer_df], axis=1)


def build_state_segments(inference_df: pd.DataFrame, state_col: str, confidence_col: str) -> pd.DataFrame:
    temp = inference_df.copy()
    temp["segment_id"] = temp[state_col].ne(temp[state_col].shift()).cumsum()
    segments = (
        temp.groupby("segment_id", sort=False)
        .agg(
            state=(state_col, "first"),
            start_timestamp=("timestamp", "min"),
            end_timestamp=("timestamp", "max"),
            num_trades=("segment_id", "size"),
            avg_confidence=(confidence_col, "mean"),
        )
        .reset_index(drop=True)
    )
    return segments


def main() -> None:
    datasets = load_all_datasets()

    engineered_parts = []
    for trader_name, df in datasets.items():
        features = engineer_features(df)
        features["trader"] = trader_name
        engineered_parts.append(features)
        print(
            f"{trader_name:12s} | "
            f"{features['timestamp'].min()} -> {features['timestamp'].max()} | "
            f"rows={len(features)}"
        )

    all_features = pd.concat(engineered_parts, ignore_index=True)
    hourly_features = aggregate_features_over_time(all_features)

    all_features.to_csv("derived_features_by_trade.csv", index=False)
    hourly_features.to_csv("feature_comparison_hourly.csv", index=False)

    summary_cols = [
        "trade_rate_per_min",
        "trades_last_15m",
        "loss_win_ratio_20",
        "hold_asymmetry_20",
        "size_after_loss_ratio_20",
        "qty_volatility_20",
        "tail_loss_share_50",
    ]
    summary = all_features.groupby("trader")[summary_cols].mean().round(3)
    print("\n=== Mean Feature Summary By Trader ===")
    print(summary.to_string())

    print_feature_comparison(hourly_features)

    baselines, baseline_df, scoring_features = fit_archetype_baselines(all_features)
    mixed_only = all_features[all_features["trader"] == "mixed"].copy().reset_index(drop=True)
    mixed_inference = infer_mixed_states(mixed_only, baselines, scoring_features=scoring_features)
    mixed_segments = build_state_segments(
        mixed_inference,
        state_col="pred_state",
        confidence_col="confidence",
    )

    prob_cols = [f"p_{trader}" for trader in ARCHETYPE_TRADERS]
    mixed_prob_long = (
        mixed_inference[["trade_idx", "timestamp", "pred_state", "state_probability", *prob_cols]]
        .melt(
            id_vars=["trade_idx", "timestamp", "pred_state", "state_probability"],
            value_vars=prob_cols,
            var_name="state",
            value_name="probability",
        )
        .assign(
            state=lambda d: d["state"].str.removeprefix("p_"),
            is_predicted_state=lambda d: d["state"].eq(d["pred_state"]),
        )
        .sort_values(["trade_idx", "state"])
        .reset_index(drop=True)
    )

    baseline_df.to_csv("trader_feature_baselines.csv", index=False)
    mixed_inference.to_csv("mixed_trade_state_inference.csv", index=False)
    mixed_prob_long.to_csv("mixed_trade_state_probabilities_long.csv", index=False)
    mixed_segments.to_csv("mixed_state_segments.csv", index=False)

    state_share = (
        mixed_inference["pred_state"]
        .value_counts(normalize=True)
        .rename("share")
        .mul(100)
        .round(2)
    )
    print("\n=== Mixed Trader Inferred State Share (Gaussian z-score probabilities) ===")
    print(state_share.to_string())

    print("\n=== Scoring Features Used ===")
    print(", ".join(scoring_features))

    print("\n=== Mixed Trader Last 12 Predictions ===")
    preview_cols = [
        "timestamp",
        "pred_state",
        "confidence",
        "p_calm",
        "p_loss_averse",
        "p_overtrader",
        "p_revenge",
    ]
    print(mixed_inference[preview_cols].tail(12).round(3).to_string(index=False))

    print("\nSaved files:")
    print(" - derived_features_by_trade.csv")
    print(" - feature_comparison_hourly.csv")
    print(" - trader_feature_baselines.csv")
    print(" - mixed_trade_state_inference.csv")
    print(" - mixed_trade_state_probabilities_long.csv")
    print(" - mixed_state_segments.csv")


if __name__ == "__main__":
    main()
