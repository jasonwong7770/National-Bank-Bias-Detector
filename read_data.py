import pandas as pd
import glob
import os

# Define the uploads directory
uploads_dir = 'uploads'

# Find all CSV files in the uploads directory
csv_files = glob.glob(os.path.join(uploads_dir, '*.csv'))

if not csv_files:
    print(f"No CSV files found in '{uploads_dir}' directory.")
else:
    # Use the first CSV file found
    file_path = csv_files[0]
    print(f"Reading file: {file_path}")
    
    try:
        df = pd.read_csv(file_path)
        print("-" * 30)
        print(df.head())
        print("-" * 30)
    except Exception as e:
        print(f"An error occurred while reading '{file_path}': {e}")
