from dataclasses import dataclass, field
from typing import List, Optional

# ─────────────────────────────────────────
# CONSTANTS  (used by both the form and
# the scoring/optimizer logic)
# ─────────────────────────────────────────

SECTORS = [
    "fintech",
    "ecommerce",
    "saas",
    "education",
    "health",
]

CHANNELS = [
    "facebook",
    "instagram",
    "google_ads",
    "email",
    "seo",
    "tiktok",
]

GOALS = [
    "generate_leads",
    "increase_sales",
    "brand_awareness",
]

PRIORITIES = [
    "low_cost",       # minimize cost per lead
    "high_volume",    # maximize number of people reached
    "high_quality",   # maximize conversion rate
]

AUDIENCE_TYPES = [
    "students",
    "professionals",
    "business_owners",
]

CLIENT_TYPES = ["b2c", "b2b"]

# ─────────────────────────────────────────
# COUNTRY → CLUSTER MAPPING
# A cluster groups countries with similar
# ad costs and audience behavior.
# ─────────────────────────────────────────

COUNTRIES = {
    # Maghreb
    "Morocco":      "maghreb",
    "Algeria":      "maghreb",
    "Tunisia":      "maghreb",
    "Libya":        "maghreb",
    # Levant
    "Egypt":        "levant",
    "Jordan":       "levant",
    "Lebanon":      "levant",
    # Gulf
    "Saudi Arabia": "gulf",
    "UAE":          "gulf",
    "Kuwait":       "gulf",
    "Qatar":        "gulf",
    # Europe
    "France":       "europe",
    "Spain":        "europe",
    "Germany":      "europe",
    "UK":           "europe",
    "Italy":        "europe",
    # North America
    "USA":          "north_america",
    "Canada":       "north_america",
    # West Africa
    "Senegal":      "west_africa",
    "Ivory Coast":  "west_africa",
    "Cameroon":     "west_africa",
    "Nigeria":      "west_africa",
    # East Asia
    "China":        "east_asia",
    "Japan":        "east_asia",
    "South Korea":  "east_asia",
}

CLUSTERS = [
    "maghreb",
    "levant",
    "gulf",
    "europe",
    "north_america",
    "west_africa",
    "east_asia",
]

def get_clusters(selected_countries: List[str]) -> List[str]:
    """
    Takes a list of country names the user selected,
    returns the unique clusters they belong to.

    Example:
        get_clusters(["Morocco", "France", "Egypt"])
        → ["maghreb", "europe", "levant"]
    """
    return list(set(
        COUNTRIES[c] for c in selected_countries
        if c in COUNTRIES
    ))


# ─────────────────────────────────────────
# PRIORITY WEIGHTS
# Tell the optimizer what to care about
# depending on the user's chosen priority.
# ─────────────────────────────────────────

PRIORITY_WEIGHTS = {
    "low_cost": {
        "cpl":        0.6,   # 60% weight on keeping cost low
        "reach":      0.2,
        "conversion": 0.2,
    },
    "high_volume": {
        "cpl":        0.2,
        "reach":      0.6,   # 60% weight on reaching many people
        "conversion": 0.2,
    },
    "high_quality": {
        "cpl":        0.2,
        "reach":      0.2,
        "conversion": 0.6,   # 60% weight on conversion rate
    },
}


# ─────────────────────────────────────────
# AUDIENCE → CHANNEL AFFINITY
# Multipliers applied to channel scores
# depending on who the target audience is.
# A value of 1.4 means "boost this channel
# by 40% for this audience".
# ─────────────────────────────────────────

AUDIENCE_CHANNEL_AFFINITY = {
    "students": {
        "tiktok":     1.4,
        "instagram":  1.3,
        "youtube":    1.2,
        "facebook":   1.0,
        "google_ads": 0.9,
        "seo":        0.9,
        "email":      0.7,
        "linkedin":   0.5,
    },
    "professionals": {
        "linkedin":   1.5,
        "google_ads": 1.3,
        "email":      1.2,
        "seo":        1.1,
        "youtube":    1.0,
        "facebook":   1.0,
        "instagram":  0.9,
        "tiktok":     0.6,
    },
    "business_owners": {
        "linkedin":   1.4,
        "google_ads": 1.3,
        "email":      1.3,
        "seo":        1.2,
        "facebook":   1.1,
        "youtube":    0.9,
        "instagram":  0.8,
        "tiktok":     0.5,
    },
}


# ─────────────────────────────────────────
# CAMPAIGN INPUT
# This is the single object that the form
# fills in and the optimizer reads.
# Both websites produce exactly this.
# ─────────────────────────────────────────

@dataclass
class CampaignInput:

    # ── Section 1: client info ──
    company_name:     str
    sector:           str        # must be in SECTORS
    target_countries: List[str]  # e.g. ["Morocco", "France"]
    client_type:      str        # "b2c" or "b2b"

    # ── Section 2: target audience ──
    age_min:          int            = 18
    age_max:          int            = 45
    audience_type:    Optional[str]  = None   # one of AUDIENCE_TYPES or None

    # ── Section 3: campaign goals ──
    goal:             str  = "generate_leads"   # one of GOALS
    horizon_months:   int  = 3                  # 1 to 12
    priority:         str  = "high_quality"     # one of PRIORITIES

    # ── Section 4: budget & channels ──
    total_budget:       float       = 0.0
    allowed_channels:   List[str]   = field(
        default_factory=lambda: list(CHANNELS)
    )

    # ── Section 5: constraints ──
    max_pct_per_channel: float = 0.50   # no channel gets more than 50%

    # ── Derived properties ──
    # These are computed automatically from the fields above.
    # You never fill them in manually.

    @property
    def clusters(self) -> List[str]:
        """The clusters that the selected countries belong to."""
        return get_clusters(self.target_countries)

    @property
    def priority_weights(self) -> dict:
        """The optimizer weights for the chosen priority."""
        return PRIORITY_WEIGHTS[self.priority]

    @property
    def audience_affinity(self) -> dict:
        """Channel multipliers for the chosen audience type."""
        if self.audience_type:
            return AUDIENCE_CHANNEL_AFFINITY[self.audience_type]
        # If no audience type selected, all channels are neutral
        return {ch: 1.0 for ch in CHANNELS}