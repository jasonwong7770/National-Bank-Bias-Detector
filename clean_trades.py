"""
clean_trades.py
---------------
Cleans a raw trade CSV before it is stored in uploads/.

Cleaning steps
--------------
1. Strip whitespace from column names and string values.
2. Enforce required columns — raise ValueError if any are missing.
3. Parse and validate the timestamp column; drop rows with unparseable timestamps.
4. Drop exact duplicate rows.
5. Drop rows where any numeric column (quantity, entry_price, exit_price,
   profit_loss, balance) is missing or non-numeric.
6. Drop rows where quantity <= 0, entry_price <= 0, or exit_price <= 0.
7. Normalise the side column to uppercase (BUY / SELL); drop rows with
   any other value.
8. Sort chronologically by timestamp and reset the index.
9. Round all float columns to 8 decimal places to remove floating-point noise.

Usage
-----
    from clean_trades import clean

    cleaned_df = clean(raw_csv_path)          # returns a pandas DataFrame
    cleaned_df.to_csv(output_path, index=False)

The function raises ValueError with a descriptive message if the file
cannot be cleaned to a usable state (e.g. no valid rows remain).
"""

import pandas as pd

REQUIRED_COLUMNS = [
    "timestamp",
    "asset",
    "side",
    "quantity",
    "entry_price",
    "exit_price",
    "profit_loss",
    "balance",
]

NUMERIC_COLUMNS = ["quantity", "entry_price", "exit_price", "profit_loss", "balance"]
VALID_SIDES     = {"BUY", "SELL"}


def clean(filepath: str) -> pd.DataFrame:
    """
    Load and clean the CSV at *filepath*.

    Returns
    -------
    pd.DataFrame
        Cleaned, sorted dataframe ready for analysis.

    Raises
    ------
    ValueError
        If required columns are missing or no valid rows survive cleaning.
    """
    df = pd.read_csv(filepath)

    # 1. Strip whitespace from column names and string cells
    df.columns = df.columns.str.strip()
    df = df.apply(lambda col: col.str.strip() if col.dtype == object else col)

    # 2. Enforce required columns
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # 3. Parse timestamps — drop rows that can't be parsed
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    before = len(df)
    df = df.dropna(subset=["timestamp"])
    if len(df) < before:
        print(f"[clean] Dropped {before - len(df)} row(s) with unparseable timestamps.")

    # 4. Drop exact duplicate rows
    before = len(df)
    df = df.drop_duplicates()
    if len(df) < before:
        print(f"[clean] Dropped {before - len(df)} exact duplicate row(s).")

    # 5. Coerce numeric columns — rows that can't be coerced become NaN then drop
    for col in NUMERIC_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    before = len(df)
    df = df.dropna(subset=NUMERIC_COLUMNS)
    if len(df) < before:
        print(f"[clean] Dropped {before - len(df)} row(s) with non-numeric values.")

    # 6. Drop rows with non-positive quantity or prices
    before = len(df)
    df = df[(df["quantity"] > 0) & (df["entry_price"] > 0) & (df["exit_price"] > 0)]
    if len(df) < before:
        print(f"[clean] Dropped {before - len(df)} row(s) with zero/negative quantity or price.")

    # 7. Normalise side to uppercase; drop rows with invalid values
    df["side"] = df["side"].str.upper()
    before = len(df)
    df = df[df["side"].isin(VALID_SIDES)]
    if len(df) < before:
        print(f"[clean] Dropped {before - len(df)} row(s) with invalid side values.")

    if df.empty:
        raise ValueError("No valid rows remain after cleaning.")

    # 8. Sort chronologically and reset index
    df = df.sort_values("timestamp").reset_index(drop=True)

    # 9. Round floats to 8 decimal places
    df[NUMERIC_COLUMNS] = df[NUMERIC_COLUMNS].round(8)

    print(f"[clean] Done. {len(df)} clean row(s) ready.")
    return df
