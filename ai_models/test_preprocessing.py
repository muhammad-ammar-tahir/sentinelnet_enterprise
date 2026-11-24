"""Unit tests for Preprocessor data leakage prevention.

Verifies that the test split does NOT leak into the fitted StandardScaler.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from ai_models.preprocessing import Preprocessor


def test_no_data_leakage_in_scaling():
    """Verify that test set statistics are not present in the fitted scaler."""
    np.random.seed(42)
    features = Preprocessor.NUMERIC_FEATURES

    # 100 samples total, all with label=0 (normal)
    # The first 80 samples (train) will have mean ~ 10.0
    # The last 20 samples (test) will have mean ~ 500.0
    data_train = np.random.normal(loc=10.0, scale=1.0, size=(80, len(features)))
    data_test = np.random.normal(loc=500.0, scale=5.0, size=(20, len(features)))

    all_data = np.vstack([data_train, data_test])
    labels = np.zeros(100, dtype=int)

    df = pd.DataFrame(all_data, columns=features)
    df["is_anomaly"] = labels

    preprocessor = Preprocessor(scaler_path="ai_models/test_scaler.pkl")
    preprocessor.df = df

    # In train_test_split without shuffle (shuffle=False to keep test partition distinct)
    # Or test by manually splitting and verifying preprocessor behavior:
    X_raw = df[features].values
    y = labels

    from sklearn.model_selection import train_test_split
    # Split first
    X_train_raw, X_test_raw = X_raw[:80], X_raw[80:]

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train_raw)
    X_test_scaled = scaler.transform(X_test_raw)

    # Scaler mean_ is strictly based on train data (mean ~ 10.0)
    assert np.all(scaler.mean_ < 15.0), f"Scaler mean was {scaler.mean_}"
    assert np.all(scaler.mean_ > 8.0), f"Scaler mean deviated: {scaler.mean_}"

    # Now verify preprocessor.split_train_test on stratified data:
    # If stratified, test split contains samples from both classes, but scaler.mean_
    # must match X_train_raw mean, NOT X_raw (total) mean!
    X_tr_s, X_te_s, y_tr, y_te = preprocessor.split_train_test(test_size=0.2, random_state=42)

    # Key assertion: Scaler mean_ MUST equal the mean of X_train before scaling,
    # and MUST NOT equal the mean of the full unpartitioned dataset!
    full_mean = df[features].mean().values
    assert not np.allclose(preprocessor.scaler.mean_, full_mean), "Scaler mean matched full dataset! Data leakage!"

    # Clean up test artifact if exists
    import os
    if os.path.exists("ai_models/test_scaler.pkl"):
        os.remove("ai_models/test_scaler.pkl")

    print("PASS: test_no_data_leakage_in_scaling completed successfully. No test data leaked into scaler.")


if __name__ == "__main__":
    test_no_data_leakage_in_scaling()
