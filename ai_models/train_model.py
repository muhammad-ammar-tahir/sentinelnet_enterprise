"""AI Model Training and Evaluation Pipeline for SentinelNet.

Trains:
1. `IsolationForest` (Unsupervised anomaly detection with contamination=0.05).
2. `RandomForestClassifier` (Supervised classification baseline).
Evaluates honest per-class metrics, false positive rates, PR-AUC, ROC-AUC,
confusion matrix, and detection latency.

Clearly documents synthetic dataset provenance and disclaims real-world generalizability.
"""

import os
import sys
import time
import json
import logging
from pathlib import Path
from typing import Dict, Any

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import joblib
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    precision_recall_fscore_support,
    roc_auc_score,
    precision_recall_curve,
    auc,
)

try:
    from ai_models.preprocessing import Preprocessor
    from ai_models.generate_training_data import generate_synthetic_telemetry
except ImportError:
    from preprocessing import Preprocessor
    from generate_training_data import generate_synthetic_telemetry

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("sentinelnet.train")


def train_and_evaluate(
    data_path: str = "ai_models/data/training_data.csv",
    unsupervised_model_path: str = "ai_models/trained_model.pkl",
    supervised_model_path: str = "ai_models/supervised_model.pkl",
    evaluation_path: str = "ai_models/evaluation.json",
    contamination: float = 0.05,
    random_state: int = 42
) -> Dict[str, Any]:
    """Execute complete end-to-end model training, honest evaluation, and artifact serialization."""
    logger.info("================================================================")
    logger.info("   SentinelNet AI Model Training Pipeline Starting")
    logger.info("================================================================")

    # 1. Check or generate training data
    if not os.path.exists(data_path):
        logger.warning("Training data '%s' not found. Generating fresh 10,000 samples...", data_path)
        generate_synthetic_telemetry(num_rows=10000, anomaly_ratio=contamination, output_path=data_path)

    # 2. Preprocess with strict data-leakage prevention (fit scaler on train ONLY)
    preprocessor = Preprocessor()
    preprocessor.load(data_path)
    preprocessor.clean()
    X_train, X_test, y_train, y_test = preprocessor.split_train_test(test_size=0.2, random_state=random_state)

    # -------------------------------------------------------------------------
    # 3. Model 1: Unsupervised Isolation Forest
    # -------------------------------------------------------------------------
    logger.info("Training Isolation Forest (contamination=%.2f, n_estimators=100)...", contamination)
    iso_start = time.perf_counter()
    iso_forest = IsolationForest(
        contamination=contamination,
        n_estimators=100,
        random_state=random_state,
        n_jobs=-1
    )
    iso_forest.fit(X_train)
    iso_train_time_sec = round(time.perf_counter() - iso_start, 3)

    # Measure inference detection time
    infer_start = time.perf_counter()
    raw_preds = iso_forest.predict(X_test)
    iso_infer_time_ms = round((time.perf_counter() - infer_start) * 1000.0 / len(X_test), 4)

    y_pred_iso = np.where(raw_preds == -1, 1, 0)
    iso_scores = -iso_forest.score_samples(X_test)  # Inverted: higher = more anomalous

    # Per-class metrics
    p_iso, r_iso, f1_iso, _ = precision_recall_fscore_support(y_test, y_pred_iso, average="binary", zero_division=0)
    cm_iso = confusion_matrix(y_test, y_pred_iso)
    tn, fp, fn, tp = cm_iso.ravel()

    # False positive rate (FPR) = FP / (FP + TN)
    fpr_iso = float(fp / (fp + tn)) if (fp + tn) > 0 else 0.0

    # ROC-AUC and PR-AUC
    auc_iso = float(roc_auc_score(y_test, iso_scores))
    precision_curve, recall_curve, _ = precision_recall_curve(y_test, iso_scores)
    pr_auc_iso = float(auc(recall_curve, precision_curve))

    logger.info(">>> Isolation Forest Honest Evaluation:")
    logger.info("    Precision:          %.4f", p_iso)
    logger.info("    Recall:             %.4f", r_iso)
    logger.info("    F1 Score:           %.4f", f1_iso)
    logger.info("    False Positive Rate:%.4f (%.2f%%)", fpr_iso, fpr_iso * 100)
    logger.info("    ROC-AUC:            %.4f", auc_iso)
    logger.info("    PR-AUC:             %.4f", pr_auc_iso)
    logger.info("    Avg Detection Time: %.4f ms/sample", iso_infer_time_ms)
    logger.info("    Confusion Matrix (TN=%d, FP=%d, FN=%d, TP=%d)", tn, fp, fn, tp)

    # -------------------------------------------------------------------------
    # 4. Model 2: Supervised Random Forest Classifier (Benchmark)
    # -------------------------------------------------------------------------
    logger.info("Training Supervised Random Forest Classifier...")
    rf_start = time.perf_counter()
    rf_clf = RandomForestClassifier(
        n_estimators=100,
        random_state=random_state,
        class_weight="balanced",
        n_jobs=-1
    )
    rf_clf.fit(X_train, y_train)
    rf_train_time_sec = round(time.perf_counter() - rf_start, 3)

    infer_start_rf = time.perf_counter()
    y_pred_rf = rf_clf.predict(X_test)
    rf_infer_time_ms = round((time.perf_counter() - infer_start_rf) * 1000.0 / len(X_test), 4)
    y_prob_rf = rf_clf.predict_proba(X_test)[:, 1]

    p_rf, r_rf, f1_rf, _ = precision_recall_fscore_support(y_test, y_pred_rf, average="binary", zero_division=0)
    cm_rf = confusion_matrix(y_test, y_pred_rf)
    tn_rf, fp_rf, fn_rf, tp_rf = cm_rf.ravel()
    fpr_rf = float(fp_rf / (fp_rf + tn_rf)) if (fp_rf + tn_rf) > 0 else 0.0

    auc_rf = float(roc_auc_score(y_test, y_prob_rf))
    pr_curve_rf, rec_curve_rf, _ = precision_recall_curve(y_test, y_prob_rf)
    pr_auc_rf = float(auc(rec_curve_rf, pr_curve_rf))

    # -------------------------------------------------------------------------
    # 5. Save Artifacts & Honest Evaluation JSON
    # -------------------------------------------------------------------------
    os.makedirs(os.path.dirname(unsupervised_model_path), exist_ok=True)
    joblib.dump(iso_forest, unsupervised_model_path)
    joblib.dump(rf_clf, supervised_model_path)

    # Save model metadata / version
    meta_path = "ai_models/model_version.json"
    with open(meta_path, "w") as f_meta:
        json.dump({
            "version": "1.2.0-synthetic-baseline",
            "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "algorithm": "IsolationForest",
            "features": preprocessor.get_feature_columns(),
            "contamination": contamination
        }, f_meta, indent=2)

    evaluation_report = {
        "status": "synthetic_baseline_evaluation",
        "benchmark_notice": (
            "NOTICE: The evaluation metrics below reflect performance on controlled, "
            "synthetically generated Mininet campus telemetry. Real-world network deployments "
            "exhibit non-Gaussian noise, bursty human traffic, and overlapping fault modes; "
            "expected production accuracy will be lower than this laboratory baseline."
        ),
        "dataset_provenance": {
            "source": "ai_models/generate_training_data.py",
            "type": "synthetic_telemetry_simulation",
            "environment": "Mininet SDN University Campus Topology (S1, S2, S3)",
            "total_samples": len(X_train) + len(X_test),
            "train_samples": len(X_train),
            "test_samples": len(X_test),
            "anomaly_ratio": contamination,
            "data_leakage_prevented": True,
            "scaling_strategy": "fit_on_train_only"
        },
        "features": preprocessor.get_feature_columns(),
        "isolation_forest_unsupervised": {
            "model_type": "IsolationForest",
            "train_duration_sec": iso_train_time_sec,
            "avg_detection_latency_ms": iso_infer_time_ms,
            "metrics": {
                "precision": round(float(p_iso), 4),
                "recall": round(float(r_iso), 4),
                "f1_score": round(float(f1_iso), 4),
                "false_positive_rate": round(fpr_iso, 4),
                "roc_auc": round(auc_iso, 4),
                "pr_auc": round(pr_auc_iso, 4)
            },
            "per_class": {
                "normal": {
                    "support": int(tn + fp),
                    "true_negatives": int(tn),
                    "false_positives": int(fp)
                },
                "anomaly": {
                    "support": int(fn + tp),
                    "true_positives": int(tp),
                    "false_negatives": int(fn)
                }
            },
            "confusion_matrix": {
                "TN": int(tn),
                "FP": int(fp),
                "FN": int(fn),
                "TP": int(tp)
            }
        },
        "random_forest_supervised": {
            "model_type": "RandomForestClassifier",
            "train_duration_sec": rf_train_time_sec,
            "avg_detection_latency_ms": rf_infer_time_ms,
            "metrics": {
                "precision": round(float(p_rf), 4),
                "recall": round(float(r_rf), 4),
                "f1_score": round(float(f1_rf), 4),
                "false_positive_rate": round(fpr_rf, 4),
                "roc_auc": round(auc_rf, 4),
                "pr_auc": round(pr_auc_rf, 4)
            },
            "confusion_matrix": {
                "TN": int(tn_rf),
                "FP": int(fp_rf),
                "FN": int(fn_rf),
                "TP": int(tp_rf)
            }
        }
    }

    with open(evaluation_path, "w") as f_json:
        json.dump(evaluation_report, f_json, indent=2)

    logger.info("Honest evaluation metrics successfully exported to '%s'", evaluation_path)
    logger.info("================================================================")
    logger.info("   Training Pipeline Complete")
    logger.info("================================================================")
    return evaluation_report


if __name__ == "__main__":
    train_and_evaluate()
