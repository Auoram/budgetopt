import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error

DATA_PATH  = Path(__file__).parent.parent / "data" / "synthetic_campaigns.csv"
MODEL_PATH = Path(__file__).parent.parent / "data" / "model.joblib"


# ─────────────────────────────────────────
# FEATURE COLUMNS
# These are the inputs the model sees.
# Must match exactly what we encode below.
# ─────────────────────────────────────────

CATEGORICAL_COLS = [
    "sector", "cluster", "channel",
    "client_type", "goal", "audience_type", "priority",
]
NUMERIC_COLS = [
    "horizon_months", "age_min", "age_max", "budget_mad",
]
FEATURE_COLS = CATEGORICAL_COLS + NUMERIC_COLS

TARGET_CPL  = "actual_cpl"
TARGET_CONV = "conv_rate"


# ─────────────────────────────────────────
# ENCODER
# Converts string columns to numbers.
# Saved alongside the model so we can
# encode new inputs at prediction time.
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
            val = df[col].astype(str)
            # Handle unseen labels gracefully
            known = set(self.encoders[col].classes_)
            val   = val.apply(lambda x: x if x in known else
                              self.encoders[col].classes_[0])
            parts.append(self.encoders[col].transform(val))
        for col in NUMERIC_COLS:
            parts.append(df[col].values)
        return np.column_stack(parts)

    def transform_single(self, row: dict) -> np.ndarray:
        df = pd.DataFrame([row])
        return self.transform(df)


# ─────────────────────────────────────────
# TRAIN
# Call this once to train and save the
# model. You don't need to call it again
# unless you add new training data.
# ─────────────────────────────────────────

def train(data_path: Path = DATA_PATH) -> dict:
    """
    Loads synthetic_campaigns.csv, trains two Random Forest
    models (one for CPL, one for conversion rate), saves
    everything to data/model.joblib.

    Returns a dict with evaluation metrics.
    """
    df = pd.read_csv(data_path)
    print(f"Loaded {len(df)} training rows.")

    # Encode features
    encoder = CampaignEncoder().fit(df)
    X = encoder.transform(df)
    y_cpl  = df[TARGET_CPL].values
    y_conv = df[TARGET_CONV].values

    # Train/test split
    X_train, X_test, y_cpl_train, y_cpl_test, y_conv_train, y_conv_test = \
        train_test_split(X, y_cpl, y_conv,
                         test_size=0.2, random_state=42)

    # Train CPL model
    model_cpl = RandomForestRegressor(
        n_estimators=200,
        max_depth=12,
        min_samples_leaf=5,
        random_state=42,
        n_jobs=-1,
    )
    model_cpl.fit(X_train, y_cpl_train)

    # Train conversion rate model
    model_conv = RandomForestRegressor(
        n_estimators=200,
        max_depth=12,
        min_samples_leaf=5,
        random_state=42,
        n_jobs=-1,
    )
    model_conv.fit(X_train, y_conv_train)

    # Evaluate
    cpl_mae  = mean_absolute_error(y_cpl_test,
                                   model_cpl.predict(X_test))
    conv_mae = mean_absolute_error(y_conv_test,
                                   model_conv.predict(X_test))

    print(f"CPL model  MAE: {cpl_mae:.2f} MAD")
    print(f"Conv model MAE: {conv_mae:.4f}")

    # Save everything in one file
    bundle = {
        "encoder":    encoder,
        "model_cpl":  model_cpl,
        "model_conv": model_conv,
    }
    joblib.dump(bundle, MODEL_PATH)
    print(f"Model saved to {MODEL_PATH}")

    return {
        "n_train":  len(X_train),
        "n_test":   len(X_test),
        "cpl_mae":  round(cpl_mae, 2),
        "conv_mae": round(conv_mae, 4),
    }


# ─────────────────────────────────────────
# PREDICT
# Given a campaign + channel, returns
# predicted CPL and conversion rate.
# Falls back to CSV values if model
# is not loaded or prediction is bad.
# ─────────────────────────────────────────

_bundle = None  # module-level cache

def _load_bundle():
    global _bundle
    if _bundle is None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                "Model not found. Run predictor.train() first."
            )
        _bundle = joblib.load(MODEL_PATH)
    return _bundle


def predict_channel(
    sector:         str,
    cluster:        str,
    channel:        str,
    client_type:    str,
    goal:           str,
    audience_type:  str,
    priority:       str,
    horizon_months: int,
    age_min:        int,
    age_max:        int,
    budget_mad:     float,
    fallback_cpl:   float = None,
    fallback_conv:  float = None,
) -> dict:
    """
    Predicts CPL and conversion rate for one channel.

    Returns:
        {
            "predicted_cpl":  float,   # MAD per lead
            "predicted_conv": float,   # conversion rate 0-1
            "source":         str,     # "model" or "fallback"
        }
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

        pred_cpl  = float(bundle["model_cpl"].predict(X)[0])
        pred_conv = float(bundle["model_conv"].predict(X)[0])

        # Sanity bounds — reject nonsensical predictions
        pred_cpl  = max(5.0, min(pred_cpl, 2000.0))
        pred_conv = max(0.005, min(pred_conv, 0.30))

        return {
            "predicted_cpl":  round(pred_cpl, 2),
            "predicted_conv": round(pred_conv, 4),
            "source":         "model",
        }

    except Exception:
        # If anything fails, fall back to CSV values
        return {
            "predicted_cpl":  fallback_cpl,
            "predicted_conv": fallback_conv,
            "source":         "fallback",
        }


def predict_all_channels(
    campaign,         # CampaignInput
    scores_df,        # DataFrame from get_channel_scores()
) -> pd.DataFrame:
    """
    Runs predict_channel() for every channel in scores_df.
    Replaces cpl_mad and conversion_rate with ML predictions
    when the model is confident (source == 'model').
    Returns the updated scores_df.
    """
    # Average cluster if multiple countries selected
    # (use first cluster for prediction — good enough)
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
            updated.at[idx, "cpl_mad"]         = result["predicted_cpl"]
            updated.at[idx, "conversion_rate"]  = result["predicted_conv"]
            updated.at[idx, "score_source"]     = "ml"
        else:
            updated.at[idx, "score_source"]     = "csv"

    return updated