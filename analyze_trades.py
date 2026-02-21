from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

# ── constants ────────────────────────────────────────────────────────────────
WINDOW = 20
WINDOW_LARGE = 50
EPS = 1e-9

REQUIRED_COLS = {
    "timestamp", "asset", "side", "quantity",
    "entry_price", "exit_price", "profit_loss", "balance",
}

ARCHETYPES = ["calm", "loss_averse", "overtrader", "revenge"]

SCORING_FEATURES = [
    # ── Overtrading (PDF: excessive trades relative to balance, time clustering)
    "trade_rate_per_min", "trades_last_15m", "trades_last_60m",
    # ── Loss Aversion (PDF: holding losers too long + closing winners too early)
    "hold_asymmetry_20",     # loss_price_move / win_price_move — 3.35 for loss_averse vs ~1.0 calm
    "loss_win_ratio_20",     # avg_loss / avg_win magnitude — 231x for loss_averse
    "win_rate_20",           # loss_averse wins 59% (closes winners fast) vs 49% calm
    "max_loss_20",           # log-scaled worst loss — catastrophic for loss_averse
    # ── Revenge Trading (PDF: larger trades immediately after a loss)
    "size_after_loss_ratio_20",  # avg qty after loss / avg qty after win
    "loss_streak",               # consecutive losses fuel revenge impulse
    # ── shared tail-risk context
    "tail_loss_share_50",
]

# Path to pre-computed baselines (sits next to this script)
_SCRIPT_DIR = Path(__file__).parent
BASELINES_PATH = _SCRIPT_DIR / "trader_feature_baselines.csv"

# ── helper functions ──────────────────────────────────────────────────────────

def compute_loss_streak(pnl: pd.Series) -> pd.Series:
    streaks, streak = [], 0
    for v in pnl:
        streak = streak + 1 if v < 0 else 0
        streaks.append(streak)
    return pd.Series(streaks, index=pnl.index, dtype=float)


def compute_win_streak(pnl: pd.Series) -> pd.Series:
    streaks, streak = [], 0
    for v in pnl:
        streak = streak + 1 if v > 0 else 0
        streaks.append(streak)
    return pd.Series(streaks, index=pnl.index, dtype=float)


def tail_loss_share(values: np.ndarray) -> float:
    losses = values[values < 0]
    if losses.size < 5:
        return 0.0
    worst = np.sort(losses)[: max(1, int(np.ceil(losses.size * 0.10)))]
    return float(np.abs(worst.sum()) / (np.abs(losses.sum()) + EPS))


# ── core feature engineering ──────────────────────────────────────────────────

def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy().sort_values("timestamp").reset_index(drop=True)
    out["timestamp"] = pd.to_datetime(out["timestamp"])

    # ── base derived columns ─────────────────────────────────────────────────
    out["is_win"]        = (out["profit_loss"] > 0).astype(int)
    out["price_move_pct"] = (
        (out["exit_price"] - out["entry_price"]).abs()
        / (out["entry_price"].abs() + EPS) * 100
    )
    out["notional"] = out["quantity"] * out["entry_price"]

    # ── time features ────────────────────────────────────────────────────────
    out["time_diff_s"] = out["timestamp"].diff().dt.total_seconds()
    fallback = out["time_diff_s"].dropna().median()
    out["time_diff_s"] = out["time_diff_s"].fillna(fallback if not pd.isna(fallback) else 60.0).clip(lower=1.0)
    out["trade_rate_per_min"] = 60.0 / out["time_diff_s"]

    out = out.set_index("timestamp")
    trade_counter = pd.Series(1.0, index=out.index)
    out["trades_last_15m"] = trade_counter.rolling("15min").sum().to_numpy()
    out["trades_last_60m"] = trade_counter.rolling("60min").sum().to_numpy()
    out = out.reset_index()

    # ── P&L context ──────────────────────────────────────────────────────────
    out["prev_pl"]     = out["profit_loss"].shift(1).fillna(0.0)
    out["loss_streak"] = compute_loss_streak(out["profit_loss"])
    out["win_streak"]  = compute_win_streak(out["profit_loss"])

    # ── REQUIRED BIAS 1 · Overtrading ────────────────────────────────────────
    # (captured by trade_rate_per_min, trades_last_15m, trades_last_60m above)

    # ── REQUIRED BIAS 2 · Loss Aversion ──────────────────────────────────────
    roll_win  = out["profit_loss"].where(out["is_win"] == 1).rolling(WINDOW, min_periods=1).mean()
    roll_loss = out["profit_loss"].where(out["is_win"] == 0).abs().rolling(WINDOW, min_periods=1).mean()
    out["loss_win_ratio_20"] = (roll_loss / (roll_win.abs() + EPS)).replace([np.inf, -np.inf], np.nan).fillna(1.0)

    win_move  = out["price_move_pct"].where(out["is_win"] == 1).rolling(WINDOW, min_periods=1).mean()
    loss_move = out["price_move_pct"].where(out["is_win"] == 0).rolling(WINDOW, min_periods=1).mean()
    out["hold_asymmetry_20"] = (loss_move / (win_move + EPS)).replace([np.inf, -np.inf], np.nan).fillna(1.0)

    # ── REQUIRED BIAS 3 · Revenge Trading ────────────────────────────────────
    qty_after_loss = out["quantity"].where(out["prev_pl"] < 0).rolling(WINDOW, min_periods=1).mean()
    qty_after_win  = out["quantity"].where(out["prev_pl"] > 0).rolling(WINDOW, min_periods=1).mean()
    out["size_after_loss_ratio_20"] = (qty_after_loss / (qty_after_win + EPS)).replace([np.inf, -np.inf], np.nan).fillna(1.0)

    notional_after_loss = out["notional"].where(out["prev_pl"] < 0).rolling(WINDOW, min_periods=1).mean()
    notional_after_win  = out["notional"].where(out["prev_pl"] > 0).rolling(WINDOW, min_periods=1).mean()
    out["notional_after_loss_ratio_20"] = (notional_after_loss / (notional_after_win + EPS)).replace([np.inf, -np.inf], np.nan).fillna(1.0)

    # ── volatility / tail risk ───────────────────────────────────────────────
    roll_qty_mean = out["quantity"].rolling(WINDOW, min_periods=1).mean()
    roll_qty_std  = out["quantity"].rolling(WINDOW, min_periods=1).std().fillna(0.0)
    out["qty_volatility_20"] = roll_qty_std / (roll_qty_mean.abs() + EPS)

    roll_pl_mean = out["profit_loss"].rolling(WINDOW, min_periods=1).mean()
    roll_pl_std  = out["profit_loss"].rolling(WINDOW, min_periods=1).std().fillna(0.0)
    out["pnl_volatility_20"] = roll_pl_std / (roll_pl_mean.abs() + EPS)

    out["tail_loss_share_50"] = (
        out["profit_loss"].rolling(WINDOW_LARGE, min_periods=5)
        .apply(tail_loss_share, raw=True).fillna(0.0)
    )

    # ── NEW discriminative features for classifier ───────────────────────────

    # win_rate_20: rolling win rate — loss_averse has ~59% vs ~49% for calm/revenge
    out["win_rate_20"] = out["is_win"].rolling(WINDOW, min_periods=1).mean()

    # pl_skew_20: rolling skewness of P&L — loss_averse has extreme negative skew
    # (a few catastrophic losses drag the distribution heavily)
    def safe_skew(x: np.ndarray) -> float:
        if len(x) < 3:
            return 0.0
        mu, sigma = x.mean(), x.std()
        if sigma < EPS:
            return 0.0
        return float(np.mean(((x - mu) / sigma) ** 3))

    out["pl_skew_20"] = (
        out["profit_loss"].rolling(WINDOW, min_periods=3)
        .apply(safe_skew, raw=True).fillna(0.0)
    )

    # max_loss_20: worst single loss in last 20 trades (abs value, log-scaled)
    # loss_averse has catastrophically large max losses (~26k vs ~162 for calm)
    worst_loss = out["profit_loss"].rolling(WINDOW, min_periods=1).min()  # most negative
    out["max_loss_20"] = np.log1p(worst_loss.clip(upper=0).abs())

    # qty_after_loss_ratio_20: avg quantity on trade IMMEDIATELY after a loss
    # divided by avg quantity after a win — revenge traders escalate more (3.14x vs 2.98x)
    qty_after_loss_imm = out["quantity"].where(out["prev_pl"] < 0).rolling(WINDOW, min_periods=1).mean()
    qty_after_win_imm  = out["quantity"].where(out["prev_pl"] > 0).rolling(WINDOW, min_periods=1).mean()
    out["qty_after_loss_ratio_20"] = (
        (qty_after_loss_imm / (qty_after_win_imm + EPS))
        .replace([np.inf, -np.inf], np.nan).fillna(1.0)
    )

    # streak_qty_slope_20: slope of quantity vs loss-streak-length in the last 20 trades
    # Revenge: +0.55 qty/streak-step (increases size as losses mount)
    # Calm:    -0.42 qty/streak-step (slightly reduces or holds steady)
    def streak_slope(window_df: pd.DataFrame) -> float:
        """Linear slope of quantity on loss streak depth (streaks >= 1 only)."""
        s = window_df["loss_streak"].values.astype(float)
        q = window_df["quantity"].values.astype(float)
        mask = (s >= 1) & np.isfinite(s) & np.isfinite(q)
        if mask.sum() < 3:
            return 0.0
        xs, ys = s[mask], q[mask]
        if xs.std() < EPS:
            return 0.0
        return float(np.polyfit(xs, ys, 1)[0])

    # Build combined df for rolling apply (we need both columns together)
    _ss_df = out[["loss_streak", "quantity"]].copy()

    def _rolling_streak_slope(idx: int) -> float:
        start = max(0, idx - WINDOW + 1)
        chunk = _ss_df.iloc[start : idx + 1]
        return streak_slope(chunk)

    out["streak_qty_slope_20"] = [_rolling_streak_slope(i) for i in range(len(out))]

    # ── EXTRA BIAS 4 · Disposition Effect ────────────────────────────────────
    # hold_asymmetry > 1 means losers are held longer (price moves more) than winners
    # Score: how far above 1.0 the ratio sits, clipped to [0, 5]
    out["disposition_score"] = (out["hold_asymmetry_20"] - 1.0).clip(lower=0.0, upper=5.0)

    # ── EXTRA BIAS 5 · Gambler's Fallacy ────────────────────────────────────
    # Increasing size after a loss streak expecting a reversal
    # (different from revenge: revenge = emotion/speed, gambler = size escalation on expectation)
    out["gambler_score"] = out["loss_streak"] * out["size_after_loss_ratio_20"]

    # ── bias flag columns (True/False per trade) ─────────────────────────────
    # Absolute thresholds anchored to reference archetype data:
    #   overtrading:   calm/loss_averse/revenge all trade at ~15/15min; overtrader at ~90/15min
    #                  → threshold: >30 trades in 15 min = clearly above calm baseline
    #   loss_aversion: PDF = holding losers too long (hold_asymmetry > 1.5) AND
    #                  unbalanced risk/reward (loss_win_ratio > 1.5)
    #   revenge:       PDF = larger trades immediately after loss; escalation during streak
    out["flag_overtrading"]     = out["trades_last_15m"] > 30
    # loss_win_ratio_20 > 2.0 means recent avg loss is 2x avg win in window
    # hold_asymmetry_20 > 2.0 means losers held through 2x more price movement than winners
    out["flag_loss_aversion"]   = (out["loss_win_ratio_20"] > 2.0) | (out["hold_asymmetry_20"] > 2.0)
    out["flag_revenge_trading"] = (out["loss_streak"] >= 2) & (out["size_after_loss_ratio_20"] > 1.15)
    out["flag_disposition"]     = out["disposition_score"] > 0.5
    out["flag_gambler_fallacy"] = out["gambler_score"] > out["gambler_score"].quantile(0.80)

    return out


# ── Bayesian bias-state classifier ───────────────────────────────────────────

def build_baselines(ref_datasets: dict[str, Path]) -> dict[str, dict]:
    """
    Compute archetype baselines directly from reference CSVs.

    Uses a two-tier nearest-centroid strategy:
      1. Overtrader is detected via frequency features (trade_rate_per_min etc.)
         which have enormous Fisher ratios relative to other archetypes.
      2. Among calm / loss_averse / revenge the frequency features are identical,
         so we compute Fisher weights EXCLUDING overtrader pairs, ensuring
         loss-aversion and revenge-specific signals actually matter.

    Both tiers share the same baseline dict; the weights array encodes tier logic.
    """
    archetype_dfs: dict[str, pd.DataFrame] = {}
    for trader, path in ref_datasets.items():
        if path.exists():
            raw = pd.read_csv(path)
            archetype_dfs[trader] = engineer_features(raw)

    if not archetype_dfs:
        return {}

    # per-trader means
    means = {t: df[SCORING_FEATURES].mean().to_numpy(dtype=float)
             for t, df in archetype_dfs.items()
             if all(f in df.columns for f in SCORING_FEATURES)}

    # pooled std: RMS of within-trader stds → shared across all traders
    stds_list = [df[SCORING_FEATURES].std().to_numpy(dtype=float)
                 for df in archetype_dfs.values()
                 if all(f in df.columns for f in SCORING_FEATURES)]
    pooled_std = np.sqrt(np.mean(np.array(stds_list) ** 2, axis=0))
    pooled_std = np.where(pooled_std < EPS, 1.0, pooled_std)

    # Fisher weights using ONLY non-overtrader pairs so that frequency
    # features don't drown out the loss-aversion / revenge signals.
    non_ot = [t for t in means if t != "overtrader"]
    n_feats = len(SCORING_FEATURES)
    fisher_weights = np.zeros(n_feats)
    n_pairs = 0
    for i in range(len(non_ot)):
        for j in range(i + 1, len(non_ot)):
            ti, tj = non_ot[i], non_ot[j]
            diff_sq = (means[ti] - means[tj]) ** 2
            denom = pooled_std ** 2 + EPS
            fisher_weights += diff_sq / denom
            n_pairs += 1

    if n_pairs > 0:
        fisher_weights /= n_pairs

    # Frequency features get a manual boost so overtrader is still well-separated
    freq_feats = {"trade_rate_per_min", "trades_last_15m", "trades_last_60m"}
    for i, feat in enumerate(SCORING_FEATURES):
        if feat in freq_feats:
            fisher_weights[i] = max(fisher_weights[i], 1.0)

    # sqrt(Fisher) → signal-to-noise scale, clip to [0.05, 5]
    feature_weights = np.sqrt(fisher_weights + EPS)
    feature_weights = np.clip(feature_weights / (feature_weights.mean() + EPS), 0.05, 5.0)

    n = len(archetype_dfs)
    return {
        trader: {
            "mean": mean,
            "std": pooled_std,
            "weights": feature_weights,
            "prior": 1.0 / n,
        }
        for trader, mean in means.items()
    }


def load_baselines(path: Path) -> dict:
    """
    Load baselines from trader_feature_baselines.csv (legacy format).
    Uses pooled std so nearest-centroid distance drives classification.
    """
    df = pd.read_csv(path)
    avail = [f for f in SCORING_FEATURES
             if f"{f}_mean" in df.columns and f"{f}_std" in df.columns]

    means = {}
    for _, row in df.iterrows():
        trader = row["trader"]
        means[trader] = np.array([row[f"{f}_mean"] for f in avail], dtype=float)

    all_stds = np.array([[row[f"{f}_std"] for f in avail]
                          for _, row in df.iterrows()], dtype=float)
    pooled_std = np.sqrt(np.mean(all_stds ** 2, axis=0))
    pooled_std = np.where(pooled_std < EPS, 1.0, pooled_std)

    return {
        row["trader"]: {
            "mean":  means[row["trader"]],
            "std":   pooled_std,
            "prior": float(row["prior"]),
            "_feats": avail,
        }
        for _, row in df.iterrows()
    }


def classify_row(x: np.ndarray, baselines: dict) -> dict[str, float]:
    """
    Weighted Gaussian nearest-centroid classifier (shared pooled std).
    Features are weighted by their Fisher discriminability score so that
    informative features dominate the classification distance.
    Returns {trader: probability} summing to 1.
    """
    log_posts: dict[str, float] = {}
    # grab weights from any archetype (they're shared)
    _sample = next(iter(baselines.values()))
    weights = _sample.get("weights", np.ones(len(x)))

    for trader, params in baselines.items():
        mean, std, prior = params["mean"], params["std"], params["prior"]
        x_safe = np.where(np.isfinite(x), x, mean)
        z      = (x_safe - mean) / (std + EPS)
        # weighted squared Mahalanobis distance
        log_ll = -0.5 * float(np.sum(weights * z ** 2))
        log_posts[trader] = np.log(prior + EPS) + log_ll

    max_lp   = max(log_posts.values())
    exp_vals = {t: float(np.exp(lp - max_lp)) for t, lp in log_posts.items()}
    total    = sum(exp_vals.values()) + EPS
    return {t: v / total for t, v in exp_vals.items()}


def add_state_probabilities(df: pd.DataFrame, baselines: dict) -> pd.DataFrame:
    """
    For every row in df, compute per-archetype probabilities and add columns:
        p_calm, p_loss_averse, p_overtrader, p_revenge,
        pred_state, state_confidence
    """
    # support both new baselines (SCORING_FEATURES) and legacy (subset)
    sample = next(iter(baselines.values()))
    feats = sample.get("_feats", SCORING_FEATURES)
    feats = [f for f in feats if f in df.columns]

    avail_idx = [SCORING_FEATURES.index(f) for f in feats if f in SCORING_FEATURES]

    trimmed: dict[str, dict] = {}
    for trader, params in baselines.items():
        mean    = params["mean"]
        std     = params["std"]
        weights = params.get("weights", np.ones(len(mean)))
        if "_feats" not in params:
            mean    = mean[avail_idx]
            std     = std[avail_idx]
            weights = weights[avail_idx]
        trimmed[trader] = {"mean": mean, "std": std, "weights": weights, "prior": params["prior"]}

    x_mat   = df[feats].to_numpy(dtype=float)
    records = [classify_row(x_mat[i], trimmed) for i in range(len(df))]
    prob_df = pd.DataFrame(records).rename(columns=lambda c: f"p_{c}")

    p_cols = [c for c in [f"p_{a}" for a in ARCHETYPES] if c in prob_df.columns]
    prob_df["pred_state"]       = prob_df[p_cols].idxmax(axis=1).str.removeprefix("p_")
    prob_df["state_confidence"] = prob_df[p_cols].max(axis=1)

    return pd.concat([df.reset_index(drop=True), prob_df.reset_index(drop=True)], axis=1)


# ── bias summary ──────────────────────────────────────────────────────────────

def print_bias_summary(df: pd.DataFrame) -> None:
    total = len(df)
    flags = {
        "Overtrading":      "flag_overtrading",
        "Loss Aversion":    "flag_loss_aversion",
        "Revenge Trading":  "flag_revenge_trading",
        "Disposition Eff.": "flag_disposition",
        "Gambler Fallacy":  "flag_gambler_fallacy",
    }
    print("\n" + "=" * 50)
    print("  BIAS SUMMARY")
    print("=" * 50)
    for label, col in flags.items():
        count = int(df[col].sum())
        pct   = count / total * 100
        bar   = "#" * int(pct / 2)
        print(f"  {label:<18}  {count:>5} / {total}  ({pct:5.1f}%)  {bar}")
    print("=" * 50)

    print("\n  FEATURE MEANS")
    print("-" * 50)
    feature_means = {
        "trade_rate_per_min":         "trades/min",
        "trades_last_15m":            "trades last 15m",
        "loss_win_ratio_20":          "loss/win ratio",
        "hold_asymmetry_20":          "hold asymmetry",
        "size_after_loss_ratio_20":   "size after loss",
        "notional_after_loss_ratio_20": "notional after loss",
        "qty_volatility_20":          "qty volatility",
        "pnl_volatility_20":          "pnl volatility",
        "tail_loss_share_50":         "tail loss share",
        "disposition_score":          "disposition score",
        "gambler_score":              "gambler score",
    }
    for col, label in feature_means.items():
        if col in df.columns:
            print(f"  {label:<26}  {df[col].mean():>10.4f}")
    print("=" * 50 + "\n")


# ── plotting ──────────────────────────────────────────────────────────────────

# Each entry: (column, label, bias group, reference line value or None)
PLOT_PANELS = [
    # Overtrading
    ("trade_rate_per_min",          "Trades / min",              "Overtrading",       None),
    ("trades_last_15m",             "Trades last 15 min",        "Overtrading",       None),
    ("trades_last_60m",             "Trades last 60 min",        "Overtrading",       None),
    # Loss Aversion
    ("loss_win_ratio_20",           "Loss/Win ratio (20)",       "Loss Aversion",     1.0),
    ("hold_asymmetry_20",           "Hold asymmetry (20)",       "Loss Aversion",     1.0),
    # Revenge Trading
    ("loss_streak",                 "Loss streak",               "Revenge Trading",   None),
    ("size_after_loss_ratio_20",    "Size after loss (20)",      "Revenge Trading",   1.0),
    ("notional_after_loss_ratio_20","Notional after loss (20)",  "Revenge Trading",   1.0),
    # Disposition Effect
    ("disposition_score",           "Disposition score",         "Disposition",       0.5),
    # Gambler's Fallacy
    ("win_streak",                  "Win streak",                "Gambler's Fallacy", None),
    ("gambler_score",               "Gambler score",             "Gambler's Fallacy", None),
    # Volatility / Risk
    ("qty_volatility_20",           "Qty volatility (20)",       "Risk",              None),
    ("pnl_volatility_20",           "PnL volatility (20)",       "Risk",              None),
    ("tail_loss_share_50",          "Tail loss share (50)",      "Risk",              None),
    # Account
    ("balance",                     "Account balance",           "Account",           None),
    ("profit_loss",                 "P&L per trade",             "Account",           0.0),
]

GROUP_COLORS = {
    "Overtrading":       "#e05c2a",
    "Loss Aversion":     "#2a7ae0",
    "Revenge Trading":   "#c0392b",
    "Disposition":       "#8e44ad",
    "Gambler's Fallacy": "#d4a017",
    "Risk":              "#27ae60",
    "Account":           "#2c3e50",
}

FLAG_COLS = {
    "flag_overtrading":     ("Overtrading",       "#e05c2a"),
    "flag_loss_aversion":   ("Loss Aversion",     "#2a7ae0"),
    "flag_revenge_trading": ("Revenge Trading",   "#c0392b"),
    "flag_disposition":     ("Disposition",       "#8e44ad"),
    "flag_gambler_fallacy": ("Gambler's Fallacy", "#d4a017"),
}


def plot_features(df: pd.DataFrame, chart_path: Path, title: str) -> None:
    # only keep panels whose column is actually in the df
    panels = [(col, lbl, grp, ref) for col, lbl, grp, ref in PLOT_PANELS if col in df.columns]
    n = len(panels)

    x = df["timestamp"] if "timestamp" in df.columns else pd.RangeIndex(len(df))

    ncols = 2
    nrows = (n + 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(18, nrows * 2.8), sharex=False)
    axes = axes.flatten()

    fig.suptitle(f"Feature Timeline — {title}", fontsize=14, fontweight="bold", y=1.002)

    for idx, (col, label, group, ref) in enumerate(panels):
        ax = axes[idx]
        color = GROUP_COLORS.get(group, "#555555")
        y = df[col]

        ax.plot(x, y, color=color, linewidth=0.8, alpha=0.85)
        ax.fill_between(x, y, alpha=0.12, color=color)

        # reference line (e.g. ratio = 1.0, P&L = 0)
        if ref is not None:
            ax.axhline(ref, color="#888888", linewidth=0.8, linestyle="--", alpha=0.7)

        # shade bias-flagged regions for matching flag
        flag_map = {
            "Overtrading":       "flag_overtrading",
            "Loss Aversion":     "flag_loss_aversion",
            "Revenge Trading":   "flag_revenge_trading",
            "Disposition":       "flag_disposition",
            "Gambler's Fallacy": "flag_gambler_fallacy",
        }
        flag_col = flag_map.get(group)
        if flag_col and flag_col in df.columns:
            flagged = df[flag_col].astype(bool)
            ymin, ymax = ax.get_ylim()
            ax.fill_between(x, ymin, ymax, where=flagged,
                            color=color, alpha=0.10, zorder=0)

        ax.set_title(f"[{group}]  {label}", fontsize=8, color=color, fontweight="bold")
        ax.tick_params(axis="x", labelsize=6, rotation=30)
        ax.tick_params(axis="y", labelsize=7)
        ax.grid(axis="y", linestyle=":", linewidth=0.5, alpha=0.5)
        ax.set_xlim(x.iloc[0] if hasattr(x, "iloc") else x[0],
                    x.iloc[-1] if hasattr(x, "iloc") else x[-1])

    # hide any unused subplots
    for idx in range(len(panels), len(axes)):
        axes[idx].set_visible(False)

    # legend for bias groups
    patches = [mpatches.Patch(color=c, label=g) for g, c in GROUP_COLORS.items()]
    fig.legend(handles=patches, loc="lower center", ncol=len(GROUP_COLORS),
               fontsize=8, frameon=False, bbox_to_anchor=(0.5, -0.01))

    plt.tight_layout()
    fig.savefig(chart_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved feature chart to {chart_path}")


def plot_state_probabilities(df: pd.DataFrame, chart_path: Path, title: str) -> None:
    """
    Stacked-area chart of p_calm / p_loss_averse / p_overtrader / p_revenge
    over time, with the predicted state highlighted and confidence shown.
    """
    prob_cols = [f"p_{a}" for a in ARCHETYPES if f"p_{a}" in df.columns]
    if not prob_cols:
        return

    state_colors = {
        "p_calm":        "#27ae60",
        "p_loss_averse": "#2a7ae0",
        "p_overtrader":  "#e05c2a",
        "p_revenge":     "#c0392b",
    }
    state_labels = {
        "p_calm":        "Calm",
        "p_loss_averse": "Loss Averse",
        "p_overtrader":  "Overtrader",
        "p_revenge":     "Revenge",
    }

    x = df["timestamp"] if "timestamp" in df.columns else pd.RangeIndex(len(df))

    fig, axes = plt.subplots(3, 1, figsize=(16, 10), sharex=True,
                             gridspec_kw={"height_ratios": [3, 1, 1]})
    fig.suptitle(f"Bias State Probabilities — {title}", fontsize=13, fontweight="bold")

    # ── panel 1: stacked area ────────────────────────────────────────────────
    ax = axes[0]
    ys = np.array([df[c].to_numpy(dtype=float) for c in prob_cols])
    colors = [state_colors[c] for c in prob_cols]
    labels = [state_labels[c] for c in prob_cols]
    ax.stackplot(x, ys, labels=labels, colors=colors, alpha=0.75)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Probability", fontsize=9)
    ax.set_title("State probability over time (stacked)", fontsize=9)
    ax.legend(loc="upper right", fontsize=8, framealpha=0.7)
    ax.grid(axis="y", linestyle=":", linewidth=0.5, alpha=0.5)

    # ── panel 2: dominant state as coloured bar ───────────────────────────────
    ax2 = axes[1]
    if "pred_state" in df.columns:
        state_to_num  = {a: i for i, a in enumerate(ARCHETYPES)}
        state_num     = df["pred_state"].map(state_to_num).fillna(0).astype(int)
        bar_colors    = [list(state_colors.values())[n] for n in state_num]
        ax2.bar(x, [1] * len(df), color=bar_colors, width=1.0, align="center")
        ax2.set_yticks([])
        ax2.set_ylabel("Pred. state", fontsize=8)
        # custom legend
        patches = [mpatches.Patch(color=state_colors[f"p_{a}"], label=state_labels[f"p_{a}"])
                   for a in ARCHETYPES if f"p_{a}" in state_colors]
        ax2.legend(handles=patches, loc="upper right", fontsize=7, framealpha=0.7)

    # ── panel 3: confidence line ──────────────────────────────────────────────
    ax3 = axes[2]
    if "state_confidence" in df.columns:
        ax3.plot(x, df["state_confidence"], color="#555555", linewidth=0.8)
        ax3.fill_between(x, df["state_confidence"], alpha=0.15, color="#555555")
        ax3.axhline(0.5, color="#aaaaaa", linewidth=0.8, linestyle="--")
        ax3.set_ylim(0, 1)
        ax3.set_ylabel("Confidence", fontsize=8)
        ax3.set_title("Classifier confidence", fontsize=8)
        ax3.tick_params(axis="x", labelsize=6, rotation=30)
        ax3.grid(axis="y", linestyle=":", linewidth=0.5, alpha=0.5)

    plt.tight_layout()
    fig.savefig(chart_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved state-probability chart to {chart_path}")


def plot_bias_flags(df: pd.DataFrame, chart_path: Path, title: str) -> None:
    """
    Rolling-average bias intensity lines over time.
    Each bias flag (0/1) is smoothed into a continuous 0–1 intensity curve.
    """
    flag_items = [(col, lbl, clr) for col, (lbl, clr) in FLAG_COLS.items() if col in df.columns]
    n = len(flag_items) + 1  # +1 for balance row
    x = df["timestamp"] if "timestamp" in df.columns else pd.RangeIndex(len(df))

    # rolling window: ~5% of trades, min 10
    roll_w = max(10, len(df) // 20)

    fig, axes = plt.subplots(n, 1, figsize=(16, n * 1.8), sharex=True)
    fig.suptitle(f"Bias Intensity Over Time — {title}", fontsize=13, fontweight="bold")

    # top panel: account balance
    ax0 = axes[0]
    ax0.plot(x, df["balance"], color="#2c3e50", linewidth=1.0)
    ax0.fill_between(x, df["balance"], alpha=0.15, color="#2c3e50")
    ax0.set_ylabel("Balance", fontsize=8)
    ax0.set_title("Account Balance", fontsize=8, fontweight="bold")
    ax0.grid(axis="y", linestyle=":", linewidth=0.5, alpha=0.5)

    for row_idx, (flag_col, label, color) in enumerate(flag_items):
        ax = axes[row_idx + 1]

        # smooth rolling mean of the 0/1 flag → intensity in [0, 1]
        intensity = (
            df[flag_col].astype(float)
            .rolling(roll_w, min_periods=1, center=True)
            .mean()
        )

        ax.plot(x, intensity, color=color, linewidth=1.2, alpha=0.9)
        ax.fill_between(x, intensity, alpha=0.18, color=color)
        ax.axhline(0.5, color="#aaaaaa", linewidth=0.7, linestyle="--", alpha=0.6)
        ax.set_ylim(0, 1)
        ax.set_ylabel(label, fontsize=8, color=color)
        ax.tick_params(axis="x", labelsize=6, rotation=30)
        ax.tick_params(axis="y", labelsize=7)
        ax.grid(axis="y", linestyle=":", linewidth=0.5, alpha=0.4)
        ax.set_title(f"{label} intensity  (rolling {roll_w}-trade avg)",
                     fontsize=7, color=color, loc="left")

        # shade balance where intensity is above 0.5
        ax0.fill_between(x, df["balance"].min(), df["balance"].max(),
                         where=intensity > 0.5, color=color, alpha=0.07, zorder=0)

    plt.tight_layout()
    fig.savefig(chart_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved bias-intensity chart to {chart_path}")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    input_path = Path(sys.argv[1])
    if not input_path.exists():
        print(f"Error: file not found: {input_path}")
        sys.exit(1)

    output_path = (
        Path(sys.argv[2]) if len(sys.argv) >= 3
        else input_path.with_name(input_path.stem + "_analyzed.csv")
    )

    # ── load ──────────────────────────────────────────────────────────────────
    df = pd.read_csv(input_path)
    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        print(f"Error: input CSV is missing required columns: {missing}")
        sys.exit(1)

    print(f"Loaded {len(df)} trades from {input_path}")

    # ── compute features ──────────────────────────────────────────────────────
    result = engineer_features(df)

    # ── classify: per-trade bias-state probabilities ──────────────────────────
    ref_datasets = {
        "calm":        _SCRIPT_DIR / "trading_datasets/calm_trader.csv",
        "loss_averse": _SCRIPT_DIR / "trading_datasets/loss_averse_trader.csv",
        "overtrader":  _SCRIPT_DIR / "trading_datasets/overtrader.csv",
        "revenge":     _SCRIPT_DIR / "trading_datasets/revenge_trader.csv",
    }
    baselines = build_baselines(ref_datasets)
    if baselines:
        result = add_state_probabilities(result, baselines)
        print(f"Classifier baselines built from {len(baselines)} reference datasets.")
    else:
        print("Warning: no reference datasets found — skipping probability scores.")

    # ── save CSV ──────────────────────────────────────────────────────────────
    result.to_csv(output_path, index=False)
    print(f"Saved per-trade feature results to {output_path}")

    print_bias_summary(result)

    # ── save charts ───────────────────────────────────────────────────────────
    stem = input_path.stem
    features_chart = input_path.with_name(stem + "_features.png")
    flags_chart    = input_path.with_name(stem + "_bias_flags.png")
    probs_chart    = input_path.with_name(stem + "_state_probs.png")

    plot_features(result, features_chart, title=stem)
    plot_bias_flags(result, flags_chart, title=stem)
    plot_state_probabilities(result, probs_chart, title=stem)


if __name__ == "__main__":
    main()
