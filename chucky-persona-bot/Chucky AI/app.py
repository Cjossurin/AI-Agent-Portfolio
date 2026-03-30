"""Chucky AI — Streamlit UI

An alternative visual interface for the Chucky AI horror-video pipeline.
Run with:  streamlit run app.py
"""

import json
import logging
import re
from collections import Counter
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-28s | %(levelname)-7s | %(message)s",
)
logger = logging.getLogger("chucky-ui")

# ── Agent imports ─────────────────────────────────────────────────────
from agents.brainstormer import IdeaGenerator, STORY_CATEGORIES, CATEGORY_NAMES
from agents.researcher import AnomalyResearcher
from agents.writer import NarrativeScriptwriter
from agents.director import VisualTechnicalDirector, VALID_STYLES
from agents.integrator import MediaIntegrator, DEFAULT_STYLE_STRENGTH
from agents.seo import SEOMetadataAgent
from agents.captioner import Captioner
from agents.composer import RemotionComposer
from agents.publisher import VideoPublisher

# ── Case-ID helpers (mirrored from main.py) ──────────────────────────

_case_counter_path = Path("assets/.case_counter")


def _next_case_number() -> int:
    Path("assets").mkdir(parents=True, exist_ok=True)
    if _case_counter_path.is_file():
        n = int(_case_counter_path.read_text().strip())
    else:
        n = len(list(Path("assets").glob("case_*")))
    n += 1
    _case_counter_path.write_text(str(n))
    return n


def _make_case_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    slug = "_".join(word.capitalize() for word in slug.split("_") if word)
    num = _next_case_number()
    return f"{num:02d}_{slug}"


# ── Friendly display names ────────────────────────────────────────────

CATEGORY_DISPLAY = {
    "real_world_unexplained": "🌍 Real-World Unexplained Events",
    "unexplained_broadcasts": "📡 Hijacked Signals & Number Stations",
    "urban_legends": "👻 Urban Legends & Haunted Places",
    "historical_encounters": "🐾 Historical Creature Encounters",
    "vanishings_cryptids": "🕳️ Vanishings & Cryptid Sightings",
}

STYLE_DISPLAY = {
    "dark_comic": "🎨 Cartoon",
    "vintage_illustration": "🖋️ Vintage",
}

# ── History helper ────────────────────────────────────────────────────

HISTORY_FILE = Path("used_topics.json")


def _load_history() -> list[dict]:
    if HISTORY_FILE.is_file():
        try:
            data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            return data.get("topics", [])
        except (json.JSONDecodeError, OSError):
            pass
    return []


# ── Session-state defaults ────────────────────────────────────────────

_DEFAULTS = {
    "pipeline_state": "idle",
    "topic": None,
    "category": None,
    "case_id": None,
    "case_data": None,
    "script_data": None,
    "storyboard_data": None,
    "media_manifest": None,
    "captions_data": None,
    "metadata": None,
    "video_path": None,
    "publish_results": None,
    "error": None,
}

for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ── Page config ───────────────────────────────────────────────────────

st.set_page_config(
    page_title="Chucky AI — Department of the Unknown",
    page_icon="💀",
    layout="wide",
)

# ── Horror theme CSS ──────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Creepster&family=Special+Elite&family=Nosifer&display=swap');

/* ── Root dark horror palette ── */
:root {
    --blood: #8B0000;
    --blood-glow: #CC0000;
    --bone: #D4C5A9;
    --fog: #2A2A2A;
    --abyss: #0A0A0A;
    --phantom: #1A1A1A;
    --mist: #888;
    --sickly: #4A7A3A;
    --ember: #FF4500;
}

/* ── Main background ── */
.stApp {
    background: linear-gradient(180deg, #0A0A0A 0%, #111 40%, #0D0D0D 100%) !important;
}

/* ── Flicker animation for title ── */
@keyframes flicker {
    0%, 19%, 21%, 23%, 25%, 54%, 56%, 100% { opacity: 1; }
    20%, 24%, 55% { opacity: 0.4; }
}

@keyframes bloodDrip {
    0% { text-shadow: 0 0 10px #8B0000, 0 0 20px #8B0000, 0 0 40px #CC0000; }
    50% { text-shadow: 0 0 15px #CC0000, 0 0 30px #8B0000, 0 0 60px #660000; }
    100% { text-shadow: 0 0 10px #8B0000, 0 0 20px #8B0000, 0 0 40px #CC0000; }
}

/* ── Scanline overlay (VHS feel) ── */
.stApp::before {
    content: '';
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: repeating-linear-gradient(
        0deg,
        transparent,
        transparent 2px,
        rgba(0,0,0,0.03) 2px,
        rgba(0,0,0,0.03) 4px
    );
    pointer-events: none;
    z-index: 1000;
}

/* ── Main title styling ── */
.stApp h1 {
    font-family: 'Nosifer', cursive !important;
    color: #8B0000 !important;
    animation: bloodDrip 3s ease-in-out infinite;
    letter-spacing: 2px;
    text-transform: uppercase;
    font-size: 2rem !important;
    border-bottom: 1px solid #333;
    padding-bottom: 15px;
}

/* ── Subheaders ── */
.stApp h2, .stApp h3 {
    font-family: 'Creepster', cursive !important;
    color: #CC0000 !important;
    letter-spacing: 1.5px;
}

/* ── Body text ── */
.stApp p, .stApp span, .stApp label, .stApp li {
    font-family: 'Special Elite', cursive !important;
    color: #D4C5A9 !important;
}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0D0D0D 0%, #1A0A0A 50%, #0D0D0D 100%) !important;
    border-right: 2px solid #3A0A0A !important;
}

section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2 {
    font-family: 'Creepster', cursive !important;
    color: #CC0000 !important;
    text-shadow: 0 0 8px rgba(139,0,0,0.6);
    letter-spacing: 2px;
}

/* ── Sidebar dividers ── */
section[data-testid="stSidebar"] hr {
    border-color: #3A0A0A !important;
}

/* ── Radio buttons ── */
.stRadio > label {
    font-family: 'Special Elite', cursive !important;
    color: #D4C5A9 !important;
}
div[role="radiogroup"] label {
    font-family: 'Special Elite', cursive !important;
    color: #AAA !important;
}
div[role="radiogroup"] label[data-checked="true"],
div[role="radiogroup"] label:hover {
    color: #CC0000 !important;
}

/* ── Selectbox ── */
.stSelectbox label {
    font-family: 'Special Elite', cursive !important;
    color: #D4C5A9 !important;
}

/* ── Primary button (Run Pipeline / Approve) ── */
.stButton > button[kind="primary"],
.stButton > button[data-testid="stBaseButton-primary"] {
    background: linear-gradient(135deg, #8B0000 0%, #4A0000 100%) !important;
    border: 1px solid #CC0000 !important;
    color: #FFF !important;
    font-family: 'Creepster', cursive !important;
    font-size: 1.1rem !important;
    letter-spacing: 2px;
    text-transform: uppercase;
    transition: all 0.3s ease;
    box-shadow: 0 0 15px rgba(139,0,0,0.3);
}
.stButton > button[kind="primary"]:hover,
.stButton > button[data-testid="stBaseButton-primary"]:hover {
    background: linear-gradient(135deg, #CC0000 0%, #8B0000 100%) !important;
    box-shadow: 0 0 25px rgba(204,0,0,0.5), 0 0 50px rgba(139,0,0,0.3) !important;
    transform: scale(1.02);
}

/* ── Secondary buttons ── */
.stButton > button:not([kind="primary"]):not([data-testid="stBaseButton-primary"]) {
    background: rgba(30,30,30,0.8) !important;
    border: 1px solid #444 !important;
    color: #D4C5A9 !important;
    font-family: 'Special Elite', cursive !important;
    letter-spacing: 1px;
    transition: all 0.3s ease;
}
.stButton > button:not([kind="primary"]):not([data-testid="stBaseButton-primary"]):hover {
    border-color: #8B0000 !important;
    color: #CC0000 !important;
    box-shadow: 0 0 10px rgba(139,0,0,0.3);
}

/* ── Metrics ── */
div[data-testid="stMetric"] {
    background: rgba(20,5,5,0.6) !important;
    border: 1px solid #2A0A0A !important;
    border-radius: 8px;
    padding: 15px !important;
}
div[data-testid="stMetric"] label {
    color: #888 !important;
    font-family: 'Special Elite', cursive !important;
    text-transform: uppercase;
    font-size: 0.75rem !important;
    letter-spacing: 1px;
}
div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
    color: #CC0000 !important;
    font-family: 'Creepster', cursive !important;
    font-size: 1.8rem !important;
}

/* ── Status containers (pipeline phases) ── */
details[data-testid="stExpander"],
div[data-testid="stStatusWidget"] {
    background: rgba(15,5,5,0.5) !important;
    border: 1px solid #2A0A0A !important;
    border-radius: 6px;
}

/* ── Expanders ── */
details[data-testid="stExpander"] summary span {
    font-family: 'Creepster', cursive !important;
    color: #CC0000 !important;
    letter-spacing: 1px;
}

/* ── Progress bar ── */
div[data-testid="stProgress"] > div > div > div {
    background: linear-gradient(90deg, #8B0000, #CC0000, #8B0000) !important;
    box-shadow: 0 0 10px rgba(204,0,0,0.5);
}

/* ── Info / warning / success / error boxes ── */
div[data-testid="stAlert"][data-type="info"] {
    background: rgba(10,10,30,0.6) !important;
    border-left: 4px solid #3A3A8B !important;
    color: #8888CC !important;
}
div[data-testid="stAlert"][data-type="success"] {
    background: rgba(10,30,10,0.6) !important;
    border-left: 4px solid #4A7A3A !important;
}
div[data-testid="stAlert"][data-type="error"] {
    background: rgba(30,5,5,0.6) !important;
    border-left: 4px solid #8B0000 !important;
}
div[data-testid="stAlert"][data-type="warning"] {
    background: rgba(30,20,5,0.6) !important;
    border-left: 4px solid #8B6500 !important;
}

/* ── JSON viewer ── */
pre {
    background: #0D0D0D !important;
    border: 1px solid #222 !important;
    color: #4A7A3A !important;
    font-family: 'Courier New', monospace !important;
}

/* ── Toast notifications ── */
div[data-testid="stToast"] {
    background: #1A0A0A !important;
    border: 1px solid #8B0000 !important;
    color: #D4C5A9 !important;
}

/* ── Dividers ── */
hr {
    border-color: #2A0A0A !important;
}

/* ── Video player container ── */
video {
    border: 2px solid #3A0A0A !important;
    border-radius: 8px;
    box-shadow: 0 0 30px rgba(139,0,0,0.2);
}

/* ── Captions / small text ── */
.stCaption, small, .stApp figcaption {
    color: #666 !important;
    font-family: 'Special Elite', cursive !important;
    font-style: italic;
}

/* ── Links ── */
a {
    color: #CC0000 !important;
    text-decoration: none !important;
}
a:hover {
    color: #FF4500 !important;
    text-shadow: 0 0 5px rgba(204,0,0,0.5);
}

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 8px; }
::-webkit-scrollbar-track { background: #0A0A0A; }
::-webkit-scrollbar-thumb { background: #3A0A0A; border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: #8B0000; }
</style>
""", unsafe_allow_html=True)


# ── Horror-themed title ───────────────────────────────────────────────

st.markdown("""
<div style="text-align: center; margin-bottom: 5px;">
    <p style="font-family: 'Special Elite', cursive; color: #555; font-size: 0.85rem;
       letter-spacing: 4px; text-transform: uppercase; margin: 0;">
       ▸ C L A S S I F I E D &nbsp; S Y S T E M &nbsp; T E R M I N A L ◂
    </p>
</div>
""", unsafe_allow_html=True)

st.title("💀 CHUCKY AI")

st.markdown("""
<div style="text-align: center; margin-top: -10px; margin-bottom: 25px;">
    <p style="font-family: 'Special Elite', cursive; color: #666; font-size: 0.9rem;
       letter-spacing: 3px;">
       Department of the Unknown — Case File Generator
    </p>
    <div style="width: 60%; margin: 0 auto; height: 1px;
         background: linear-gradient(90deg, transparent, #8B0000, transparent);"></div>
</div>
""", unsafe_allow_html=True)


# ── Sidebar ───────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("""
    <div style="text-align: center; padding: 10px 0 5px 0;">
        <span style="font-size: 2.5rem;">🕯️</span>
        <h2 style="font-family: 'Creepster', cursive; color: #CC0000;
            margin: 5px 0; letter-spacing: 3px;">CONTROL ROOM</h2>
        <p style="font-family: 'Special Elite', cursive; color: #555;
           font-size: 0.75rem; letter-spacing: 2px;">AUTHORIZED PERSONNEL ONLY</p>
    </div>
    """, unsafe_allow_html=True)

    mode_labels = {
        "full_auto": "🎲 Full Auto (AI picks category + subject)",
        "category_ai": "📂 Pick Category, AI picks subject",
        "manual_subject": "✍️ Manual Subject Input",
    }
    mode_keys = list(mode_labels.keys())
    mode_choice = st.radio(
        "⛧ Subject Mode",
        range(len(mode_keys)),
        format_func=lambda i: mode_labels[mode_keys[i]],
        index=0,
        disabled=st.session_state.pipeline_state == "running",
    )
    selected_mode = mode_keys[mode_choice]

    manual_topic = None
    manual_category = None
    if selected_mode in ("category_ai", "manual_subject"):
        cat_labels = list(CATEGORY_DISPLAY.values())
        cat_keys = list(CATEGORY_DISPLAY.keys())
        if selected_mode == "category_ai":
            cat_idx = st.selectbox(
                "📂 Case Category",
                range(len(cat_labels)),
                format_func=lambda i: cat_labels[i],
                disabled=st.session_state.pipeline_state == "running",
            )
            manual_category = cat_keys[cat_idx]
        else:
            manual_topic = st.text_input(
                "📝 Subject",
                placeholder="e.g. The Hinterkaifeck Farm Murders",
                disabled=st.session_state.pipeline_state == "running",
            )
            cat_options = ["None (optional)"] + cat_labels
            cat_choice = st.selectbox(
                "📂 Case Category (optional)",
                range(len(cat_options)),
                format_func=lambda i: cat_options[i],
                disabled=st.session_state.pipeline_state == "running",
            )
            if cat_choice > 0:
                manual_category = cat_keys[cat_choice - 1]

    style_labels = list(STYLE_DISPLAY.values())
    style_keys = list(STYLE_DISPLAY.keys())
    style_choice = st.radio(
        "🎞️ Content Type",
        range(len(style_labels)),
        format_func=lambda i: style_labels[i],
        disabled=st.session_state.pipeline_state == "running",
    )
    manual_style = style_keys[style_choice]

    style_strength = st.slider(
        "🏚️ Style Strength",
        min_value=0.0,
        max_value=1.0,
        value=DEFAULT_STYLE_STRENGTH,
        step=0.05,
        help=(
            "Controls how strongly the reference image influences the output. "
            "0 = ignore reference (photorealistic), 1 = copy reference exactly. "
            "Default 0.5 balances prompt fidelity with style transfer."
        ),
        disabled=st.session_state.pipeline_state == "running",
    )

    st.divider()

    run_clicked = st.button(
        "⚡ INITIATE SEQUENCE",
        type="primary",
        use_container_width=True,
        disabled=st.session_state.pipeline_state in ("running", "video_ready"),
    )

    st.divider()

    # Pipeline history
    history = _load_history()
    st.metric("☠️ Cases Filed", len(history))

    st.markdown("""
    <div style="text-align: center; margin-top: 20px; padding: 10px;
         border-top: 1px solid #2A0A0A;">
        <p style="font-family: 'Special Elite', cursive; color: #333;
           font-size: 0.7rem; letter-spacing: 1px;">
           CHUCKY AI v1.0<br>
           ⚠ MEMETIC HAZARD WARNING ⚠
        </p>
    </div>
    """, unsafe_allow_html=True)


# ── Pipeline runner ───────────────────────────────────────────────────

def _reset_state():
    for k, v in _DEFAULTS.items():
        st.session_state[k] = v


def run_pipeline(
    input_mode: str,
    m_category: str | None,
    m_style: str | None,
    m_topic: str | None = None,
    m_strength: float | None = None,
):
    """Execute the full pipeline phases 0-6, updating Streamlit UI."""

    ss = st.session_state
    ss.pipeline_state = "running"
    ss.error = None
    ss.publish_results = None

    progress = st.progress(0, text="Initializing dark protocols…")
    phases = st.container()

    total = 7  # phases 0 through 6

    try:
        brainstormer = IdeaGenerator()

        # ── Phase 0: Brainstormer ─────────────────────────────────────
        phase_0_label = (
            "Phase 0 — Input Subject"
            if input_mode == "manual_subject"
            else "Phase 0 — The Brainstormer"
        )
        with phases.status(phase_0_label, expanded=True) as s:
            progress.progress(0 / total, text="Phase 0: Preparing case subject…")
            if input_mode == "manual_subject":
                topic = (m_topic or "").strip()
                if not topic:
                    raise ValueError(
                        "Manual Subject Input requires a subject. "
                        "Please enter one in the sidebar.",
                    )
                category = m_category
                st.write("**Mode:** Manual subject input")
            elif input_mode == "category_ai":
                if not m_category:
                    raise ValueError("Please choose a case category.")
                topic, category = brainstormer.generate_topic(
                    category_override=m_category,
                )
                st.write("**Mode:** Category + AI subject")
            else:
                topic, category = brainstormer.generate_topic()
                st.write("**Mode:** Full auto")

            ss.topic = topic
            ss.category = category

            st.write(f"**Topic:** {topic}")
            if category:
                st.write(f"**Category:** {CATEGORY_DISPLAY.get(category, category)}")
            else:
                st.write("**Category:** None selected")
            s.update(label=f"{phase_0_label} ☑", state="complete")

        # ── Phase 1: Researcher ───────────────────────────────────────
        with phases.status("Phase 1 — The Anomaly Researcher", expanded=True) as s:
            progress.progress(1 / total, text="Phase 1: Unearthing buried records…")
            researcher = AnomalyResearcher()
            case_data = researcher.research_case(topic)
            brainstormer.save_topic(topic, category)
            ss.case_data = case_data

            case_name = case_data.get("case_name", topic)
            st.write(f"**Case name:** {case_name}")
            s.update(label="Phase 1 — The Anomaly Researcher ☑", state="complete")

        # ── Phase 2: Writer ───────────────────────────────────────────
        with phases.status("Phase 2 — The Scriptwriter", expanded=True) as s:
            progress.progress(2 / total, text="Phase 2: Channeling the narration…")
            writer = NarrativeScriptwriter()
            script_data = writer.write_script(case_data)
            ss.script_data = script_data

            blocks = script_data.get("narration_blocks", [])
            st.write(f"**Narration blocks:** {len(blocks)}")
            if blocks:
                preview = re.sub(r"<[^>]+>", "", blocks[0].get("text", ""))
                st.caption(preview[:200] + ("…" if len(preview) > 200 else ""))
            s.update(label="Phase 2 — The Scriptwriter ☑", state="complete")

        # ── Phase 3: Director ─────────────────────────────────────────
        with phases.status("Phase 3 — The Visual Director", expanded=True) as s:
            progress.progress(3 / total, text="Phase 3: Composing the nightmare…")
            director = VisualTechnicalDirector()
            storyboard_data = director.create_storyboard(
                script_data,
                force_style=m_style,
                category=category,
            )
            ss.storyboard_data = storyboard_data
            chosen_style = storyboard_data.get("chosen_style", "unknown")

            st.write(f"**Art style:** {STYLE_DISPLAY.get(chosen_style, chosen_style)}")
            st.write(f"**Storyboard frames:** {len(storyboard_data.get('storyboard', []))}")
            s.update(label="Phase 3 — The Visual Director ☑", state="complete")

        # ── Phase 4: Media Generation ─────────────────────────────────
        with phases.status("Phase 4 — Media Synthesis", expanded=True) as s:
            progress.progress(4 / total, text="Phase 4: Manifesting audio & visuals…")
            case_id = _make_case_id(case_data.get("case_name", topic))
            ss.case_id = case_id
            integrator = MediaIntegrator(style_strength=m_strength)
            media_manifest = integrator.generate_media(storyboard_data, case_id)
            ss.media_manifest = media_manifest

            st.write(f"**Case ID:** {case_id}")
            st.write(f"**Blocks generated:** {len(media_manifest.get('blocks', []))}")
            s.update(label="Phase 4 — Media Synthesis ☑", state="complete")

        # ── Phase 4.5: Captions ───────────────────────────────────────
        with phases.status("Phase 4.5 — Caption Extraction", expanded=True) as s:
            progress.progress(4.5 / total, text="Phase 4.5: Extracting whispered words…")
            captioner = Captioner()
            captions_data = captioner.generate_captions(case_id, media_manifest)
            ss.captions_data = captions_data

            st.write("**Word-level captions extracted**")
            s.update(label="Phase 4.5 — Caption Extraction ☑", state="complete")

        # ── Phase 5: SEO Metadata ─────────────────────────────────────
        with phases.status("Phase 5 — SEO Metadata", expanded=True) as s:
            progress.progress(5 / total, text="Phase 5: Encoding transmission tags…")
            seo = SEOMetadataAgent()
            metadata = seo.generate_metadata(case_id, case_data, script_data)
            ss.metadata = metadata

            yt = metadata.get("youtube_metadata", {})
            st.write(f"**YouTube title:** {yt.get('title', yt.get('shorts_title', 'N/A'))}")
            s.update(label="Phase 5 — SEO Metadata ☑", state="complete")

        # ── Phase 6: Remotion Render ──────────────────────────────────
        with phases.status("Phase 6 — Final Render", expanded=True) as s:
            progress.progress(6 / total, text="Phase 6: Assembling the footage…")
            composer = RemotionComposer()
            composer.build_video(case_id, media_manifest, captions_data)

            out_dir = Path("out")
            canonical = out_dir / f"case_{case_id}_final.mp4"
            if not canonical.is_file():
                candidates = sorted(out_dir.glob(f"case_{case_id}*.mp4"))
                if candidates:
                    candidates[0].rename(canonical)

            ss.video_path = str(canonical) if canonical.is_file() else None
            st.write(f"**Video:** {canonical.name}")
            s.update(label="Phase 6 — Final Render ☑", state="complete")

        progress.progress(1.0, text="☠ Sequence complete — review the footage below")
        ss.pipeline_state = "video_ready"
        st.toast("The footage is ready for your review…", icon="💀")

    except Exception as exc:
        logger.exception("Pipeline error")
        ss.pipeline_state = "idle"
        ss.error = str(exc)
        st.error(f"⚠ SYSTEM FAILURE: {exc}")


# ── Trigger pipeline ──────────────────────────────────────────────────

if run_clicked:
    _reset_state()
    run_pipeline(selected_mode, manual_category, manual_style, manual_topic, style_strength)

# ── Video review & publish ────────────────────────────────────────────

if st.session_state.pipeline_state == "video_ready":
    st.divider()

    st.markdown("""
    <h2 style="font-family: 'Creepster', cursive; color: #CC0000; text-align: center;
        letter-spacing: 3px; text-shadow: 0 0 10px rgba(139,0,0,0.5);">
        🎥 EVIDENCE REVIEW
    </h2>
    <p style="text-align: center; font-family: 'Special Elite', cursive; color: #555;
       font-size: 0.8rem;">Review the footage before authorizing transmission</p>
    """, unsafe_allow_html=True)

    video_path = st.session_state.video_path
    if video_path and Path(video_path).is_file():
        st.video(video_path)
    else:
        st.warning("⚠ Footage not found — the render may have failed.")

    # Show metadata
    metadata = st.session_state.metadata
    if metadata:
        with st.expander("📋 Transmission Metadata", expanded=False):
            yt = metadata.get("youtube_metadata", {})
            if yt:
                st.markdown(f"**Title:** {yt.get('title', yt.get('shorts_title', ''))}")
            tik = metadata.get("tiktok_metadata", {})
            if tik:
                st.markdown(f"**TikTok:** {tik.get('video_caption', '')}")
            st.json(metadata)

    col1, col2 = st.columns(2)

    with col1:
        if st.button("⚡ AUTHORIZE TRANSMISSION", type="primary", use_container_width=True):
            st.session_state.pipeline_state = "publishing"
            st.rerun()

    with col2:
        if st.button("🚫 TERMINATE CASE", use_container_width=True):
            case_id = st.session_state.case_id
            st.toast(f"Case {case_id} has been terminated.", icon="🗑️")
            _reset_state()
            st.rerun()

# ── Publishing ────────────────────────────────────────────────────────

if st.session_state.pipeline_state == "publishing":
    st.divider()

    st.markdown("""
    <h2 style="font-family: 'Creepster', cursive; color: #CC0000; text-align: center;
        letter-spacing: 3px;">📡 TRANSMITTING…</h2>
    """, unsafe_allow_html=True)

    try:
        with st.status("Broadcasting to all channels…", expanded=True) as s:
            publisher = VideoPublisher()
            results = publisher.publish(
                st.session_state.case_id, st.session_state.metadata,
            )
            st.session_state.publish_results = results
            st.session_state.pipeline_state = "published"
            s.update(label="Transmission complete ☑", state="complete")
        st.rerun()
    except Exception as exc:
        logger.exception("Publish error")
        st.error(f"⚠ TRANSMISSION FAILURE: {exc}")
        st.session_state.pipeline_state = "video_ready"

# ── Published results ─────────────────────────────────────────────────

if st.session_state.pipeline_state == "published":
    st.divider()

    st.markdown("""
    <h2 style="font-family: 'Creepster', cursive; color: #4A7A3A; text-align: center;
        letter-spacing: 3px; text-shadow: 0 0 10px rgba(74,122,58,0.5);">
        ☠ TRANSMISSION SUCCESSFUL
    </h2>
    """, unsafe_allow_html=True)

    results = st.session_state.publish_results or {}
    platform_icons = {
        "tiktok": "🎵", "youtube": "▶️", "instagram": "📸",
        "facebook": "📘", "x": "𝕏",
    }

    for platform, result in results.items():
        icon = platform_icons.get(platform, "📱")
        status = result.get("status", "unknown")
        if status == "success":
            resp = result.get("response", {})
            post = resp.get("post", {})
            platforms_data = post.get("platforms", [{}])
            url = None
            if platforms_data:
                url = platforms_data[0].get("platformPostUrl")
            if url:
                st.success(f"{icon} **{platform.title()}** — [View Post]({url})")
            else:
                st.success(f"{icon} **{platform.title()}** — Transmitted")
        elif status == "skipped":
            st.info(f"{icon} **{platform.title()}** — Already published (skipped)")
        elif status == "pending":
            st.warning(f"{icon} **{platform.title()}** — ⏳ Unconfirmed — re-run to check status")
        else:
            err = result.get("error", "Unknown error")
            st.error(f"{icon} **{platform.title()}** — {err}")

    st.divider()
    if st.button("🔄 OPEN NEW CASE FILE", use_container_width=True):
        _reset_state()
        st.rerun()

# ── Idle state ────────────────────────────────────────────────────────

if st.session_state.pipeline_state == "idle" and not st.session_state.error:
    st.divider()

    st.markdown("""
    <div style="text-align: center; padding: 40px 20px; margin: 20px 0;
         border: 1px solid #1A0A0A; border-radius: 10px;
         background: radial-gradient(ellipse at center, rgba(139,0,0,0.05) 0%, transparent 70%);">
        <p style="font-family: 'Creepster', cursive; color: #8B0000; font-size: 1.5rem;
           letter-spacing: 3px; margin-bottom: 10px;">AWAITING INSTRUCTIONS</p>
        <p style="font-family: 'Special Elite', cursive; color: #555; font-size: 0.9rem;">
            Configure parameters in the Control Room and press<br>
            <span style="color: #CC0000; font-weight: bold;">⚡ INITIATE SEQUENCE</span>
            to generate a new case file.
        </p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("☠️ Cases Filed", len(_load_history()))
    with col2:
        sh_file = Path("style_history.json")
        last_style = "—"
        if sh_file.is_file():
            try:
                styles = json.loads(sh_file.read_text(encoding="utf-8"))
                if styles:
                    last_style = STYLE_DISPLAY.get(styles[-1], styles[-1])
            except (json.JSONDecodeError, OSError):
                pass
        st.metric("🖌️ Last Protocol", last_style)
    with col3:
        history_items = _load_history()
        if history_items:
            cats = Counter(t.get("category", "?") for t in history_items)
            top = cats.most_common(1)[0][0]
            st.metric("📂 Top Category", CATEGORY_DISPLAY.get(top, top)[:25])
        else:
            st.metric("📂 Top Category", "—")

# ── Error from last run ──────────────────────────────────────────────

if st.session_state.error and st.session_state.pipeline_state == "idle":
    st.error(f"**⚠ SYSTEM ERROR:** {st.session_state.error}")
