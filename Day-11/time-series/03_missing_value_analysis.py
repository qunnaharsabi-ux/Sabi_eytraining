import pandas as pd

# -----------------------------
# Load the dataset
# -----------------------------
file_path = "sakshi_ppg_20260611T074737_len148s.csv"   # Update path if needed
df = pd.read_csv(file_path)

# -----------------------------
# Calculate missing values
# -----------------------------
missing_count = df.isnull().sum()
missing_percent = (missing_count / len(df)) * 100

# -----------------------------
# Determine fill strategy
# -----------------------------
strategy = []

for col in df.columns:
    if missing_count[col] == 0:
        strategy.append("No missing values")
    elif pd.api.types.is_numeric_dtype(df[col]):
        strategy.append("Forward Fill (ffill) → Backward Fill (bfill)")
    else:
        strategy.append("Forward Fill (ffill)")

# -----------------------------
# Create summary report
# -----------------------------
report = pd.DataFrame({
    "Column": df.columns,
    "Missing Count": missing_count.values,
    "Missing Percentage": missing_percent.round(2).values,
    "Suggested Strategy": strategy
})

# -----------------------------
# Print report
# -----------------------------
print("\n===== Missing Value Report =====")
print(report)

# -----------------------------
# Fill missing values
# -----------------------------
df_filled = df.copy()

# Forward fill then backward fill
df_filled = df_filled.ffill().bfill()

# -----------------------------
# Save outputs
# -----------------------------
report.to_csv("missing_value_report.csv", index=False)
df_filled.to_csv("filled_dataset.csv", index=False)

print("\nMissing value report saved as 'missing_value_report.csv'")
print("Filled dataset saved as 'filled_dataset.csv'")