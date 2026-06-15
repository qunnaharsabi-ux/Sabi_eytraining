import pandas as pd

# -----------------------------
# Load the dataset
# -----------------------------
file_path = "sakshi_ppg_20260611T074737_len148s.csv"   # Update path if needed
df = pd.read_csv(file_path)

# -----------------------------
# Display basic information
# -----------------------------
print("Dataset Shape:", df.shape)
print("\nColumns:")
print(df.columns.tolist())

# -----------------------------
# Select numeric columns
# -----------------------------
numeric_df = df.select_dtypes(include=["number"])

# -----------------------------
# Calculate statistics
# -----------------------------
mean_values = numeric_df.mean()
std_values = numeric_df.std()
mode_values = numeric_df.mode().iloc[0]

# -----------------------------
# Create summary DataFrame
# -----------------------------
summary = pd.DataFrame({
    "Mean": mean_values,
    "Standard Deviation": std_values,
    "Mode": mode_values
})

# -----------------------------
# Print results
# -----------------------------
print("\n===== Basic Statistics =====")
print(summary)

# -----------------------------
# Save to CSV
# -----------------------------
summary.to_csv("basic_statistics.csv")

print("\nStatistics saved to 'basic_statistics.csv'")