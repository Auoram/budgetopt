"""
core/task_generator.py
──────────────────────
Generates a structured execution task list for a campaign,
based on its channels, sector, goal, and horizon.

Each task has:
  - category:   Creative | Setup | Launch | Monitoring | Reporting
  - channel:    which channel it belongs to (or "all")
  - title:      short action label
  - description: detailed instructions
  - due_day:    suggested day offset from campaign start (int)
  - priority:   high | medium | low
  - assignee_role: which freelancer role should handle it
"""

from dataclasses import dataclass, field
from typing import List, Optional
from core.data_model import CampaignInput


# ─────────────────────────────────────────
# DATA CLASS
# ─────────────────────────────────────────

@dataclass
class Task:
    channel:       str          # channel slug or "all"
    category:      str          # Creative | Setup | Launch | Monitoring | Reporting
    title:         str
    description:   str
    due_day:       int          # days from campaign start date
    priority:      str          # high | medium | low
    assignee_role: str          # role slug from team_builder.ROLE_LABELS
    status:        str = "todo" # todo | in_progress | done | blocked
    notes:         str = ""


# ─────────────────────────────────────────
# TASK TEMPLATES PER CHANNEL
# ─────────────────────────────────────────
# Each entry is a list of task dicts.
# "due_day" is relative — day 1 = campaign start.
# ─────────────────────────────────────────

CHANNEL_TASKS = {

    "facebook": [
        # ── Creative ──
        {
            "category":     "Creative",
            "title":        "Write Facebook ad copy",
            "description":  (
                "Write 3 variations of ad copy for Facebook: "
                "primary text (max 125 chars), headline (max 40 chars), "
                "and description (max 30 chars). "
                "Include one urgency version, one social-proof version, "
                "and one benefit-led version."
            ),
            "due_day":      3,
            "priority":     "high",
            "assignee_role":"copywriter",
        },
        {
            "category":     "Creative",
            "title":        "Design static ad creatives",
            "description":  (
                "Design 3–5 static images (1080×1080 feed + 1080×1920 Story). "
                "Follow Facebook ad specs: text under 20% of image, "
                "brand colours consistent. Deliver as PNG and PDF."
            ),
            "due_day":      4,
            "priority":     "high",
            "assignee_role":"graphic_designer",
        },
        # ── Setup ──
        {
            "category":     "Setup",
            "title":        "Create Facebook Business Manager & ad account",
            "description":  (
                "Verify Business Manager is set up. "
                "Create or confirm the ad account with correct currency (MAD). "
                "Add payment method and billing threshold."
            ),
            "due_day":      1,
            "priority":     "high",
            "assignee_role":"media_buyer",
        },
        {
            "category":     "Setup",
            "title":        "Install and verify Facebook Pixel",
            "description":  (
                "Install the Meta Pixel on the website via GTM or direct code. "
                "Verify with Meta Pixel Helper: PageView, Lead, and Purchase "
                "events must fire correctly before launch."
            ),
            "due_day":      2,
            "priority":     "high",
            "assignee_role":"web_developer",
        },
        {
            "category":     "Setup",
            "title":        "Build custom audiences and lookalikes",
            "description":  (
                "Create: (1) Website visitors — last 180 days, "
                "(2) Customer list upload if available, "
                "(3) 1% and 3% lookalike audiences from each source. "
                "Label all audiences clearly with date and source."
            ),
            "due_day":      3,
            "priority":     "high",
            "assignee_role":"media_buyer",
        },
        {
            "category":     "Setup",
            "title":        "Configure campaign structure in Ads Manager",
            "description":  (
                "Set up campaign with correct objective. "
                "Create ad sets per audience segment. "
                "Apply budget, schedule, and placements. "
                "Use Campaign Budget Optimisation (CBO) if budget > 5,000 MAD/day."
            ),
            "due_day":      4,
            "priority":     "high",
            "assignee_role":"media_buyer",
        },
        # ── Launch ──
        {
            "category":     "Launch",
            "title":        "Upload creatives and submit ads for review",
            "description":  (
                "Upload all approved creatives. "
                "Assign copy variations to each ad set. "
                "Submit for Meta review — allow 24h. "
                "Confirm all ads pass review before marking done."
            ),
            "due_day":      5,
            "priority":     "high",
            "assignee_role":"media_buyer",
        },
        # ── Monitoring ──
        {
            "category":     "Monitoring",
            "title":        "Daily Facebook performance check",
            "description":  (
                "Every weekday: check CTR (target > 1%), "
                "CPL vs benchmark, frequency (pause if > 3.5), "
                "and relevance score. "
                "Pause underperforming ad sets. "
                "Log results in the campaign tracker."
            ),
            "due_day":      7,
            "priority":     "high",
            "assignee_role":"media_buyer",
        },
        {
            "category":     "Monitoring",
            "title":        "A/B test creative performance review",
            "description":  (
                "After 7 days: compare CTR and CPL across creative variants. "
                "Pause the lowest performer. "
                "Scale budget on the top 1–2 creatives by 20%."
            ),
            "due_day":      12,
            "priority":     "medium",
            "assignee_role":"media_buyer",
        },
    ],

    "instagram": [
        {
            "category":     "Creative",
            "title":        "Produce Instagram Reels (30s)",
            "description":  (
                "Produce 2 Reels (max 30s each) optimised for Instagram. "
                "Hook in first 3 seconds. Subtitles required. "
                "Export as MP4 1080×1920, < 250 MB."
            ),
            "due_day":      4,
            "priority":     "high",
            "assignee_role":"video_editor",
        },
        {
            "category":     "Creative",
            "title":        "Write Instagram captions and hashtag set",
            "description":  (
                "Write captions for feed posts and Stories: "
                "engaging first line (visible before 'more'), "
                "CTA, and 10–15 relevant hashtags. "
                "Avoid banned hashtags — verify with Instagram."
            ),
            "due_day":      3,
            "priority":     "medium",
            "assignee_role":"copywriter",
        },
        {
            "category":     "Setup",
            "title":        "Link Instagram account to Business Manager",
            "description":  (
                "Confirm Instagram Business or Creator account is connected "
                "to the correct Facebook Page and Ad Account. "
                "Enable Shopping if relevant to the sector."
            ),
            "due_day":      1,
            "priority":     "high",
            "assignee_role":"media_buyer",
        },
        {
            "category":     "Launch",
            "title":        "Schedule and publish Instagram content calendar",
            "description":  (
                "Use Meta Business Suite or Later to schedule organic posts "
                "supporting the paid campaign. "
                "Aim for 3–4 posts per week. "
                "Coordinate posting times with paid ad schedule."
            ),
            "due_day":      5,
            "priority":     "medium",
            "assignee_role":"community_manager",
        },
        {
            "category":     "Monitoring",
            "title":        "Instagram engagement and comment moderation",
            "description":  (
                "Daily: reply to comments on ads and organic posts within 2h. "
                "Hide spam. Flag negative sentiment to account manager. "
                "Track saves and shares as quality signals."
            ),
            "due_day":      6,
            "priority":     "medium",
            "assignee_role":"community_manager",
        },
    ],

    "google_ads": [
        {
            "category":     "Setup",
            "title":        "Keyword research and match type mapping",
            "description":  (
                "Use Google Keyword Planner + SEMrush/Ahrefs to identify: "
                "exact match brand terms, phrase match product terms, "
                "broad match competitor terms. "
                "Export to spreadsheet with volume, CPC estimates, and intent labels."
            ),
            "due_day":      2,
            "priority":     "high",
            "assignee_role":"media_buyer",
        },
        {
            "category":     "Creative",
            "title":        "Write Responsive Search Ads (RSAs)",
            "description":  (
                "Write 15 headlines (max 30 chars each) and 4 descriptions "
                "(max 90 chars each) for each ad group. "
                "Include keyword in at least 3 headlines. "
                "Pin headline 1 to brand/product name."
            ),
            "due_day":      3,
            "priority":     "high",
            "assignee_role":"copywriter",
        },
        {
            "category":     "Setup",
            "title":        "Configure Google Ads account and conversion tracking",
            "description":  (
                "Create Google Ads account with correct currency. "
                "Link Google Analytics 4. "
                "Set up conversion actions: Lead form submit, Purchase, Phone call. "
                "Verify conversions fire in Tag Assistant."
            ),
            "due_day":      2,
            "priority":     "high",
            "assignee_role":"web_developer",
        },
        {
            "category":     "Setup",
            "title":        "Build campaign structure — ad groups and negative keywords",
            "description":  (
                "Create tightly themed ad groups (max 10–15 keywords each). "
                "Add negative keyword list (competitor brand names, "
                "irrelevant modifiers, job-seeker terms). "
                "Set bidding strategy: Maximise Conversions or Target CPA."
            ),
            "due_day":      4,
            "priority":     "high",
            "assignee_role":"media_buyer",
        },
        {
            "category":     "Launch",
            "title":        "Enable campaigns and confirm ad serving",
            "description":  (
                "Set campaigns live. "
                "Verify ads are serving in Ad Preview Tool for target keywords. "
                "Check Quality Scores — pause keywords scoring < 4. "
                "Confirm budget pacing is on track within first 6h."
            ),
            "due_day":      5,
            "priority":     "high",
            "assignee_role":"media_buyer",
        },
        {
            "category":     "Monitoring",
            "title":        "Weekly search term report review",
            "description":  (
                "Download Search Terms report. "
                "Add converting new terms as exact match keywords. "
                "Add irrelevant terms to negative list. "
                "Check impression share — increase bids if lost to budget."
            ),
            "due_day":      12,
            "priority":     "high",
            "assignee_role":"media_buyer",
        },
    ],

    "tiktok": [
        {
            "category":     "Creative",
            "title":        "Produce TikTok-native video ads (3 variations)",
            "description":  (
                "Produce 3 videos (9–15s each) in vertical format 1080×1920. "
                "Each must have a strong hook in first 2 seconds. "
                "Avoid stock footage — native, authentic style performs best. "
                "Add trending audio or original voiceover."
            ),
            "due_day":      4,
            "priority":     "high",
            "assignee_role":"video_editor",
        },
        {
            "category":     "Creative",
            "title":        "Write TikTok ad captions and on-screen text",
            "description":  (
                "Write short punchy captions (max 150 chars) for each video. "
                "Script the on-screen text overlays for each video. "
                "Include CTA in last 3 seconds."
            ),
            "due_day":      3,
            "priority":     "high",
            "assignee_role":"copywriter",
        },
        {
            "category":     "Setup",
            "title":        "Create TikTok Ads Manager account and pixel",
            "description":  (
                "Set up TikTok for Business account. "
                "Install TikTok Pixel via GTM or direct code. "
                "Verify ViewContent, AddToCart, and CompletePayment events. "
                "Connect TikTok account for Spark Ads if using organic content."
            ),
            "due_day":      2,
            "priority":     "high",
            "assignee_role":"web_developer",
        },
        {
            "category":     "Monitoring",
            "title":        "TikTok video performance review",
            "description":  (
                "Check daily: Video view rate (target > 25% watch to end), "
                "CTR (target > 1.5%), CPL vs benchmark. "
                "Pause videos with < 15% watch rate after 2 days. "
                "Scale budget on top performer by 30%."
            ),
            "due_day":      7,
            "priority":     "high",
            "assignee_role":"media_buyer",
        },
    ],

    "email": [
        {
            "category":     "Creative",
            "title":        "Write email sequence (3–5 emails)",
            "description":  (
                "Write a drip sequence: "
                "Email 1 — Welcome / Hook (send day 0), "
                "Email 2 — Value / Education (day 3), "
                "Email 3 — Social proof / Case study (day 7), "
                "Email 4 — Offer / CTA (day 10), "
                "Email 5 — Last chance / Urgency (day 14). "
                "Subject lines A/B tested (2 variants each)."
            ),
            "due_day":      4,
            "priority":     "high",
            "assignee_role":"copywriter",
        },
        {
            "category":     "Creative",
            "title":        "Design HTML email templates",
            "description":  (
                "Design responsive email templates (600px max width). "
                "Test in Litmus or Email on Acid: "
                "Gmail, Outlook, Apple Mail, mobile. "
                "Deliver as HTML file + plain-text version."
            ),
            "due_day":      5,
            "priority":     "high",
            "assignee_role":"graphic_designer",
        },
        {
            "category":     "Setup",
            "title":        "Configure email platform and import list",
            "description":  (
                "Set up Mailchimp / Klaviyo / Brevo account. "
                "Import and segment contact list. "
                "Verify domain authentication: SPF, DKIM, DMARC records. "
                "Set up suppression list for unsubscribes and bounces."
            ),
            "due_day":      2,
            "priority":     "high",
            "assignee_role":"web_developer",
        },
        {
            "category":     "Monitoring",
            "title":        "Email metrics weekly review",
            "description":  (
                "Weekly: check open rate (target > 25%), "
                "CTR (target > 3%), unsubscribe rate (must be < 0.5%). "
                "Resend to non-openers with different subject line after 5 days. "
                "Flag deliverability issues immediately."
            ),
            "due_day":      10,
            "priority":     "medium",
            "assignee_role":"data_analyst",
        },
    ],

    "seo": [
        {
            "category":     "Setup",
            "title":        "SEO audit and technical baseline",
            "description":  (
                "Run full technical audit (Screaming Frog or Sitebulb): "
                "crawl errors, broken links, page speed (Core Web Vitals), "
                "mobile usability, duplicate content, canonical tags. "
                "Deliver prioritised fix list."
            ),
            "due_day":      3,
            "priority":     "high",
            "assignee_role":"seo_specialist",
        },
        {
            "category":     "Setup",
            "title":        "Keyword mapping and content plan",
            "description":  (
                "Map target keywords to existing pages. "
                "Identify content gaps — pages to create. "
                "Produce a 3-month content calendar: "
                "1 pillar page + 4 supporting articles per month minimum."
            ),
            "due_day":      5,
            "priority":     "high",
            "assignee_role":"seo_specialist",
        },
        {
            "category":     "Creative",
            "title":        "Write SEO articles (month 1 batch)",
            "description":  (
                "Write the first month's content batch: "
                "1 pillar article (2,000+ words) and 4 supporting articles "
                "(800–1,200 words each). "
                "Each must target one primary keyword, include internal links, "
                "and have an optimised meta title and description."
            ),
            "due_day":      14,
            "priority":     "high",
            "assignee_role":"copywriter",
        },
        {
            "category":     "Setup",
            "title":        "Implement technical SEO fixes",
            "description":  (
                "Fix critical issues from audit: "
                "page speed (image compression, lazy load, CDN), "
                "schema markup (Article, Product, FAQ), "
                "XML sitemap submission to Google Search Console, "
                "robots.txt review."
            ),
            "due_day":      7,
            "priority":     "high",
            "assignee_role":"web_developer",
        },
        {
            "category":     "Monitoring",
            "title":        "Monthly SEO rank tracking report",
            "description":  (
                "Track keyword positions weekly (Google Search Console + SEMrush). "
                "Monthly report: impressions, clicks, avg position, "
                "new rankings in top 10. "
                "Note: SEO results appear after 3–6 months — set expectations accordingly."
            ),
            "due_day":      30,
            "priority":     "medium",
            "assignee_role":"data_analyst",
        },
    ],

    "linkedin": [
        {
            "category":     "Setup",
            "title":        "Configure LinkedIn Campaign Manager",
            "description":  (
                "Create LinkedIn Campaign Manager account. "
                "Set up LinkedIn Insight Tag on website. "
                "Define audience: job title, seniority, industry, company size. "
                "Choose objective: Lead Generation or Website Conversions."
            ),
            "due_day":      2,
            "priority":     "high",
            "assignee_role":"media_buyer",
        },
        {
            "category":     "Creative",
            "title":        "Write LinkedIn sponsored content copy",
            "description":  (
                "Write 3 sponsored post variations: "
                "thought-leadership angle, pain-point angle, ROI/results angle. "
                "Max 150 chars introductory text + headline + CTA. "
                "For Lead Gen Forms: write form headline and privacy policy text."
            ),
            "due_day":      3,
            "priority":     "high",
            "assignee_role":"copywriter",
        },
        {
            "category":     "Monitoring",
            "title":        "LinkedIn lead quality review",
            "description":  (
                "Weekly: export leads from Lead Gen Forms. "
                "Check job title and company size match ICP. "
                "Review CTR (target > 0.5% for LinkedIn — lower than other platforms). "
                "Pause audiences with CPL > 2× benchmark."
            ),
            "due_day":      10,
            "priority":     "high",
            "assignee_role":"data_analyst",
        },
    ],
}

# ─────────────────────────────────────────
# CROSS-CHANNEL TASKS (always generated)
# ─────────────────────────────────────────

def _global_tasks(campaign: CampaignInput) -> List[Task]:
    """Tasks that apply to every campaign regardless of channels."""
    tasks = []

    # Kick-off
    tasks.append(Task(
        channel       = "all",
        category      = "Setup",
        title         = "Campaign kick-off briefing",
        description   = (
            f"Brief all team members on campaign goals: "
            f"sector={campaign.sector}, goal={campaign.goal.replace('_', ' ')}, "
            f"budget={int(campaign.total_budget):,} MAD, "
            f"horizon={campaign.horizon_months} months. "
            f"Share access to ad accounts, brand assets, and this task list."
        ),
        due_day       = 1,
        priority      = "high",
        assignee_role = "project_manager",
    ))

    # UTM tracking setup
    tasks.append(Task(
        channel       = "all",
        category      = "Setup",
        title         = "Set up UTM tracking parameters",
        description   = (
            "Create a UTM naming convention document. "
            "Build UTM links for every channel using Google's Campaign URL Builder. "
            "Convention: utm_source=channel, utm_medium=paid|organic, "
            "utm_campaign=campaign_name_date. "
            "Share the UTM sheet with all media buyers before launch."
        ),
        due_day       = 2,
        priority      = "high",
        assignee_role = "data_analyst",
    ))

    # Weekly report
    tasks.append(Task(
        channel       = "all",
        category      = "Reporting",
        title         = "Weekly performance report",
        description   = (
            "Every Monday: compile cross-channel performance report. "
            "Include: spend by channel, leads by channel, CPL by channel, "
            "week-over-week trend, budget remaining, "
            "and 2–3 action points for the coming week."
        ),
        due_day       = 8,
        priority      = "high",
        assignee_role = "data_analyst",
    ))

    # End-of-campaign report
    tasks.append(Task(
        channel       = "all",
        category      = "Reporting",
        title         = "End-of-campaign performance report",
        description   = (
            "Final report covering the full campaign period: "
            "total spend vs budget, total leads, blended CPL, "
            "channel breakdown, top creatives, lessons learned, "
            "and recommended budget split for next campaign."
        ),
        due_day       = campaign.horizon_months * 30,
        priority      = "high",
        assignee_role = "data_analyst",
    ))

    # Short-horizon SEO warning
    if "seo" in campaign.allowed_channels and campaign.horizon_months < 4:
        tasks.append(Task(
            channel       = "seo",
            category      = "Setup",
            title         = "SEO expectation-setting note",
            description   = (
                f"Campaign horizon is {campaign.horizon_months} month(s). "
                "SEO typically shows measurable results after 3–6 months. "
                "Focus SEO work on technical fixes and content creation now — "
                "results will appear after the campaign window. "
                "Consider shifting more budget to paid channels for short-term leads."
            ),
            due_day       = 1,
            priority      = "medium",
            assignee_role = "seo_specialist",
        ))

    return tasks


# ─────────────────────────────────────────
# SECTOR-SPECIFIC EXTRA TASKS
# ─────────────────────────────────────────

SECTOR_EXTRA_TASKS = {
    "ecommerce": [
        Task(
            channel       = "all",
            category      = "Setup",
            title         = "Configure abandoned cart recovery",
            description   = (
                "Set up abandoned cart email/SMS flow in your ESP. "
                "Trigger: cart abandoned > 1h. "
                "Sequence: reminder at 1h, offer at 24h, last chance at 72h. "
                "Track recovery rate as a key KPI."
            ),
            due_day       = 5,
            priority      = "high",
            assignee_role = "web_developer",
        ),
        Task(
            channel       = "all",
            category      = "Setup",
            title         = "Set up product feed for dynamic ads",
            description   = (
                "Export product catalogue as XML/CSV. "
                "Upload to Meta Commerce Manager and Google Merchant Center. "
                "Verify all products are approved. "
                "Enable Dynamic Product Ads on Facebook and Google Shopping."
            ),
            due_day       = 3,
            priority      = "high",
            assignee_role = "web_developer",
        ),
    ],
    "saas": [
        Task(
            channel       = "all",
            category      = "Setup",
            title         = "Define and track trial-to-paid conversion event",
            description   = (
                "Identify the key conversion event (free trial signup, demo request, "
                "or paid subscription start). "
                "Ensure this event is tracked in GA4, LinkedIn, and Google Ads. "
                "Set target conversion rate benchmarks before launch."
            ),
            due_day       = 2,
            priority      = "high",
            assignee_role = "data_analyst",
        ),
    ],
    "health": [
        Task(
            channel       = "all",
            category      = "Creative",
            title         = "Compliance review of all health ad copy",
            description   = (
                "Review all ad copy against Meta and Google health advertising policies. "
                "Remove: before/after claims, guaranteed results, medical claims "
                "not backed by citation. "
                "Health ads are high-risk for rejection — get legal/compliance sign-off "
                "before upload."
            ),
            due_day       = 4,
            priority      = "high",
            assignee_role = "copywriter",
        ),
    ],
    "fintech": [
        Task(
            channel       = "all",
            category      = "Creative",
            title         = "Compliance review of financial ad copy",
            description   = (
                "Review all ad copy against Meta and Google financial services policies. "
                "Required disclaimers: risk warnings for investment products, "
                "regulatory body mention if applicable. "
                "Financial ads may require pre-approval from Meta — apply early."
            ),
            due_day       = 3,
            priority      = "high",
            assignee_role = "copywriter",
        ),
    ],
}


# ─────────────────────────────────────────
# MAIN GENERATOR
# ─────────────────────────────────────────

def generate_tasks(campaign: CampaignInput) -> List[Task]:
    """
    Main entry point.
    Returns a full task list for the campaign:
      - Global tasks (kick-off, UTM, reports)
      - Per-channel tasks for each allowed channel
      - Sector-specific extra tasks
    Tasks are sorted by due_day, then priority.
    """
    tasks: List[Task] = []

    # Global tasks
    tasks.extend(_global_tasks(campaign))

    # Per-channel tasks
    for channel in campaign.allowed_channels:
        for t in CHANNEL_TASKS.get(channel, []):
            tasks.append(Task(
                channel       = channel,
                category      = t["category"],
                title         = t["title"],
                description   = t["description"],
                due_day       = t["due_day"],
                priority      = t["priority"],
                assignee_role = t["assignee_role"],
            ))

    # Sector extras
    for t in SECTOR_EXTRA_TASKS.get(campaign.sector, []):
        tasks.append(t)

    # Sort: by due_day, then priority order
    priority_order = {"high": 0, "medium": 1, "low": 2}
    tasks.sort(key=lambda t: (t.due_day, priority_order.get(t.priority, 9)))

    return tasks


CATEGORY_EMOJI = {
    "Creative":   "🎨",
    "Setup":      "⚙️",
    "Launch":     "🚀",
    "Monitoring": "📈",
    "Reporting":  "📋",
}

PRIORITY_COLOR = {
    "high":   "🔴",
    "medium": "🟡",
    "low":    "🟢",
}