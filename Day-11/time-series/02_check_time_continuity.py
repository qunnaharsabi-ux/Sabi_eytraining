import pandas as pd

# -----------------------------
# Load the dataset
# -----------------------------
file_path = "sakshi_ppg_20260611T074737_len148s.csv"   # Update path if needed
df = pd.read_csv(file_path)

# -----------------------------
# Specify the timestamp column
# -----------------------------
# Change this if your timestamp column has a different name
timestamp_col = "timestamp_ms"

# -----------------------------
# Check if column exists
# -----------------------------
if timestamp_col not in df.columns:
    raise ValueError(f"Column '{timestamp_col}' not found in dataset.")

# -----------------------------
# Sort by timestamp
# -----------------------------
df = df.sort_values(by=timestamp_col).reset_index(drop=True)

# -----------------------------
# Calculate time differences
# -----------------------------
df["time_diff"] = df[timestamp_col].diff()

# Expected interval = most common difference
expected_interval = df["time_diff"].mode()[0]

print(f"Expected Sampling Interval: {expected_interval}")

# -----------------------------
# Find discontinuities
# -----------------------------
missing_intervals = df[df["time_diff"] != expected_interval]

print("\n===== Missing/Irregular Timestamp Records =====")
print(missing_intervals[[timestamp_col, "time_diff"]])

# -----------------------------
# Save results
# -----------------------------
missing_intervals.to_csv(
    "missing_timestamp_report.csv",
    index=False
)

print("\nTime continuity report saved as 'missing_timestamp_report.csv'")