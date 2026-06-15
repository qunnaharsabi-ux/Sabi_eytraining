import pandas as pd

# -----------------------------
# Load the dataset
# -----------------------------
file_path = "filled_dataset.csv"  # Update path if needed
df = pd.read_csv(file_path)

# -----------------------------
# Select numeric columns
# -----------------------------
numeric_cols = df.select_dtypes(include=["number"]).columns

# Exclude columns that should not be checked for outliers
exclude_cols = ["seq", "timestamp_ms"]

# Dictionary to store summary
outlier_summary = {}

# DataFrame to store all outlier rows
all_outliers = pd.DataFrame()

# -----------------------------
# Detect outliers using IQR
# -----------------------------
for col in numeric_cols:
    if col in exclude_cols:
        continue

    Q1 = df[col].quantile(0.25)
    Q3 = df[col].quantile(0.75)
    IQR = Q3 - Q1

    lower_bound = Q1 - 1.5 * IQR
    upper_bound = Q3 + 1.5 * IQR

    outliers = df[
        (df[col] < lower_bound) |
        (df[col] > upper_bound)
    ].copy()

    outliers["Outlier_Column"] = col

    all_outliers = pd.concat(
        [all_outliers, outliers],
        ignore_index=True
    )

    outlier_summary[col] = len(outliers)

# -----------------------------
# Print summary
# -----------------------------
print("\n===== Outlier Summary =====")

for col, count in outlier_summary.items():
    print(f"{col}: {count} outliers")

# -----------------------------
# Save results
# -----------------------------
summary_df = pd.DataFrame(
    list(outlier_summary.items()),
    columns=["Column", "Outlier_Count"]
)

summary_df.to_csv(
    "outlier_summary.csv",
    index=False
)

all_outliers.to_csv(
    "outliers_detected.csv",
    index=False
)

print("\nOutlier summary saved to 'outlier_summary.csv'")
print("Detailed outliers saved to 'outliers_detected.csv'")