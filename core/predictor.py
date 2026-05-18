import warnings
import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error

warnings.filterwarnings(
    "ignore",
    message=".*sklearn.utils.parallel.delayed.*",
    category=UserWarning,
)

DATA_PATH  = Path(__file__).parent.parent / "data" / "synthetic_campaigns.csv"
MODEL_PATH = Path(__file__).parent.parent / "data" / "model.joblib"

CATEGORICAL_COLS = [
    "sector", "cluster", "channel",
    "client_type", "goal", "audience_type", "priority",
]
NUMERIC_COLS = [
    "horizon_months", "age_min", "age_max", "budget_mad",
]
FEATURE_COLS = CATEGORICAL_COLS + NUMERIC_COLS
TARGET_CPL   = "actual_cpl"
TARGET_CONV  = "conv_rate"


# ─────────────────────────────────────────
# ENCODER
# ─────────────────────────────────────────

class CampaignEncoder:
    def __init__(self):
        self.encoders = {col: LabelEncoder() for col in CATEGORICAL_COLS}
        self.fitted   = False

    def fit(self, df: pd.DataFrame):
        for col, enc in self.encoders.items():
            enc.fit(df[col].astype(str))
        self.fitted = True
        return self

    def transform(self, df: pd.DataFrame) -> np.ndarray:
        parts = []
        for col in CATEGORICAL_COLS:
            val   = df[col].astype(str)
            known = set(self.encoders[col].classes_)
            val   = val.apply(
                lambda x: x if x in known
                else self.encoders[col].classes_[0]
            )
            parts.append(self.encoders[col].transform(val))
        for col in NUMERIC_COLS:
            parts.append(df[col].values)
        return np.column_stack(parts)

    def transform_single(self, row: dict) -> np.ndarray:
        return self.transform(pd.DataFrame([row]))


# ─────────────────────────────────────────
# TRAIN
# ─────────────────────────────────────────

def train(data_path: Path = DATA_PATH) -> dict:
    """
    Trains two Random Forest models (CPL + conversion rate).
    Also computes per-tree std on the test set so we can
    report confidence intervals on the model card.
    Saves everything to model.joblib.
    Returns a metrics dict.
    """
    df = pd.read_csv(data_path)
    print(f"Loaded {len(df)} training rows.")

    encoder = CampaignEncoder().fit(df)
    X       = encoder.transform(df)
    y_cpl   = df[TARGET_CPL].values
    y_conv  = df[TARGET_CONV].values

    X_train, X_test, y_cpl_train, y_cpl_test, y_conv_train, y_conv_test = \
        train_test_split(X, y_cpl, y_conv, test_size=0.2, random_state=42)

    model_cpl = RandomForestRegressor(
        n_estimators=200, max_depth=12,
        min_samples_leaf=5, random_state=42, n_jobs=-1,
    )
    model_cpl.fit(X_train, y_cpl_train)

    model_conv = RandomForestRegressor(
        n_estimators=200, max_depth=12,
        min_samples_leaf=5, random_state=42, n_jobs=-1,
    )
    model_conv.fit(X_train, y_conv_train)

    # ── MAE on test set ──────────────────────────────────
    cpl_preds  = model_cpl.predict(X_test)
    conv_preds = model_conv.predict(X_test)
    cpl_mae    = mean_absolute_error(y_cpl_test,  cpl_preds)
    conv_mae   = mean_absolute_error(y_conv_test, conv_preds)

    # ── Per-tree predictions → std (confidence interval) ─
    # Each tree gives its own prediction. The std across 200
    # trees is our uncertainty estimate for a given input.
    # We compute the mean std on the test set as a summary.
    cpl_tree_preds  = np.array([
        tree.predict(X_test) for tree in model_cpl.estimators_
    ])   # shape: (200, n_test)
    conv_tree_preds = np.array([
        tree.predict(X_test) for tree in model_conv.estimators_
    ])

    cpl_std_mean  = float(np.mean(np.std(cpl_tree_preds,  axis=0)))
    conv_std_mean = float(np.mean(np.std(conv_tree_preds, axis=0)))

    # ── R² scores ────────────────────────────────────────
    from sklearn.metrics import r2_score
    cpl_r2  = float(r2_score(y_cpl_test,  cpl_preds))
    conv_r2 = float(r2_score(y_conv_test, conv_preds))

    print(f"CPL  model — MAE: {cpl_mae:.2f} MAD | std: {cpl_std_mean:.2f} | R²: {cpl_r2:.3f}")
    print(f"Conv model — MAE: {conv_mae:.4f}    | std: {conv_std_mean:.4f} | R²: {conv_r2:.3f}")

    bundle = {
        "encoder":        encoder,
        "model_cpl":      model_cpl,
        "model_conv":     model_conv,
        # Stored metrics — shown on page 7 model card
        "metrics": {
            "n_train":        len(X_train),
            "n_test":         len(X_test),
            "cpl_mae":        round(cpl_mae,       2),
            "cpl_std":        round(cpl_std_mean,  2),
            "cpl_r2":         round(cpl_r2,        3),
            "conv_mae":       round(conv_mae,       4),
            "conv_std":       round(conv_std_mean,  4),
            "conv_r2":        round(conv_r2,        3),
        },
    }
    joblib.dump(bundle, MODEL_PATH)
    print(f"Model saved to {MODEL_PATH}")

    return bundle["metrics"]


# ─────────────────────────────────────────
# LOAD
# ─────────────────────────────────────────

_bundle = None

def _load_bundle():
    global _bundle
    if _bundle is None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                "Model not found. Run predictor.train() first."
            )
        _bundle = joblib.load(MODEL_PATH)
    return _bundle


def get_stored_metrics() -> dict:
    """
    Returns the metrics dict saved inside model.joblib.
    Used by the page 7 model card without re-running inference.
    Returns empty dict if model not found or old bundle without metrics.
    """
    try:
        bundle = _load_bundle()
        return bundle.get("metrics", {})
    except Exception:
        return {}


# ─────────────────────────────────────────
# PREDICT — single channel
# ─────────────────────────────────────────

def predict_channel(
    sector: str, cluster: str, channel: str,
    client_type: str, goal: str, audience_type: str,
    priority: str, horizon_months: int,
    age_min: int, age_max: int, budget_mad: float,
    fallback_cpl: float = None, fallback_conv: float = None,
) -> dict:
    """
    Predicts CPL and conversion rate for one channel.
    Returns predicted values + source ("model" or "fallback").
    """
    try:
        bundle  = _load_bundle()
        encoder = bundle["encoder"]
        row = {
            "sector":         sector,
            "cluster":        cluster,
            "channel":        channel,
            "client_type":    client_type,
            "goal":           goal,
            "audience_type":  audience_type or "professionals",
            "priority":       priority,
            "horizon_months": horizon_months,
            "age_min":        age_min,
            "age_max":        age_max,
            "budget_mad":     budget_mad,
        }
        X         = encoder.transform_single(row)
        pred_cpl  = float(bundle["model_cpl"].predict(X)[0])
        pred_conv = float(bundle["model_conv"].predict(X)[0])
        pred_cpl  = max(5.0,   min(pred_cpl,  2000.0))
        pred_conv = max(0.005, min(pred_conv, 0.30))
        return {
            "predicted_cpl":  round(pred_cpl,  2),
            "predicted_conv": round(pred_conv, 4),
            "source":         "model",
        }
    except Exception:
        return {
            "predicted_cpl":  fallback_cpl,
            "predicted_conv": fallback_conv,
            "source":         "fallback",
        }


# ─────────────────────────────────────────
# PREDICT WITH CONFIDENCE INTERVAL
# ─────────────────────────────────────────

def predict_channel_with_std(
    sector: str, cluster: str, channel: str,
    client_type: str, goal: str, audience_type: str,
    priority: str, horizon_months: int,
    age_min: int, age_max: int, budget_mad: float,
    fallback_cpl: float = None, fallback_conv: float = None,
) -> dict:
    """
    Like predict_channel() but also returns the standard deviation
    across the 200 Random Forest trees — our uncertainty estimate.

    Interpretation:
        CPL estimate:  pred_cpl ± cpl_std  (68% confidence interval)
        Conv estimate: pred_conv ± conv_std

    Returns:
        predicted_cpl   float  — mean CPL across all trees
        cpl_std         float  — std across trees (uncertainty)
        cpl_low         float  — pred_cpl - cpl_std
        cpl_high        float  — pred_cpl + cpl_std
        predicted_conv  float  — mean conversion rate
        conv_std        float  — std across trees
        source          str    — "model" or "fallback"
    """
    try:
        bundle  = _load_bundle()
        encoder = bundle["encoder"]
        row = {
            "sector":         sector,
            "cluster":        cluster,
            "channel":        channel,
            "client_type":    client_type,
            "goal":           goal,
            "audience_type":  audience_type or "professionals",
            "priority":       priority,
            "horizon_months": horizon_months,
            "age_min":        age_min,
            "age_max":        age_max,
            "budget_mad":     budget_mad,
        }
        X = encoder.transform_single(row)

        # Collect each tree's prediction
        cpl_tree_preds  = np.array([
            tree.predict(X)[0] for tree in bundle["model_cpl"].estimators_
        ])
        conv_tree_preds = np.array([
            tree.predict(X)[0] for tree in bundle["model_conv"].estimators_
        ])

        pred_cpl  = float(np.mean(cpl_tree_preds))
        cpl_std   = float(np.std(cpl_tree_preds))
        pred_conv = float(np.mean(conv_tree_preds))
        conv_std  = float(np.std(conv_tree_preds))

        # Apply sanity bounds
        pred_cpl  = max(5.0,   min(pred_cpl,  2000.0))
        cpl_low   = max(5.0,   pred_cpl - cpl_std)
        cpl_high  = min(2000.0, pred_cpl + cpl_std)
        pred_conv = max(0.005, min(pred_conv, 0.30))

        return {
            "predicted_cpl":  round(pred_cpl,  2),
            "cpl_std":        round(cpl_std,   2),
            "cpl_low":        round(cpl_low,   2),
            "cpl_high":       round(cpl_high,  2),
            "predicted_conv": round(pred_conv, 4),
            "conv_std":       round(conv_std,  4),
            "source":         "model",
        }

    except Exception:
        return {
            "predicted_cpl":  fallback_cpl,
            "cpl_std":        None,
            "cpl_low":        None,
            "cpl_high":       None,
            "predicted_conv": fallback_conv,
            "conv_std":       None,
            "source":         "fallback",
        }


# ─────────────────────────────────────────
# PREDICT — all channels (used by optimizer)
# ─────────────────────────────────────────

def predict_all_channels(
    campaign,       # CampaignInput
    scores_df,      # DataFrame from get_channel_scores()
) -> pd.DataFrame:
    """
    Runs predict_channel() for every channel in scores_df.
    Replaces cpl_mad and conversion_rate with ML predictions.
    Also stores cpl_std for downstream use.
    """
    cluster = campaign.clusters[0] if campaign.clusters else "maghreb"
    updated = scores_df.copy()

    for idx, row in updated.iterrows():
        result = predict_channel(
            sector         = campaign.sector,
            cluster        = cluster,
            channel        = row["channel"],
            client_type    = campaign.client_type,
            goal           = campaign.goal,
            audience_type  = campaign.audience_type or "professionals",
            priority       = campaign.priority,
            horizon_months = campaign.horizon_months,
            age_min        = campaign.age_min,
            age_max        = campaign.age_max,
            budget_mad     = campaign.total_budget,
            fallback_cpl   = row["cpl_mad"],
            fallback_conv  = row["conversion_rate"],
        )
        if result["source"] == "model":
            updated.at[idx, "cpl_mad"]        = result["predicted_cpl"]
            updated.at[idx, "conversion_rate"] = result["predicted_conv"]
            updated.at[idx, "score_source"]    = "ml"
        else:
            updated.at[idx, "score_source"]    = "csv"

    return updated