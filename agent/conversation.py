from dataclasses import dataclass, field
from typing import Optional
from core.data_model import CampaignInput
from core.optimizer import AllocationResult


# ─────────────────────────────────────────
# CONVERSATION STATE
# Holds everything about the current chat
# session between the user and the agent.
# ─────────────────────────────────────────

@dataclass
class ConversationState:
    """
    Tracks the state of one conversation session.
    One instance per user session in Streamlit.
    """

    # Full message history for display
    # Each entry: {"role": "user"|"assistant", "content": str}
    messages: list = field(default_factory=list)

    # The original user message (first one)
    original_message: str = ""

    # Accumulated context — original + all follow-up answers
    # This is what gets re-extracted after each clarification
    accumulated_context: str = ""

    # What the agent is currently waiting for
    # None = not waiting, "budget" | "channels" = waiting
    waiting_for: Optional[str] = None

    # The last successful extraction result
    last_extraction: Optional[dict] = None

    # The last successful CampaignInput
    last_campaign: Optional[CampaignInput] = None

    # The last allocation result
    last_result: Optional[AllocationResult] = None

    # How many clarification rounds have happened
    clarification_count: int = 0

    # Max clarification rounds before giving up
    max_clarifications: int = 3

    def add_user_message(self, content: str):
        self.messages.append({"role": "user", "content": content})

    def add_assistant_message(self, content: str):
        self.messages.append({"role": "assistant", "content": content})

    def reset(self):
        """Resets the conversation to start fresh."""
        self.__init__()


# ─────────────────────────────────────────
# CLARIFICATION QUESTIONS
# ─────────────────────────────────────────

def get_clarification_question(missing_field: str) -> str:
    """Returns a targeted question for a missing field."""
    questions = {
        "total_budget": (
            "I need one more detail — what is your **total marketing budget**?\n\n"
            "You can give it in MAD, USD, or EUR. "
            "For example: *'500,000 MAD'*, *'$50,000'*, or *'200,000 euros'*."
        ),
        "allowed_channels": (
            "Which advertising channels would you like to use?\n\n"
            "Available options:\n"
            "- 📘 **Facebook Ads**\n"
            "- 📷 **Instagram Ads**\n"
            "- 🔍 **Google Ads**\n"
            "- 📧 **Email Marketing**\n"
            "- 🌱 **SEO / Content**\n"
            "- 🎵 **TikTok Ads**\n\n"
            "You can say *'all channels'* or list specific ones."
        ),
    }
    return questions.get(
        missing_field,
        f"Could you provide more information about {missing_field}?"
    )


def get_welcome_message() -> str:
    return (
        "Hello! I'm your **BudgetOpt** assistant.\n\n"
        "Tell me about your campaign in natural language and I'll "
        "recommend the optimal budget allocation across channels.\n\n"
        "For example:\n"
        "> *'I have 500,000 MAD to promote a fintech app in Morocco "
        "over 3 months. Target young adults 20-35, Facebook and Instagram.'*\n\n"
        "You can write in English or French."
    )


# ─────────────────────────────────────────
# AGENT LOGIC
# ─────────────────────────────────────────

class BudgetAgent:
    """
    Manages the conversation flow:
    1. Extract campaign from user message        ← extractor.py (LLM call 1)
    2. If missing fields → ask clarifying question
    3. If complete → run pipeline               ← pipeline.py (optimizer)
    4. Generate natural language explanation    ← explainer.py (LLM call 2)
    5. Handle follow-up answers by re-extracting
    """

    def __init__(self):
        from agent.extractor import get_extractor
        self.extractor = get_extractor()

    def process_message(
        self,
        user_message: str,
        state: ConversationState,
    ) -> tuple[str, ConversationState]:
        """
        Processes one user message and returns
        (agent_response, updated_state).
        """
        state.add_user_message(user_message)

        # ── Case 1: agent was waiting for a clarification ──
        if state.waiting_for is not None:
            return self._handle_clarification(user_message, state)

        # ── Case 2: new campaign request ──
        return self._handle_new_request(user_message, state)

    def _handle_new_request(
        self,
        user_message: str,
        state: ConversationState,
    ) -> tuple[str, ConversationState]:
        """Handles a fresh campaign description."""
        state.original_message    = user_message
        state.accumulated_context = user_message
        state.clarification_count = 0

        extraction = self.extractor.extract(user_message)
        state.last_extraction = extraction

        return self._route_extraction(extraction, state)

    def _handle_clarification(
        self,
        user_answer: str,
        state: ConversationState,
    ) -> tuple[str, ConversationState]:
        """
        Handles a follow-up answer.
        Combines original context + new answer and re-extracts.
        """
        state.clarification_count += 1

        state.accumulated_context = (
            f"{state.original_message} "
            f"{user_answer}"
        )

        # Give up if too many rounds
        if state.clarification_count >= state.max_clarifications:
            state.waiting_for = None
            response = (
                "I'm having trouble extracting all the required "
                "information. Please describe your campaign again "
                "with: **budget**, **channels**, **sector**, "
                "**countries**, and **duration**."
            )
            state.add_assistant_message(response)
            return response, state

        extraction = self.extractor.extract(state.accumulated_context)
        state.last_extraction = extraction
        state.waiting_for     = None

        return self._route_extraction(extraction, state)

    def _route_extraction(
        self,
        extraction: dict,
        state: ConversationState,
    ) -> tuple[str, ConversationState]:
        """Routes based on extraction status."""
        status = extraction["status"]

        # ── Missing budget ──
        if status == "missing_budget":
            state.waiting_for = "budget"
            response = get_clarification_question("total_budget")
            state.add_assistant_message(response)
            return response, state

        # ── Missing channels ──
        if status == "missing_channels":
            state.waiting_for = "channels"
            response = get_clarification_question("allowed_channels")
            state.add_assistant_message(response)
            return response, state

        # ── Error ──
        if status == "error":
            state.waiting_for = None
            response = (
                "I had trouble understanding that. "
                "Could you rephrase your campaign description?\n\n"
                f"*Technical detail: {extraction['error']}*"
            )
            state.add_assistant_message(response)
            return response, state

        # ── Success — run pipeline then explain ──
        campaign = extraction["campaign"]
        state.last_campaign = campaign
        state.waiting_for   = None

        try:
            # ── Step 1: optimizer (deterministic) ──────────
            from core.pipeline import pipeline
            result = pipeline(campaign)
            state.last_result = result

            # ── Step 2: LLM explanation (second LLM call) ──
            from agent.explainer import generate_explanation
            explanation = generate_explanation(campaign, result)

            # ── Step 3: assemble final response ────────────
            response = self._format_result(campaign, result, explanation)

        except Exception as e:
            response = (
                f"I extracted your campaign details but the "
                f"optimizer encountered an error: {e}\n\n"
                "Please try again with different parameters."
            )

        state.add_assistant_message(response)
        return response, state

    def _format_result(
        self,
        campaign: CampaignInput,
        result: AllocationResult,
        explanation: str,
    ) -> str:
        """
        Assembles the final chat response:
        - allocation table (deterministic, always correct)
        - KPI summary (deterministic)
        - LLM-generated explanation (natural language, second LLM call)

        The table and KPIs are built from result directly — never from
        the LLM — so numbers are always accurate regardless of what the
        LLM writes in the explanation.
        """
        from core.charts import channel_label

        sorted_channels = sorted(
            result.pct_per_channel,
            key=lambda x: -result.pct_per_channel[x],
        )

        lines = []

        # ── Header ──────────────────────────────────────────
        lines.append(
            f"Here is my recommended budget allocation for "
            f"**{campaign.company_name}** "
            f"({campaign.sector.title()} · "
            f"{campaign.client_type.upper()} · "
            f"{', '.join(campaign.target_countries)}):"
        )
        lines.append("")

        # ── Allocation table ─────────────────────────────────
        lines.append("| Channel | Budget (MAD) | Share | Est. Leads |")
        lines.append("|---|---|---|---|")
        for ch in sorted_channels:
            lines.append(
                f"| {channel_label(ch)} "
                f"| {int(result.budget_per_channel[ch]):,} "
                f"| {result.pct_per_channel[ch]:.1f}% "
                f"| {int(result.expected_leads[ch]):,} |"
            )

        lines.append("")

        # ── KPI summary ──────────────────────────────────────
        roi = round(
            result.total_revenue / campaign.total_budget * 100
            if campaign.total_budget > 0 else 0,
            1,
        )
        lines.append(
            f"**Total expected leads:** {int(result.total_leads):,}  \n"
            f"**Total expected revenue:** {int(result.total_revenue):,} MAD  \n"
            f"**Estimated ROI:** {roi:.0f}%"
        )

        lines.append("")

        # ── LLM-generated explanation (second LLM call) ──────
        lines.append("**Why this allocation?**")
        lines.append("")
        lines.append(explanation)

        # ── Footer ──────────────────────────────────────────
        lines.append("")
        lines.append(
            f"*{campaign.horizon_months} month"
            f"{'s' if campaign.horizon_months > 1 else ''} · "
            f"{campaign.priority.replace('_', ' ').title()} priority · "
            f"Max {int(campaign.max_pct_per_channel * 100)}% per channel*"
        )
        lines.append("")
        lines.append(
            "You can download the full allocation as CSV or PDF "
            "using the buttons below the chat."
        )

        return "\n".join(lines)


# ── Module-level singleton ────────────────────────────────

_agent = None

def get_agent() -> BudgetAgent:
    global _agent
    if _agent is None:
        _agent = BudgetAgent()
    return _agent