from pathlib import Path


def ensure_model_exists():
    """
    Checks if the ML model exists.
    If not, generates synthetic data and trains the model.
    Called once at app startup on Streamlit Cloud.
    """
    model_path = Path(__file__).parent.parent / "data" / "model.joblib"
    data_path  = Path(__file__).parent.parent / "data" / "synthetic_campaigns.csv"

    if model_path.exists():
        return  # already trained — nothing to do

    print("Model not found — generating training data and training...")

    # Generate synthetic data if missing
    if not data_path.exists():
        from core.data_generator import generate_campaign_data
        df = generate_campaign_data(n_samples=2000)
        data_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(data_path, index=False)
        print(f"Generated {len(df)} training rows.")

    # Train the model
    from core.predictor import train
    metrics = train()
    print(f"Model trained. CPL MAE: {metrics['cpl_mae']}")


def ensure_team_tables_exist():
    """
    Creates the freelancers and campaign_team tables in feedback.db
    if they don't already exist, and seeds freelancers from CSV
    on first run.
    Called once at app startup alongside ensure_model_exists().
    """
    from core.team_db import init_team_tables
    init_team_tables()

def ensure_task_tables_exist():
    from core.task_db import init_task_tables
    init_task_tables()