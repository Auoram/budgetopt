from core.data_model import CampaignInput
from core.optimizer import optimize, AllocationResult


def pipeline(campaign: CampaignInput) -> AllocationResult:
    """
    The single entry point for both websites.

    Takes a fully populated CampaignInput and returns
    an AllocationResult with the complete budget allocation.

    Usage:
        from core.pipeline import pipeline
        result = pipeline(campaign)

    The Streamlit form creates the CampaignInput from
    form fields and calls this.

    The LangChain agent extracts a CampaignInput from
    natural language and calls this.

    Neither website needs to import scoring.py,
    predictor.py, or optimizer.py directly.
    """
    return optimize(campaign)