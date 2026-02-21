import pandas as pd

def clean_csv(file_name):
    '''
    Cleans a CSV file by removing rows with any missing values.

    Args:
        file_name (str): Path to the CSV file to be cleaned.

    Returns:
        pd.DataFrame: Cleaned DataFrame with no missing values.
    '''
    # Load the CSV file
    df = pd.read_csv(file_name)

    # Check for missing values
    print("Missing values per column:\n", df.isnull().sum())

    # Remove rows with any missing fields
    df_clean = df.dropna()
    df_clean.reset_index(drop=True, inplace=True)

    # Save the cleaned data to a new CSV
    cleaned_file_name = file_name.replace(".csv", "_clean.csv")
    df_clean.to_csv(cleaned_file_name, index=False)

    return df_clean