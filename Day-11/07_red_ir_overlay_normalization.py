"""
File: 07_red_ir_overlay_normalization.py

Purpose:
--------
Superimpose Red and IR PPG signals after normalization/standardization
to compare their waveform shapes and variability in peak positions.

Input:
------
sakshi_ppg_20260611T074737_len148s(1).csv

Output:
-------
1. red_ir_standardized_overlay.png
2. red_ir_normalized_overlay.png
"""

import pandas as pd
import matplotlib.pyplot as plt
from sklearn.preprocessing import StandardScaler, MinMaxScaler


# -----------------------------
# Load Dataset
# -----------------------------
file_path = "sakshi_ppg_20260611T074737_len148s.csv"
df = pd.read_csv(file_path)

# -----------------------------
# Validate Required Columns
# -----------------------------
required_columns = ["timestamp_ms", "red", "ir"]

for col in required_columns:
    if col not in df.columns:
        raise ValueError(f"Missing required column: {col}")

# -----------------------------
# Standardization (Z-Score)
# -----------------------------
std_scaler = StandardScaler()

df["red_standardized"] = std_scaler.fit_transform(df[["red"]])
df["ir_standardized"] = std_scaler.fit_transform(df[["ir"]])

plt.figure(figsize=(12, 5))
plt.plot(
    df["timestamp_ms"],
    df["red_standardized"],
    label="Red (Standardized)"
)
plt.plot(
    df["timestamp_ms"],
    df["ir_standardized"],
    label="IR (Standardized)"
)

plt.title("Standardized Overlay of Red and IR Signals")
plt.xlabel("Timestamp (ms)")
plt.ylabel("Standardized Value")
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.savefig("red_ir_standardized_overlay.png")
plt.show()

# -----------------------------
# Min-Max Normalization
# -----------------------------
norm_scaler = MinMaxScaler()

df["red_normalized"] = norm_scaler.fit_transform(df[["red"]])
df["ir_normalized"] = norm_scaler.fit_transform(df[["ir"]])

plt.figure(figsize=(12, 5))
plt.plot(
    df["timestamp_ms"],
    df["red_normalized"],
    label="Red (Normalized)"
)
plt.plot(
    df["timestamp_ms"],
    df["ir_normalized"],
    label="IR (Normalized)"
)

plt.title("Normalized Overlay of Red and IR Signals")
plt.xlabel("Timestamp (ms)")
plt.ylabel("Normalized Value")
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.savefig("red_ir_normalized_overlay.png")
plt.show()

print("\nAnalysis completed successfully!")
print("Generated files:")
print(" - red_ir_standardized_overlay.png")
print(" - red_ir_normalized_overlay.png")