"""Telemetry Data Preprocessing Module for SentinelNet.

Provides the `Preprocessor` class to clean, clip outliers, normalize,
and partition network telemetry data for ML model training and inference.
Fixes data leakage by fitting the scaler STRICTLY on training split only.
"""

import os
import logging
from typing import List, Tuple, Optional
import pandas as pd
import numpy as np
import joblib
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split

logger = logging.getLogger("sentinelnet.preprocessing")


class Preprocessor:
    """Handles data ingestion, validation, outlier clipping, and scaling for network telemetry."""

    NUMERIC_FEATURES: List[str] = [
        "latency_ms",
        "packet_loss_pct",
        "cpu_pct",
        "memory_pct",
        "bandwidth_mbps",
        "interface_up",
        "error_count"
    ]

    def __init__(self, scaler_path: str = "ai_models/scaler.pkl"):
        """Initialize Preprocessor with optional persistent scaler path."""
        self.scaler_path = scaler_path
        self.scaler = StandardScaler()
        self.is_fitted = False
        self.df: Optional[pd.DataFrame] = None
        logger.info("Preprocessor initialized (scaler_path=%s)", self.scaler_path)

    def get_feature_columns(self) -> List[str]:
        """Return the list of numeric feature column names expected by the ML models."""
        return list(self.NUMERIC_FEATURES)

    def load(self, path: str = "ai_models/data/training_data.csv") -> pd.DataFrame:
        """Load telemetry CSV from filesystem into a pandas DataFrame."""
        if not os.path.exists(path):
            raise FileNotFoundError(f"Telemetry dataset not found at '{path}'.")
        self.df = pd.read_csv(path)
        logger.info("Loaded %d rows and %d columns from %s", len(self.df), len(self.df.columns), path)
        return self.df

    def clean(self, df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        """Clean dataset by dropping nulls, validating types, and clipping extreme physical bounds."""
        target_df = self.df if df is None else df
        if target_df is None:
            raise ValueError("No DataFrame loaded to clean.")

        cleaned = target_df.copy()
        # Drop rows with missing values
        cleaned.dropna(subset=self.NUMERIC_FEATURES, inplace=True)

        # Enforce realistic physiological bounds (clip outliers)
        cleaned["latency_ms"] = cleaned["latency_ms"].clip(lower=0.0, upper=1000.0)
        cleaned["packet_loss_pct"] = cleaned["packet_loss_pct"].clip(lower=0.0, upper=100.0)
        cleaned["cpu_pct"] = cleaned["cpu_pct"].clip(lower=0.0, upper=100.0)
        cleaned["memory_pct"] = cleaned["memory_pct"].clip(lower=0.0, upper=100.0)
        cleaned["bandwidth_mbps"] = cleaned["bandwidth_mbps"].clip(lower=0.0, upper=1000.0)
        cleaned["interface_up"] = cleaned["interface_up"].clip(lower=0, upper=1)
        cleaned["error_count"] = cleaned["error_count"].clip(lower=0, upper=10000)

        if df is None:
            self.df = cleaned
        logger.info("Dataset cleaned. Retained %d valid samples.", len(cleaned))
        return cleaned

    def scale(self, X: np.ndarray, fit: bool = True) -> np.ndarray:
        """Standardize feature matrix X using StandardScaler (zero mean, unit variance).

        Args:
            X: 2D numpy array [n_samples, n_features].
            fit: If True, fits scaler on X and saves to disk. If False, transforms using fitted scaler.

        Returns:
            np.ndarray: Scaled feature array.
        """
        if fit:
            X_scaled = self.scaler.fit_transform(X)
            self.is_fitted = True
            # Save fitted scaler
            os.makedirs(os.path.dirname(self.scaler_path) if os.path.dirname(self.scaler_path) else ".", exist_ok=True)
            joblib.dump(self.scaler, self.scaler_path)
            logger.info("Scaler fitted and saved to '%s'", self.scaler_path)
            return X_scaled
        else:
            if not self.is_fitted:
                self.load_scaler()
            return self.scaler.transform(X)

    def load_scaler(self) -> StandardScaler:
        """Load existing fitted scaler from disk."""
        if not os.path.exists(self.scaler_path):
            raise FileNotFoundError(f"Fitted scaler not found at '{self.scaler_path}'.")
        self.scaler = joblib.load(self.scaler_path)
        self.is_fitted = True
        logger.info("Fitted scaler loaded from '%s'", self.scaler_path)
        return self.scaler

    def split_train_test(
        self,
        test_size: float = 0.2,
        random_state: int = 42
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Extract features and labels, partition train/test BEFORE scaling, and fit scaler ONLY on train.

        Prevents data leakage from test set into training feature space.
        """
        if self.df is None:
            raise ValueError("No dataset loaded. Call load() first.")

        X_raw = self.df[self.NUMERIC_FEATURES].values
        y = self.df["is_anomaly"].values if "is_anomaly" in self.df.columns else np.zeros(len(self.df))

        # 1. Split FIRST on raw unscaled features
        X_train_raw, X_test_raw, y_train, y_test = train_test_split(
            X_raw, y, test_size=test_size, random_state=random_state, stratify=y
        )

        # 2. Fit scaler ONLY on X_train_raw
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train_raw)

        # 3. Transform X_test_raw using train-fitted scaler (NEVER fit on test)
        X_test_scaled = scaler.transform(X_test_raw)

        # 4. Save fitted scaler for production inference
        self.scaler = scaler
        self.is_fitted = True
        os.makedirs(os.path.dirname(self.scaler_path) if os.path.dirname(self.scaler_path) else ".", exist_ok=True)
        joblib.dump(self.scaler, self.scaler_path)
        logger.info("Scaler fitted strictly on training set (%d samples) and saved to '%s'", len(X_train_raw), self.scaler_path)

        logger.info(
            "Split dataset without leakage into Train: %d samples, Test: %d samples (test_size=%.2f)",
            len(X_train_scaled), len(X_test_scaled), test_size
        )
        return X_train_scaled, X_test_scaled, y_train, y_test

    def save_processed(
        self,
        X_train: np.ndarray,
        X_test: np.ndarray,
        y_train: np.ndarray,
        y_test: np.ndarray,
        output_dir: str = "ai_models/data"
    ) -> None:
        """Save train/test numpy arrays to disk for fast experimentation."""
        os.makedirs(output_dir, exist_ok=True)
        np.save(os.path.join(output_dir, "X_train.npy"), X_train)
        np.save(os.path.join(output_dir, "X_test.npy"), X_test)
        np.save(os.path.join(output_dir, "y_train.npy"), y_train)
        np.save(os.path.join(output_dir, "y_test.npy"), y_test)
        logger.info("Processed data matrices saved to '%s'", output_dir)
