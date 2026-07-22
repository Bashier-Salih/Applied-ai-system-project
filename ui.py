"""Shared UI layer for the PawPal+ multipage app.

Everything visual lives here so the three pages (landing / dashboard /
advisor) stay small and consistent:

- ``inject_css()``       -- the playful design system (fonts, palette, motion)
- ``img_data_uri()``     -- local images embedded as base64 data URIs, so they
                            render inside custom HTML and can never break the
                            way hotlinked Wikimedia URLs did
- ``section_label()`` / ``callout()`` -- small HTML helpers used everywhere
- ``get_advisor()``      -- one cached CareAdvisor for the whole session
- ``render_advisor_response()`` -- shared renderer for Q&A and plan review
"""

import base64
from pathlib import Path

import streamlit as st

from care_advisor.advisor import CareAdvisor
from care_advisor.retrieval import DocStore

# Plain-text labels for the UI (no emoji, per design direction). The CLI
# (main.py / formatting.py) keeps its own emoji styling separately.
PRIORITY_LABEL = {"high": "High", "medium": "Medium", "low": "Low"}
RECURRENCE_LABEL = {"daily": "Daily", "weekly": "Weekly", None: "One-off"}

ASSETS_DIR = Path(__file__).parent / "assets"

_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


@st.cache_data
def img_data_uri(filename: str) -> str | None:
    """Return a base64 data URI for an image in assets/, or None if missing.

    Data URIs work inside st.markdown HTML and don't depend on any remote
    host staying up (the old Wikimedia thumbnail links started 404ing).
    """
    path = ASSETS_DIR / filename
    if not path.exists():
        return None
    mime = _MIME.get(path.suffix.lower(), "image/jpeg")
    encoded = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime};base64,{encoded}"


def landing_hero_src() -> str | None:
    """The user-provided landing image, if present (assets/landing.*)."""
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        uri = img_data_uri(f"landing{ext}")
        if uri:
            return uri
    return None


@st.cache_resource
def get_advisor():
    """Build one CareAdvisor for the whole app session.

    @st.cache_resource means this body only runs once, even though Streamlit
    re-runs scripts top-to-bottom on every interaction. Without caching,
    every rerun would reload and re-index all of knowledge/*.md.
    """
    return CareAdvisor(doc_store=DocStore())


def section_label(text: str) -> None:
    st.markdown(f"<span class='section-label'>{text}</span>", unsafe_allow_html=True)


def callout(kind: str, body_html: str) -> None:
    """kind is one of: good, warning, danger."""
    st.markdown(
        f"<div class='callout callout-{kind}'><span class='dot'></span>{body_html}</div>",
        unsafe_allow_html=True,
    )


def render_advisor_response(response):
    """Shared renderer for both AI features (Q&A and Plan Review) -- they
    return the same AdvisorResponse shape, so one function draws the answer,
    the confidence badge, any guardrail flag, and the sources expander.
    """
    if response.refused:
        callout("warning", response.answer)
        return

    confidence = response.confidence
    if confidence >= 80:
        tier_class, tier_label = "badge-good", "Grounded"
    elif confidence >= 40:
        tier_class, tier_label = "badge-mid", "Partial"
    else:
        tier_class, tier_label = "badge-low", "Weak / ungrounded"

    st.markdown(f"<div class='advisor-answer'>{response.answer}</div>", unsafe_allow_html=True)
    st.markdown(
        f"<span class='conf-badge {tier_class}'><span class='dot'></span>{tier_label}"
        f"<span class='conf-number'>{confidence}/100</span></span>",
        unsafe_allow_html=True,
    )

    if response.grounding and not response.grounding.grounded:
        callout("danger", f"Guardrail flag: {response.grounding.reason}")

    if response.retrieved:
        with st.expander(f"Sources ({len(response.retrieved)})"):
            for r in response.retrieved:
                st.markdown(
                    f"**[{r.chunk.id}] {r.chunk.doc_title}: {r.chunk.heading}** "
                    f"<span class='mono-muted'>similarity {r.score:.2f}</span>\n\n{r.chunk.text}",
                    unsafe_allow_html=True,
                )


def inject_css() -> None:
    """The PawPal+ playful design system.

    Direction: warm cream canvas, rounded friendly type (Baloo 2 display +
    Nunito body), a coral/teal/sun accent trio, chunky pill buttons with a
    springy press, soft gradient-mesh atmosphere. WCAG AA contrast and
    reduced-motion respected.
    """
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Baloo+2:wght@500;600;700;800&family=Nunito:ital,wght@0,400;0,500;0,600;0,700;0,800;1,600&family=DM+Mono:wght@400;500&display=swap');

        :root {
            --bg:        #FFF7EF;
            --bg-2:      #FFEBD9;
            --surface:   #FFFFFF;
            --border:    rgba(51, 38, 30, 0.10);
            --border-soft: rgba(51, 38, 30, 0.06);
            --text:      #33261E;
            --muted:     #6F625A;
            --muted-2:   #A99C92;
            --accent:      #0B7D71;   /* teal (interactive / primary) */
            --accent-hover:#0A6A60;
            --accent-wash: rgba(11, 125, 113, 0.12);
            --coral:       #FF6F52;   /* brand hero */
            --coral-deep:  #E24E30;
            --sun:         #FFC24B;   /* attention */
            --good-bg:   #E4F5F1;  --good-text:   #0B6C61; --good-border: rgba(11,125,113,0.22);
            --mid-bg:    #FFF3DA;  --mid-text:    #8A5A00; --mid-border: rgba(154,99,0,0.22);
            --low-bg:    #FFE9E3;  --low-text:    #B5350F; --low-border: rgba(181,53,15,0.22);
            --ease: cubic-bezier(0.4, 0, 0.2, 1);
            --spring: cubic-bezier(0.34, 1.56, 0.64, 1);
            --radius: 16px;
            --shadow: 0 1px 1px rgba(51,38,30,0.04), 0 8px 20px -12px rgba(51,38,30,0.16), 0 18px 40px -24px rgba(226,78,48,0.14);
            --shadow-hover: 0 1px 1px rgba(51,38,30,0.05), 0 14px 28px -12px rgba(51,38,30,0.22), 0 26px 52px -24px rgba(226,78,48,0.20);
        }

        /* Base fonts come from .streamlit/config.toml (Nunito body, Baloo 2
           headings). Do NOT force font-family on every span/div with
           !important: Material Symbols icons are font ligatures, and a global
           override turns them into raw text ("home", "arrow_forward") that
           overlaps the real labels. */
        html, body, .stApp {
            font-family: 'Nunito', sans-serif;
            color: var(--text);
        }
        code, .mono, .conf-number, .mono-muted {
            font-family: 'DM Mono', monospace !important;
        }

        /* ── Canvas: warm cream with a soft fixed gradient-mesh ───────────── */
        .stApp {
            background:
                radial-gradient(1200px 520px at 88% -6%, rgba(255,194,75,0.20), transparent 60%),
                radial-gradient(900px 480px at -8% 6%, rgba(255,111,82,0.16), transparent 58%),
                radial-gradient(1000px 560px at 60% 108%, rgba(11,125,113,0.12), transparent 60%),
                var(--bg);
            background-attachment: fixed;
        }
        /* Don't override padding-top: Streamlit computes it to clear the fixed
           header + top navigation. Forcing it smaller makes content slide
           underneath the nav and text overlap. */
        .block-container { padding-bottom: 3rem !important; }

        h1, h2, h3, h4 {
            font-family: 'Baloo 2', sans-serif;
            font-weight: 700;
            letter-spacing: -0.01em;
            color: var(--text);
        }

        /* ── Top navigation bar (st.navigation position="top") ────────────── */
        header[data-testid="stHeader"] {
            background: linear-gradient(180deg, rgba(255,247,239,0.95), rgba(255,247,239,0.75));
            backdrop-filter: blur(8px);
        }

        /* ── Landing hero ──────────────────────────────────────────────────── */
        .hero {
            display: flex;
            flex-direction: column;
            align-items: center;
            text-align: center;
            gap: 1.1rem;
            padding: 3.2rem 1rem 1.6rem;
        }
        .hero-eyebrow {
            font-family: 'Baloo 2', sans-serif;
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.18em;
            text-transform: uppercase;
            color: var(--coral-deep);
        }
        .hero-title {
            font-family: 'Baloo 2', sans-serif;
            font-size: clamp(3rem, 2rem + 5vw, 5.4rem);
            font-weight: 800;
            letter-spacing: -0.02em;
            line-height: 1.0;
            background: linear-gradient(105deg, var(--coral-deep), var(--coral) 55%, var(--sun));
            -webkit-background-clip: text;
            background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .hero-tagline {
            font-size: 1.12rem;
            font-weight: 600;
            color: var(--muted);
            max-width: 46ch;
        }
        .hero-images { display: flex; gap: 1rem; align-items: flex-end; margin-top: 0.8rem; }
        .hero-images img {
            border-radius: 22px;
            object-fit: cover;
            border: 4px solid var(--surface);
            box-shadow: var(--shadow);
            transition: transform 0.3s var(--spring), box-shadow 0.3s var(--ease);
        }
        .hero-images .hero-single { width: min(420px, 78vw); height: auto; transform: rotate(-1.5deg); }
        .hero-images .hero-a { width: 168px; height: 208px; transform: rotate(-4deg); }
        .hero-images .hero-b { width: 132px; height: 164px; margin-bottom: 10px; transform: rotate(5deg); }
        .hero-images img:hover { transform: translateY(-5px) rotate(0deg) scale(1.03); box-shadow: var(--shadow-hover); }

        /* ── Dashboard page header ─────────────────────────────────────────── */
        .topbar {
            display: grid;
            grid-template-columns: 1fr auto;
            align-items: end;
            gap: 1.5rem;
            padding: 1.2rem 1.5rem 1.3rem;
            margin-bottom: 1.6rem;
            background: linear-gradient(135deg, rgba(255,255,255,0.92), rgba(255,255,255,0.58));
            border: 1px solid var(--border-soft);
            border-radius: 24px;
            box-shadow: var(--shadow);
        }
        .topbar-left { display: flex; flex-direction: column; gap: 0.35rem; }
        .topbar-eyebrow {
            font-family: 'Baloo 2', sans-serif;
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            color: var(--coral-deep);
        }
        .topbar-title {
            font-family: 'Baloo 2', sans-serif;
            font-size: clamp(1.6rem, 1rem + 1.5vw, 2.2rem);
            font-weight: 800;
            letter-spacing: -0.02em;
            line-height: 1.05;
            background: linear-gradient(105deg, var(--coral-deep), var(--coral) 55%, var(--sun));
            -webkit-background-clip: text;
            background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .topbar-subtitle { font-size: 0.98rem; color: var(--muted); max-width: 44ch; font-weight: 500; }
        .topbar-avatars { display: flex; gap: 0.6rem; align-items: flex-end; }
        .topbar-avatars img {
            border-radius: 18px;
            object-fit: cover;
            border: 3px solid var(--surface);
            box-shadow: var(--shadow);
            transition: transform 0.3s var(--spring), box-shadow 0.3s var(--ease);
        }
        .topbar-avatars img:first-child { width: 60px; height: 74px; transform: rotate(-4deg); }
        .topbar-avatars img:last-child  { width: 46px; height: 58px; margin-bottom: 6px; transform: rotate(5deg); }
        .topbar-avatars img:hover { transform: translateY(-4px) rotate(0deg) scale(1.05); box-shadow: var(--shadow-hover); }

        @media (max-width: 640px) {
            .topbar { grid-template-columns: 1fr; }
            .topbar-avatars { display: none; }
        }

        /* ── Section label: playful gradient chip marker ──────────────────── */
        .section-label {
            font-family: 'Baloo 2', sans-serif;
            font-size: 0.74rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: var(--accent);
            margin-bottom: 0.5rem;
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
        }
        .section-label::before {
            content: "";
            width: 12px;
            height: 12px;
            border-radius: 5px;
            background: linear-gradient(135deg, var(--coral), var(--sun));
            box-shadow: 0 2px 6px -1px rgba(226,78,48,0.5);
        }

        /* ── Stat blocks (dashboard "at a glance" card) ────────────────────── */
        .stat-value {
            font-family: 'Baloo 2', sans-serif;
            font-size: 1.7rem;
            font-weight: 800;
            line-height: 1.1;
            color: var(--text);
        }
        .stat-label { font-size: 0.82rem; font-weight: 700; color: var(--muted-2); text-transform: uppercase; letter-spacing: 0.06em; }

        /* ── Status dot ────────────────────────────────────────────────────── */
        .dot {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: currentColor;
            margin-right: 0.55rem;
            vertical-align: middle;
        }

        /* ── Buttons: chunky pills with a springy press ────────────────────── */
        .stButton>button, div[data-testid="stFormSubmitButton"] button {
            background: var(--accent);
            color: #FFFFFF;
            border: none;
            border-radius: 999px;
            font-family: 'Baloo 2', sans-serif;
            font-weight: 700;
            font-size: 0.98rem;
            letter-spacing: 0.01em;
            padding: 0.55rem 1.5rem;
            min-height: 44px;
            box-shadow: 0 6px 0 -1px var(--accent-hover), var(--shadow);
            transition: transform 0.18s var(--spring), box-shadow 0.18s var(--ease), background 0.18s var(--ease);
        }
        .stButton>button:hover, div[data-testid="stFormSubmitButton"] button:hover {
            background: var(--accent-hover);
            transform: translateY(-2px);
            box-shadow: 0 8px 0 -1px var(--accent-hover), var(--shadow-hover);
        }
        .stButton>button:active, div[data-testid="stFormSubmitButton"] button:active {
            transform: translateY(3px);
            box-shadow: 0 2px 0 -1px var(--accent-hover), var(--shadow);
        }
        .stButton>button:focus-visible, div[data-testid="stFormSubmitButton"] button:focus-visible {
            outline: 3px solid var(--sun);
            outline-offset: 2px;
        }
        /* Button label text (p only, never the icon span, which must keep
           its Material Symbols ligature font). */
        .stButton>button p, div[data-testid="stFormSubmitButton"] button p {
            font-family: 'Baloo 2', sans-serif !important;
            font-weight: 700 !important;
            color: #FFFFFF !important;
        }

        /* ── Inputs: rounded with a soft focus halo ────────────────────────── */
        .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] > div {
            border-radius: 12px !important;
            border: 2px solid var(--border) !important;
            background: var(--surface) !important;
            transition: border-color 0.2s var(--ease), box-shadow 0.2s var(--ease);
        }
        .stTextInput input:focus, .stNumberInput input:focus {
            border-color: var(--accent) !important;
            box-shadow: 0 0 0 4px var(--accent-wash) !important;
        }
        label p { font-size: 0.9rem !important; color: var(--muted) !important; font-weight: 700 !important; }

        /* ── Cards: rounded, warm shadow, gentle lift on hover ─────────────── */
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: var(--radius) !important;
            border: 1px solid var(--border-soft) !important;
            background: var(--surface);
            box-shadow: var(--shadow);
            transition: box-shadow 0.28s var(--ease), transform 0.28s var(--spring);
            padding: 0.4rem;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:hover {
            box-shadow: var(--shadow-hover);
            transform: translateY(-2px);
        }

        /* ── Segmented control: match the pill language ────────────────────── */
        div[data-testid="stSegmentedControl"] button {
            border-radius: 999px !important;
            font-family: 'Baloo 2', sans-serif;
            font-weight: 700;
        }

        /* ── Sidebar ───────────────────────────────────────────────────────── */
        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #FFFFFF, #FFF3E8);
            border-right: 1px solid var(--border-soft);
        }
        section[data-testid="stSidebar"] .block-container { padding-top: 2.5rem !important; }

        /* ── Callouts: tone-on-tone, rounded, geometric dot marker ─────────── */
        .callout {
            border-radius: 14px;
            border: 1px solid var(--border-soft);
            padding: 0.85rem 1.1rem;
            margin: 0.5rem 0;
            font-size: 0.96rem;
            font-weight: 600;
            display: flex;
            align-items: flex-start;
        }
        .callout-good    { background: var(--good-bg); border-color: var(--good-border); color: var(--good-text); }
        .callout-warning { background: var(--mid-bg);  border-color: var(--mid-border);  color: var(--mid-text); }
        .callout-danger  { background: var(--low-bg);  border-color: var(--low-border);  color: var(--low-text); }

        /* ── Advisor answer block ──────────────────────────────────────────── */
        .advisor-answer {
            background: var(--surface);
            border: 1px solid var(--border-soft);
            border-left: 5px solid var(--coral);
            padding: 1.1rem 1.3rem;
            border-radius: 16px;
            margin-bottom: 0.6rem;
            line-height: 1.65;
            font-weight: 500;
            box-shadow: var(--shadow);
        }
        .conf-badge {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 0.3rem 0.85rem;
            font-family: 'Baloo 2', sans-serif;
            font-size: 0.8rem;
            font-weight: 700;
            letter-spacing: 0.01em;
            border: 1px solid transparent;
        }
        .badge-good { background: var(--good-bg); color: var(--good-text); border-color: var(--good-border); }
        .badge-mid  { background: var(--mid-bg);  color: var(--mid-text);  border-color: var(--mid-border); }
        .badge-low  { background: var(--low-bg);  color: var(--low-text);  border-color: var(--low-border); }
        .conf-number { opacity: 0.85; margin-left: 0.5rem; }
        .mono-muted { color: var(--muted); font-size: 0.85rem; }

        /* ── Respect users who prefer reduced motion ───────────────────────── */
        @media (prefers-reduced-motion: reduce) {
            *, *::before, *::after {
                animation-duration: 0.01ms !important;
                transition-duration: 0.01ms !important;
            }
            .topbar-avatars img, .hero-images img { transform: none; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
