import pandas as pd
import matplotlib.pyplot as plt
from statsmodels.tsa.seasonal import seasonal_decompose
import os

# -----------------------------
# Load the dataset
# -----------------------------
file_path = "filled_dataset.csv"   # Use the dataset after handling missing values
df = pd.read_csv(file_path)

# -----------------------------
# Select signal column
# -----------------------------
# Change this to "red", "ir", "red_corrected", etc. as needed
signal_col = "ir"

# -----------------------------
# Create output directory
# -----------------------------
os.makedirs("plots", exist_ok=True)

# -----------------------------
# Perform seasonal decomposition
# -----------------------------
# Choose a period appropriate for your data.
# For PPG data, experiment with values such as 20, 50, or 100.
period = 50

result = seasonal_decompose(
    df[signal_col],
    model="additive",
    period=period,
    extrapolate_trend="freq"
)

# -----------------------------
# Plot decomposition
# -----------------------------
fig = result.plot()
fig.set_size_inches(12, 8)

plt.tight_layout()
plt.savefig(f"plots/{signal_col}_trend_seasonality.png")
plt.show()

# -----------------------------
# Save decomposition components
# -----------------------------
decomposition_df = pd.DataFrame({
    "Observed": result.observed,
    "Trend": result.trend,
    "Seasonal": result.seasonal,
    "Residual": result.resid
})

decomposition_df.to_csv(
    f"{signal_col}_decomposition.csv",
    index=False
)

print("Trend and seasonality analysis completed successfully.")
print(f"Results saved to '{signal_col}_decomposition.csv'")
print(f"Plot saved to 'plots/{signal_col}_trend_seasonality.png'")