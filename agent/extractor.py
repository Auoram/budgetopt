import json
import re
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage
from langsmith import traceable
from core.data_model import (
    SECTORS, COUNTRIES, CHANNELS, GOALS,
    PRIORITIES, AUDIENCE_TYPES, CampaignInput,
)


# ─────────────────────────────────────────
# PYDANTIC SCHEMA
# ─────────────────────────────────────────

class ExtractedCampaign(BaseModel):
    """
    Structured campaign parameters extracted
    from a natural language user message.
    """

    company_name: str = Field(
        default="Unknown",
        description=(
            "Name of the company or product. "
            "If not mentioned, use 'Unknown'."
        ),
    )

    sector: str = Field(
        default="fintech",
        description=(
            "Industry sector. Must be exactly one of: "
            f"{', '.join(SECTORS)}. "
            "Map: 'bank/payment/wallet'→fintech, "
            "'shop/store/retail'→ecommerce, "
            "'software/platform/app'→saas, "
            "'school/course/training'→education, "
            "'clinic/hospital/wellness'→health. "
            "Default: fintech."
        ),
    )

    target_countries: List[str] = Field(
        default_factory=lambda: ["Morocco"],
        description=(
            "List of target countries. Each must be exactly from: "
            f"{', '.join(list(COUNTRIES.keys()))}. "
            "Map regions: "
            "'Gulf/GCC'→['Saudi Arabia','UAE','Kuwait'], "
            "'Maghreb'→['Morocco','Algeria','Tunisia'], "
            "'MENA'→['Morocco','Egypt','Saudi Arabia','UAE'], "
            "'Europe'→['France','Germany','UK','Spain']. "
            "City names → their country (Casablanca→Morocco). "
            "Default: ['Morocco']."
        ),
    )

    client_type: str = Field(
        default="b2c",
        description=(
            "Must be exactly 'b2c' or 'b2b'. "
            "B2B = selling to businesses. "
            "B2C = selling to consumers. "
            "Default: b2c."
        ),
    )

    age_min: int = Field(
        default=18,
        description=(
            "Minimum target audience age. Integer 18-60. "
            "Map: 'young/youth/Gen Z'→18, "
            "'young adults'→20, 'professionals'→25, "
            "'seniors'→50. Default: 18."
        ),
    )

    age_max: int = Field(
        default=45,
        description=(
            "Maximum target audience age. Integer 18-60. "
            "Must be greater than age_min. "
            "Map: 'young adults'→35, 'professionals'→55, "
            "'all ages'→60. Default: 45."
        ),
    )

    audience_type: str = Field(
        default="professionals",
        description=(
            "Must be exactly one of: "
            f"{', '.join(AUDIENCE_TYPES)}. "
            "Map: 'students/youth/Gen Z/young people'→students, "
            "'workers/employees/managers'→professionals, "
            "'entrepreneurs/CEOs/founders/owners'→business_owners. "
            "NEVER use gender words (women, men, females, males) — "
            "map them to the closest type: "
            "women 25-40 → professionals, young men → students, "
            "male CEOs → business_owners. "
            "Default: professionals."
        ),
    )

    goal: str = Field(
        default="generate_leads",
        description=(
            "Campaign objective. Must be exactly one of: "
            f"{', '.join(GOALS)}. "
            "Map: 'get clients/sign-ups/leads/registrations'"
            "→generate_leads, "
            "'sell/revenue/purchases/sales'→increase_sales, "
            "'awareness/visibility/reach/branding'→brand_awareness. "
            "Default: generate_leads."
        ),
    )

    horizon_months: int = Field(
        default=3,
        description=(
            "Campaign duration in months. Integer 1-12. "
            "Map: 'short term'→2, '1 quarter/Q1'→3, "
            "'half year/6 months'→6, 'annual/1 year'→12. "
            "Default: 3."
        ),
    )

    priority: str = Field(
        default="high_quality",
        description=(
            "Optimization priority. Must be exactly one of: "
            f"{', '.join(PRIORITIES)}. "
            "Map: 'cheap/affordable/low cost/budget'→low_cost, "
            "'many leads/volume/scale/reach'→high_volume, "
            "'quality/conversion/ROI/qualified'→high_quality. "
            "Default: high_quality."
        ),
    )

    total_budget: Optional[float] = Field(
        default=None,
        description=(
            "Total marketing budget as a number in MAD. "
            "Convert: 1 USD=10 MAD, 1 EUR=11 MAD, 1 GBP=13 MAD. "
            "Examples: '5M MAD'→5000000, '500K'→500000, "
            "'$50,000'→500000, '200K euros'→2200000. "
            "If no budget mentioned at all, return null."
        ),
    )

    allowed_channels: List[str] = Field(
        default_factory=list,
        description=(
            "Channels to use. Each must be exactly one of: "
            f"{', '.join(CHANNELS)}. "
            "Map: 'social media/social'→"
            "['facebook','instagram','tiktok'], "
            "'search'→['google_ads'], "
            "'professional/b2b'→['linkedin','google_ads'], "
            "'all channels/everything'→"
            "['facebook','instagram','google_ads','email','seo','tiktok','linkedin']. "
            "If channels not mentioned, return empty list []."
        ),
    )

    max_pct_per_channel: float = Field(
        default=0.5,
        description=(
            "Max fraction of budget for one channel. Float 0.1-1.0. "
            "Map: 'no more than 40%'→0.4, 'max 60%'→0.6. "
            "Default: 0.5."
        ),
    )

    # ── Validators ────────────────────────────────────────

    @field_validator("sector")
    @classmethod
    def validate_sector(cls, v):
        v = v.lower().strip()
        return v if v in SECTORS else "fintech"

    @field_validator("client_type")
    @classmethod
    def validate_client_type(cls, v):
        v = v.lower().strip()
        return v if v in ["b2c", "b2b"] else "b2c"

    @field_validator("goal")
    @classmethod
    def validate_goal(cls, v):
        v = v.lower().strip()
        return v if v in GOALS else "generate_leads"

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v):
        v = v.lower().strip()
        return v if v in PRIORITIES else "high_quality"

    @field_validator("target_countries")
    @classmethod
    def validate_countries(cls, v):
        valid = [c for c in v if c in COUNTRIES]
        return valid if valid else ["Morocco"]

    @field_validator("allowed_channels")
    @classmethod
    def validate_channels(cls, v):
        return [c for c in v if c in CHANNELS]

    @field_validator("audience_type")
    @classmethod
    def validate_audience_type(cls, v):
        v = v.lower().strip()
        if v in AUDIENCE_TYPES:
            return v
        mapping = {
            "females":          "professionals",
            "female":           "professionals",
            "women":            "professionals",
            "woman":            "professionals",
            "males":            "professionals",
            "male":             "professionals",
            "men":              "professionals",
            "man":              "professionals",
            "youth":            "students",
            "young":            "students",
            "teens":            "students",
            "teenagers":        "students",
            "gen z":            "students",
            "genz":             "students",
            "young adults":     "students",
            "young people":     "students",
            "adults":           "professionals",
            "managers":         "professionals",
            "employees":        "professionals",
            "workers":          "professionals",
            "executives":       "professionals",
            "consumers":        "professionals",
            "entrepreneurs":    "business_owners",
            "ceos":             "business_owners",
            "ceo":              "business_owners",
            "founders":         "business_owners",
            "founder":          "business_owners",
            "owners":           "business_owners",
            "owner":            "business_owners",
            "decision makers":  "business_owners",
            "decision-makers":  "business_owners",
            "b2b":              "business_owners",
        }
        return mapping.get(v, "professionals")

    @field_validator("age_min")
    @classmethod
    def validate_age_min(cls, v):
        return max(18, min(60, int(v)))

    @field_validator("age_max")
    @classmethod
    def validate_age_max(cls, v):
        return max(18, min(60, int(v)))

    @field_validator("max_pct_per_channel")
    @classmethod
    def validate_max_pct(cls, v):
        return max(0.1, min(1.0, float(v)))

    @field_validator("horizon_months")
    @classmethod
    def validate_horizon(cls, v):
        return max(1, min(12, int(v)))

    # ── Convert to CampaignInput ──────────────────────────

    def to_campaign_input(self) -> CampaignInput:
        age_max = max(self.age_min + 5, self.age_max)
        channels = (
            self.allowed_channels
            if self.allowed_channels
            else list(CHANNELS)
        )
        return CampaignInput(
            company_name        = self.company_name,
            sector              = self.sector,
            target_countries    = self.target_countries,
            client_type         = self.client_type,
            age_min             = self.age_min,
            age_max             = age_max,
            audience_type       = self.audience_type,
            goal                = self.goal,
            horizon_months      = self.horizon_months,
            priority            = self.priority,
            total_budget        = float(self.total_budget),
            allowed_channels    = channels,
            max_pct_per_channel = self.max_pct_per_channel,
        )


# ─────────────────────────────────────────
# EXTRACTION CHAIN
# ─────────────────────────────────────────

class CampaignExtractor:
    """
    Extracts structured campaign parameters
    from natural language using local Ollama.
    """

    def __init__(self, model: str = "llama3.1"):
        self.llm = ChatOllama(
            model       = model,
            temperature = 0,
            format      = "json",
        )
        from agent.prompts import SYSTEM_PROMPT
        self.system_prompt = SYSTEM_PROMPT

    def _clean_json(self, raw: str) -> str:
        """Cleans LLM output to get pure JSON."""
        raw = re.sub(r"```json\s*", "", raw)
        raw = re.sub(r"```\s*", "", raw)
        raw = raw.strip()
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start != -1 and end > start:
            return raw[start:end]
        return raw

    def _correct_priority(
        self, priority: str, user_message: str
    ) -> str:
        """
        Overrides LLM priority if message contains
        strong keyword signals the model missed.
        """
        msg = user_message.lower()
        low_cost_keywords = [
            "cheapest", "cheap", "affordable", "low cost",
            "low-cost", "minimum spend", "reduce cost",
            "cost effective", "cost-effective", "low budget",
            "moins cher", "économique", "pas cher",
        ]
        high_volume_keywords = [
            "as many as possible", "maximum people",
            "large audience", "mass", "scale",
            "high volume", "many leads", "wide reach",
            "le plus de personnes", "maximum de gens",
        ]
        for kw in low_cost_keywords:
            if kw in msg:
                return "low_cost"
        for kw in high_volume_keywords:
            if kw in msg:
                return "high_volume"
        return priority

    # ── @traceable wraps this method so every call appears
    # ── as a named run in the LangSmith dashboard with:
    # ──   inputs:  the user message
    # ──   outputs: status + raw_json + error
    # ── This is all we need — LangChain auto-traces the
    # ── ChatOllama call inside it as a child span.

    @traceable(name="extract_campaign", run_type="chain")
    def extract(self, user_message: str) -> dict:
        """
        Extracts campaign parameters from a natural language message.

        LangSmith logs:
          - input:  user_message
          - output: status, raw_json, error (if any)
          - child:  the ChatOllama LLM call (auto-traced)

        Returns:
            status:         "ok" | "missing_budget" |
                            "missing_channels" | "error"
            extracted:      ExtractedCampaign or None
            campaign:       CampaignInput or None
            missing_fields: list of missing field names
            raw_json:       the parsed JSON dict
            error:          error string or None
        """
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=user_message),
        ]

        try:
            response    = self.llm.invoke(messages)
            raw_content = response.content
            clean       = self._clean_json(raw_content)
            raw_json    = json.loads(clean)

            if raw_json.get("total_budget") is None:
                return {
                    "status":         "missing_budget",
                    "extracted":      None,
                    "campaign":       None,
                    "missing_fields": ["total_budget"],
                    "raw_json":       raw_json,
                    "error":          None,
                }

            extracted = ExtractedCampaign(**raw_json)

            if not extracted.allowed_channels:
                return {
                    "status":         "missing_channels",
                    "extracted":      extracted,
                    "campaign":       None,
                    "missing_fields": ["allowed_channels"],
                    "raw_json":       raw_json,
                    "error":          None,
                }

            corrected = self._correct_priority(
                extracted.priority, user_message
            )
            if corrected != extracted.priority:
                extracted.priority = corrected

            campaign = extracted.to_campaign_input()

            return {
                "status":         "ok",
                "extracted":      extracted,
                "campaign":       campaign,
                "missing_fields": [],
                "raw_json":       raw_json,
                "error":          None,
            }

        except json.JSONDecodeError as e:
            return {
                "status":         "error",
                "extracted":      None,
                "campaign":       None,
                "missing_fields": [],
                "raw_json":       None,
                "error":          (
                    f"JSON parse failed: {e}. "
                    f"Raw: {raw_content[:200]}"
                ),
            }
        except Exception as e:
            return {
                "status":         "error",
                "extracted":      None,
                "campaign":       None,
                "missing_fields": [],
                "raw_json":       None,
                "error":          str(e),
            }


# ── Module-level singleton ────────────────────────────────

_extractor = None

def get_extractor() -> CampaignExtractor:
    global _extractor
    if _extractor is None:
        _extractor = CampaignExtractor()
    return _extractor

def extract_campaign(user_message: str) -> dict:
    """Main entry point. Takes a message, returns extraction dict."""
    return get_extractor().extract(user_message)