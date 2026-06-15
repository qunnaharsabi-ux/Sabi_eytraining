import pandas as pd
import matplotlib.pyplot as plt
import os

# -----------------------------
# Load the dataset
# -----------------------------
file_path = "filled_dataset.csv"  # Use this if you've already handled missing values
# file_path = "sakshi_ppg_20260611T074737_len148s.csv"  # Or use original file

df = pd.read_csv(file_path)

# -----------------------------
# Create output directory
# -----------------------------
os.makedirs("plots", exist_ok=True)

# -----------------------------
# Timestamp column
# -----------------------------
timestamp_col = "timestamp_ms"

# Convert to datetime (optional)
if timestamp_col in df.columns:
    df["timestamp"] = pd.to_datetime(df[timestamp_col], unit="ms")
    x_axis = df["timestamp"]
    x_label = "Time"
else:
    x_axis = df.index
    x_label = "Sample Index"

# -----------------------------
# Plot numeric columns
# -----------------------------
exclude_cols = ["seq", "timestamp_ms"]

numeric_cols = df.select_dtypes(include=["number"]).columns

for col in numeric_cols:
    if col in exclude_cols:
        continue

    plt.figure(figsize=(12, 5))
    plt.plot(x_axis, df[col], linewidth=1)

    plt.title(f"Time Series Plot - {col}")
    plt.xlabel(x_label)
    plt.ylabel(col)

    plt.grid(True)

    plt.tight_layout()
    plt.savefig(f"plots/{col}_timeseries.png")
    plt.show()

print("\nTime series plots generated successfully.")
print("Plots saved in the 'plots/' folder.")