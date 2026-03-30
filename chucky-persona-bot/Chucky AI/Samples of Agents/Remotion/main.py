"""
Chucky AI — Crew Orchestrator
Department of the Unknown

Runs the full 8-agent sequential pipeline:
  Agent 1 (Archival Brainstormer)
    → Agent 2 (Atmosphere Architect)
      → Agent 3 (Casting Director)
        → Agent 4 (Pacing Outliner)
          → Agent 5 (Screenwriter)
            → Agent 6 (Showrunner)
              → Agent 7 (Prompt Translator)
                → Agent 8 (SEO & Social Media Manager)

Each agent's output flows as context into the next, producing a complete
horror concept → environment → characters → outline → script → final cut
→ production-ready generation prompts for Fal.ai and ElevenLabs
→ platform-optimized SEO metadata for YouTube, TikTok, and Instagram.
"""

import json
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths  (resolve before any relative imports)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "agents" / "output"
SCRIPT_DATA_DIR = PROJECT_ROOT / "video_engine" / "public"
HISTORY_PATH = PROJECT_ROOT / "agents" / "generation_history.json"

# Ensure the agents package is importable
sys.path.insert(0, str(PROJECT_ROOT / "agents"))

# ---------------------------------------------------------------------------
# Imports from agent modules
# ---------------------------------------------------------------------------
from agent_1_brainstormer import (
    BrainstormerOutput,
    BRAINSTORMER_BACKSTORY,
    ingest_documents,
    query_knowledge_base,
)
from agent_2_atmosphere import (
    AtmosphereOutput,
    create_atmosphere_agent,
    create_atmosphere_task,
    ingest_atmosphere_documents,
    query_atmosphere_knowledge_base,
)
from agent_3_casting import (
    CastingOutput,
    create_casting_agent,
    create_casting_task,
)
from agent_4_outliner import (
    OutlinerOutput,
    create_outliner_agent,
    create_outliner_task,
    ingest_pacing_documents,
    query_pacing_knowledge_base,
)
from agent_5_screenwriter import (
    ScreenwriterOutput,
    create_screenwriter_agent,
    create_screenwriter_task,
)
from agent_6_showrunner import (
    ShowrunnerOutput,
    create_showrunner_agent,
    create_showrunner_task,
    ingest_cliche_documents,
    query_cliche_knowledge_base,
)
from agent_7_translator import (
    TranslatorOutput,
    create_translator_agent,
    create_translator_task,
)
from agent_8_seo import (
    SEOOutput,
    create_seo_agent,
    create_seo_task,
    ingest_seo_documents,
    query_seo_knowledge_base,
)


# ============================================================
# Persistent Generation History
# ============================================================

def load_generation_history() -> list[dict]:
    """
    Load the generation history from agents/generation_history.json.
    Returns a list of dicts with 'title', 'logline', and 'date' keys.
    Creates the file with an empty array if it does not exist.
    """
    if not HISTORY_PATH.exists():
        HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        HISTORY_PATH.write_text("[]", encoding="utf-8")
        return []
    try:
        data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        return []
    except (json.JSONDecodeError, OSError):
        return []


def save_to_generation_history(title: str, logline: str) -> None:
    """
    Append a new entry to agents/generation_history.json.
    Each entry stores the title, logline, and date of generation.
    """
    history = load_generation_history()
    history.append({
        "title": title,
        "logline": logline,
        "date": date.today().isoformat(),
    })
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(
        json.dumps(history, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"[HISTORY] Saved to generation history: \"{title}\"")


# ============================================================
# Pipeline
# ============================================================

def run_pipeline() -> dict:
    """
    Build and execute the full 8-agent sequential crew.
    Agent 1 autonomously invents today's concept — no human theme needed.
    Returns the combined output from all eight agents as a dict.
    """
    from crewai import Agent, Crew, Process, Task
    from crewai.tools import tool
    from langchain_anthropic import ChatAnthropic

    # ==================================================================
    # Step 1 — Ingest RAG documents
    # ==================================================================
    import time as _time
    print("\n--- RAG Ingestion ---")
    _rag_fns = [
        ingest_documents,
        ingest_atmosphere_documents,
        ingest_pacing_documents,
        ingest_cliche_documents,
        ingest_seo_documents,
    ]
    for _i, _fn in enumerate(_rag_fns):
        _t0 = _time.time()
        _fn()
        _elapsed = _time.time() - _t0
        # If ingestion took >3s embedding likely occurred — cool down
        # before the next agent to avoid cross-agent quota exhaustion
        if _elapsed > 3 and _i < len(_rag_fns) - 1:
            print("[RAG] Cross-agent cooldown — waiting 65s...")
            _time.sleep(65)

    # ==================================================================
    # Step 1b — Load generation history for dedup
    # ==================================================================
    used_history = load_generation_history()
    if used_history:
        history_lines = []
        for entry in used_history:
            t = entry.get("title", "Unknown")
            l = entry.get("logline", "")
            d = entry.get("date", "")
            history_lines.append(f"- \"{t}\" ({d}): {l}")
        used_themes_str = "\n".join(history_lines)
        print(f"[HISTORY] {len(used_history)} previous generation(s) loaded.")
    else:
        used_themes_str = "(none — this is the first generation)"
        print("[HISTORY] No previous generations found. First run.")

    # ==================================================================
    # Step 2 — Build Agent 1:  The Archival Brainstormer
    # ==================================================================
    @tool
    def search_horror_archives(query: str) -> str:
        """Search the horror research archive for inspiration, reference material,
        liminal space concepts, environmental rules, and cosmic dread examples.
        Use this before generating ideas to ground your concepts in researched material."""
        return query_knowledge_base(query)

    llm = ChatAnthropic(
        model="claude-sonnet-4-20250514",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        temperature=0.9,
        max_tokens=4096,
    )

    brainstormer_agent = Agent(
        role="Horror Concept Architect",
        goal=(
            "Research the horror archives thoroughly using at least 5 diverse searches, "
            "then autonomously generate 3 unique, viral-worthy 60-90 second horror short "
            "concepts for a faceless TikTok/YouTube Shorts/Reels channel. Each concept must "
            "have a frame-level-precise 2-second scroll-stopping hook and be designed as a "
            "seamless visual loop where the final frame flows back into the opening. Every "
            "concept must be grounded in specific architectural, psychological, or perceptual "
            "research — not generic horror tropes. You must NEVER repeat or closely resemble "
            "any previously generated concept."
        ),
        backstory=BRAINSTORMER_BACKSTORY,
        llm=llm,
        tools=[search_horror_archives],
        max_iter=10,
        verbose=True,
    )

    brainstorm_task = Task(
        description=f"""\
You are the first agent in the Department of the Unknown production pipeline. \
The concepts you generate will be handed to the Atmosphere Architect, \
Casting Director, Pacing Outliner, Screenwriter, Showrunner, Visual Translator, \
and SEO Optimizer. Your output is the seed that determines the quality of the \
entire video. Make it worthy of that chain.

You are operating in AUTONOMOUS MODE — no human provides a theme. You must \
research, synthesize, and invent today's horror concepts entirely on your own.

<previously_generated_concepts>
{used_themes_str}
</previously_generated_concepts>

You are STRICTLY FORBIDDEN from reusing any theme, title, environment, anomaly, \
or closely similar concept from the list above. Every new generation must be \
meaningfully distinct in setting, mechanism, and hook.

## Step 1: Research (MANDATORY — do not skip)

Use the `search_horror_archives` tool to mine the research archive BEFORE \
writing a single concept. You must run AT LEAST 5 searches with diverse, \
specific queries. The archive contains expert-level research on liminal space \
architecture, cosmic dread mechanisms, and environmental horror rules. \
Your queries should be precise and varied:

1. A specific architectural query: \
`parking garage identical levels sodium vapor lighting spatial disorientation`
2. A psychological mechanism query: \
`pattern recognition failure cognitive map breakdown repetitive geometry`
3. An environmental rules query: \
`behavioral constraints implied consequence mundane setting horror`
4. A reality-glitch query: \
`temporal anomaly timestamp desynchronization clock wrong time`
5. A production-specific query: \
`scroll-stopping visual hook 2-second opening short-form video`
6. (Optional) Any unexpected angle that sparks a novel idea

Read each result carefully. Extract specific details you can recombine into \
something the archive has never seen assembled this way.

## Step 2: Synthesize (REQUIRED — reason before generating)

Before writing any concepts, reason through your research in your internal \
thinking. Ask yourself:
- What specific architectural detail from my research can I subvert or combine \
with another domain?
- What psychological mechanism have I NOT yet exploited?
- What environmental rule pattern could I place in a setting that has never \
been paired with it?
- What visual element will stop a scroll in under 1.3 seconds?
- How does the final frame loop seamlessly back to the opening?

Do NOT copy research verbatim. Use it as raw material — recombine, mutate, \
and collide concepts from different domains to create something that has never \
existed before.

## Step 3: Generate 3 Concepts

Create exactly **3** horror concepts. Each must be meaningfully distinct — \
different environments, different anomaly types, different hook mechanisms. \
No two concepts may share the same liminal space type or dread category.

For each concept, provide these four fields with the precision described below:

**`title`** — 3 to 7 words. Evocative and specific. The title must imply the \
wrongness without explaining it. It should make a viewer curious enough to stop \
scrolling. FORBIDDEN: generic titles like "The Dark Room", "Something Wrong", \
"The Last Floor", or any title that could describe a hundred different horror videos.

**`hook_visual`** — The EXACT first 2 seconds the viewer sees. Write this with \
frame-level precision: camera angle (POV, wide, close-up, low-angle), the \
specific environment (name the space, its materials, its lighting color temperature), \
and the ONE element that is visibly wrong. This must be producible with AI image \
generation (Flux Pro). Do not describe motion — describe a single, frozen moment \
of wrongness.

**`hook_audio`** — The EXACT first 2 seconds the viewer hears, paired with the \
visual hook. Name the specific sound: its source, its quality (frequency, texture, \
volume), and what is WRONG about it. FORBIDDEN: "an eerie sound", "a mysterious \
noise", "unsettling ambience", or any non-specific audio descriptor.

**`logline`** — Exactly 2 sentences. No more, no fewer.
- Sentence 1: The environment + the protagonist's constrained behavior + the rule \
or anomaly that governs it.
- Sentence 2: The escalation + the seamless loop mechanism (how the final moment \
flows back to the opening hook without a visible cut).

<example_output>
This is an example of the CALIBER of output expected. Do NOT copy this concept — \
use it only to understand the level of specificity and craft required.

{{
  "concepts": [
    {{
      "title": "The Sixty-First Second",
      "hook_visual": "Close-up of a digital wall clock in a fluorescent-lit office \
break room, white plastic housing, blue LED display reading 11:59:60 — the colon \
blinks normally but the seconds digit shows 60 instead of resetting to 00.",
      "hook_audio": "The sharp, mechanical click of the clock's internal relay \
advancing — but the click repeats twice in rapid succession, like a skipped heartbeat, \
then silence where the ambient HVAC hum should be.",
      "logline": "A night-shift security guard notices the break room clock displays \
a 61st second and is trained to sit motionless facing the clock until the minute \
advances — if he looks away during the extra second, the room dimensions change. \
The clock resets to 11:59:00,  and the guard exhales and reaches for his coffee — \
but the display begins counting toward 60 again as the camera pulls back to reveal \
the break room walls are now 3 feet closer than they were."
    }}
  ]
}}
</example_output>

Notice the specificity: exact lighting, exact material, exact numerical anomaly, \
exact sound source, exact behavioral rule, exact loop mechanism. This is the bar.

## Absolute Constraints

- FACELESS — no visible human faces, no identifiable actors
- Producible with AI image generation (Flux Pro) + TTS narration (ElevenLabs) only
- All 3 concepts fully distinct — no shared environment type, no shared anomaly class
- Every logline Sentence 2 MUST describe the seamless loop closure
- FORBIDDEN settings: abandoned asylums, dark forests, graveyards, Victorian mansions, \
gothic architecture, candlelit rooms, fog-shrouded moors
- FORBIDDEN entities: zombies, glowing red eyes, demons, supernatural creatures
- FORBIDDEN mechanisms: jump scares as primary horror, gore as lead mechanism
- FORBIDDEN language: "delve", "shivers down the spine", "what lurks in the shadows", \
"a sense of unease", "eerie silence", "creepy", "spooky", "haunted", "something is watching"

## Output Format

Return ONLY a valid JSON object. No preamble, no explanation, no markdown fences. \
The JSON must parse cleanly.

{{
  "concepts": [
    {{"title": "...", "hook_visual": "...", "hook_audio": "...", "logline": "..."}},
    {{"title": "...", "hook_visual": "...", "hook_audio": "...", "logline": "..."}},
    {{"title": "...", "hook_visual": "...", "hook_audio": "...", "logline": "..."}}
  ]
}}""",
        expected_output=(
            "A JSON object with a 'concepts' array containing exactly 3 horror "
            "concept objects, each with 'title', 'hook_visual', 'hook_audio', and "
            "'logline' string fields. Every field must demonstrate frame-level "
            "specificity grounded in researched material."
        ),
        agent=brainstormer_agent,
        output_json=BrainstormerOutput,
    )

    # ==================================================================
    # Step 3 — Build Agent 2:  The Atmosphere Architect
    # ==================================================================
    @tool
    def search_obscure_lore(query: str) -> str:
        """Search the obscure lore database for liminal space aesthetics, SCP-style
        environmental rules, and cognitohazard patterns. Use this before designing
        the environment to ground your choices in researched lore."""
        return query_atmosphere_knowledge_base(query)

    atmosphere_agent = create_atmosphere_agent(tools=[search_obscure_lore])
    atmosphere_task = create_atmosphere_task(
        agent=atmosphere_agent,
        context_tasks=[brainstorm_task],  # receives Agent 1 output
    )

    # ==================================================================
    # Step 4 — Build Agent 3:  The Creature & Casting Director
    # ==================================================================
    casting_agent = create_casting_agent()
    casting_task = create_casting_task(
        agent=casting_agent,
        context_tasks=[brainstorm_task, atmosphere_task],  # receives both
    )

    # ==================================================================
    # Step 5 — Build Agent 4:  The Pacing Outliner
    # ==================================================================
    @tool
    def search_pacing_archives(query: str) -> str:
        """Search the viral pacing database for viewer retention data, hook psychology,
        mathematical pacing benchmarks, and loop mechanics case studies. Use this
        before structuring the production outline to calibrate block durations."""
        return query_pacing_knowledge_base(query)

    outliner_agent = create_outliner_agent(tools=[search_pacing_archives])
    outliner_task = create_outliner_task(
        agent=outliner_agent,
        context_tasks=[brainstorm_task, atmosphere_task, casting_task],
    )

    # ==================================================================
    # Step 6 — Build Agent 5:  The Screenwriter
    # ==================================================================
    screenwriter_agent = create_screenwriter_agent()
    screenwriter_task = create_screenwriter_task(
        agent=screenwriter_agent,
        context_tasks=[outliner_task],  # primarily needs the timed outline
    )

    # ==================================================================
    # Step 7 — Build Agent 6:  The Showrunner
    # ==================================================================
    @tool
    def search_cliche_archives(query: str) -> str:
        """Search the AI cliché blacklist for overused horror tropes, banned phrases,
        and corrective alternatives. Use this before the cliché purge pass to build
        a comprehensive mental blacklist of patterns to eliminate."""
        return query_cliche_knowledge_base(query)

    showrunner_agent = create_showrunner_agent(tools=[search_cliche_archives])
    showrunner_task = create_showrunner_task(
        agent=showrunner_agent,
        context_tasks=[outliner_task, screenwriter_task],
    )

    # ==================================================================
    # Step 8 — Build Agent 7:  The Prompt Translator
    # ==================================================================
    translator_agent = create_translator_agent()
    translator_task = create_translator_task(
        agent=translator_agent,
        context_tasks=[showrunner_task],
    )

    # ==================================================================
    # Step 9 — Build Agent 8:  The SEO & Social Media Manager
    # ==================================================================
    @tool
    def search_seo_knowledge_base(query: str) -> str:
        """Search the SEO & social media knowledge base for platform-specific
        algorithmic intelligence, hashtag taxonomies, CTA frameworks, and
        community tab strategies. Use this BEFORE generating any metadata."""
        return query_seo_knowledge_base(query)

    seo_agent = create_seo_agent(tools=[search_seo_knowledge_base])
    seo_task = create_seo_task(
        agent=seo_agent,
        context_tasks=[brainstorm_task, atmosphere_task, translator_task],
    )

    # ==================================================================
    # Step 10 — Assemble & run the Crew
    # ==================================================================
    print("\n--- Assembling Crew ---")
    print(f"  Agent 1: {brainstormer_agent.role}")
    print(f"  Agent 2: {atmosphere_agent.role}")
    print(f"  Agent 3: {casting_agent.role}")
    print(f"  Agent 4: {outliner_agent.role}")
    print(f"  Agent 5: {screenwriter_agent.role}")
    print(f"  Agent 6: {showrunner_agent.role}")
    print(f"  Agent 7: {translator_agent.role}")
    print(f"  Agent 8: {seo_agent.role}")
    print(f"  Process: Sequential")
    print(f"  Mode:    Autonomous\n")

    crew = Crew(
        agents=[
            brainstormer_agent,
            atmosphere_agent,
            casting_agent,
            outliner_agent,
            screenwriter_agent,
            showrunner_agent,
            translator_agent,
            seo_agent,
        ],
        tasks=[
            brainstorm_task,
            atmosphere_task,
            casting_task,
            outliner_task,
            screenwriter_task,
            showrunner_task,
            translator_task,
            seo_task,
        ],
        process=Process.sequential,
        verbose=True,
    )

    crew.kickoff()

    # ==================================================================
    # Step 11 — Collect outputs from every task
    # ==================================================================
    combined_output: dict = {}

    for label, task_obj, schema in [
        ("brainstorm", brainstorm_task, BrainstormerOutput),
        ("atmosphere", atmosphere_task, AtmosphereOutput),
        ("casting", casting_task, CastingOutput),
        ("outline", outliner_task, OutlinerOutput),
        ("screenplay_v1", screenwriter_task, ScreenwriterOutput),
        ("final_script", showrunner_task, ShowrunnerOutput),
        ("generation_prompts", translator_task, TranslatorOutput),
        ("seo_metadata", seo_task, SEOOutput),
    ]:
        try:
            raw = (
                task_obj.output.json_dict
                if hasattr(task_obj.output, "json_dict")
                else None
            )
            if raw is None:
                raw_text = str(task_obj.output)
                start = raw_text.find("{")
                end = raw_text.rfind("}") + 1
                if start != -1 and end > start:
                    raw = json.loads(raw_text[start:end])
                else:
                    raw = {"raw_output": raw_text}

            # Validate against the Pydantic schema
            try:
                validated = schema(**raw)
                combined_output[label] = validated.model_dump()
            except Exception:
                combined_output[label] = raw
        except Exception as exc:
            combined_output[label] = {"error": str(exc)}

    return combined_output


# ============================================================
# Pretty-print helpers
# ============================================================

def _print_brainstorm(data: dict) -> None:
    print("\n┌─── AGENT 1: ARCHIVAL BRAINSTORMER ───┐")
    concepts = data.get("concepts", [data])
    for i, c in enumerate(concepts, 1):
        if isinstance(c, dict):
            print(f"\n  Concept {i}: {c.get('title', 'N/A')}")
            print(f"  Hook [VISUAL]: {c.get('hook_visual', 'N/A')}")
            print(f"  Hook [AUDIO]:  {c.get('hook_audio', 'N/A')}")
            print(f"  Logline:       {c.get('logline', 'N/A')}")
    print("\n└──────────────────────────────────────┘")


def _print_atmosphere(data: dict) -> None:
    print("\n┌─── AGENT 2: ATMOSPHERE ARCHITECT ─────┐")
    print(f"\n  Location:\n    {data.get('location', 'N/A')}")
    print(f"\n  Environmental Rule:\n    {data.get('environmental_rule', 'N/A')}")
    print(f"\n  Soundscape:\n    {data.get('soundscape', 'N/A')}")
    print("\n└───────────────────────────────────────┘")


def _print_casting(data: dict) -> None:
    print("\n┌─── AGENT 3: CREATURE & CASTING DIRECTOR ┐")
    protag = data.get("protagonist_profile", {})
    anomaly = data.get("anomaly_profile", {})
    print(f"\n  PROTAGONIST")
    print(f"    Archetype:     {protag.get('archetype', 'N/A')}")
    print(f"    Vulnerability: {protag.get('vulnerability', 'N/A')}")
    print(f"    Physicality:   {protag.get('physicality', 'N/A')}")
    print(f"\n  ANOMALY")
    print(f"    Designation:      {anomaly.get('designation', 'N/A')}")
    print(f"    Manifestation:    {anomaly.get('manifestation', 'N/A')}")
    print(f"    Behavior Pattern: {anomaly.get('behavior_pattern', 'N/A')}")
    print(f"    Cognitive Effect: {anomaly.get('cognitive_effect', 'N/A')}")
    print("\n└──────────────────────────────────────────┘")


def _print_outline(data: dict) -> None:
    print("\n┌─── AGENT 4: PACING OUTLINER ──────────┐")
    print(f"\n  Title:    {data.get('title', 'N/A')}")
    print(f"  Duration: {data.get('total_duration', 'N/A')}")
    blocks = data.get("pacing_blocks", [])
    for block in blocks:
        if isinstance(block, dict):
            print(f"\n  [{block.get('timecode', '?')}] {block.get('label', '?')}")
            print(f"    VISUAL: {block.get('visual_direction', 'N/A')[:120]}...")
            print(f"    AUDIO:  {block.get('audio_direction', 'N/A')[:120]}...")
            print(f"    PACING: {block.get('pacing_notes', 'N/A')[:120]}...")
    print(f"\n  Loop Mechanism:\n    {data.get('loop_mechanism', 'N/A')[:200]}...")
    print("\n└───────────────────────────────────────┘")


def _print_screenplay(data: dict) -> None:
    print("\n┌─── AGENT 5: SCREENWRITER (V1) ────────┐")
    print(f"\n  Title:   {data.get('title', 'N/A')}")
    print(f"  Version: {data.get('version', 'N/A')}")
    blocks = data.get("script_blocks", [])
    for block in blocks:
        if isinstance(block, dict):
            print(f"\n  [{block.get('timecode', '?')}] {block.get('label', '?')}")
            print(f"    [VISUAL]:    {block.get('visual', 'N/A')[:140]}...")
            print(f"    [AUDIO]:     {block.get('audio', 'N/A')[:140]}...")
            narr = block.get("narration", "")
            if narr:
                print(f"    [NARRATION]: {narr[:140]}...")
    print("\n└───────────────────────────────────────┘")


def _print_final_script(data: dict) -> None:
    print("\n┌══════════════════════════════════════════┐")
    print("│   AGENT 6: SHOWRUNNER — FINAL SCRIPT     │")
    print("├══════════════════════════════════════════┤")
    print(f"\n  Title:   {data.get('title', 'N/A')}")
    print(f"  Version: {data.get('version', 'N/A')}")
    blocks = data.get("script_blocks", [])
    for block in blocks:
        if isinstance(block, dict):
            print(f"\n  ── [{block.get('timecode', '?')}] {block.get('label', '?')} ──")
            print(f"    [VISUAL]:")
            print(f"      {block.get('visual', 'N/A')}")
            print(f"    [AUDIO]:")
            print(f"      {block.get('audio', 'N/A')}")
            narr = block.get("narration", "")
            if narr:
                print(f"    [NARRATION]:")
                print(f"      {narr}")
    print(f"\n  LOOP TRANSITION:")
    print(f"    {data.get('loop_transition_script', 'N/A')}")
    print(f"\n  SHOWRUNNER NOTES:")
    print(f"    {data.get('showrunner_notes', 'N/A')}")
    print("\n╘══════════════════════════════════════════╛")


def _print_generation_prompts(data: dict) -> None:
    print("\n┌─── AGENT 7: PROMPT TRANSLATOR ────────┐")
    print(f"\n  Title: {data.get('title', 'N/A')}")
    scenes = data.get("scene_prompts", [])
    for s in scenes:
        if isinstance(s, dict):
            print(f"\n  [{s.get('scene_id', '?')}] ({s.get('duration_estimate_seconds', '?')}s)")
            print(f"    FLUX:  {s.get('flux_image_prompt', 'N/A')[:160]}...")
            tts = s.get("elevenlabs_tts_text", "")
            if tts:
                print(f"    TTS:   {tts[:120]}...")
            else:
                print(f"    TTS:   (none)")
    print("\n└───────────────────────────────────────┘")


def _print_seo_metadata(data: dict) -> None:
    print("\n┌─── AGENT 8: SEO & SOCIAL MEDIA ───────┐")

    tt = data.get("tiktok_metadata", {})
    print(f"\n  TIKTOK")
    print(f"    Caption:   {tt.get('video_caption', 'N/A')}")

    yt = data.get("youtube_metadata", {})
    print(f"\n  YOUTUBE")
    print(f"    Caption:   {yt.get('shorts_caption', 'N/A')}")
    print(f"    Thumb:     {yt.get('thumbnail_text', 'N/A')}")
    tags = yt.get("tags", [])
    print(f"    Tags ({len(tags)}): {', '.join(tags[:8])}{'...' if len(tags) > 8 else ''}")
    print(f"    Community: {yt.get('community_post', 'N/A')[:120]}{'...' if len(yt.get('community_post', '')) > 120 else ''}")

    ig = data.get("instagram_metadata", {})
    print(f"\n  INSTAGRAM")
    print(f"    Caption:   {ig.get('reels_caption', 'N/A')[:150]}{'...' if len(ig.get('reels_caption', '')) > 150 else ''}")
    print(f"    Alt text:  {ig.get('alt_text', 'N/A')}")

    fb = data.get("facebook_metadata", {})
    print(f"\n  FACEBOOK")
    print(f"    Caption:   {fb.get('reels_caption', 'N/A')[:150]}{'...' if len(fb.get('reels_caption', '')) > 150 else ''}")
    print(f"    Feed post: {fb.get('feed_post', 'N/A')[:120]}{'...' if len(fb.get('feed_post', '')) > 120 else ''}")

    xt = data.get("x_twitter_metadata", {})
    print(f"\n  X / TWITTER")
    print(f"    Tweet:     {xt.get('main_tweet', 'N/A')}")
    print(f"    Follow-up: {xt.get('follow_up_tweet', 'N/A')}")

    print("\n└───────────────────────────────────────┘")


# ============================================================
# File export for Remotion
# ============================================================

def save_script_data(combined_output: dict) -> tuple[Path, Path | None]:
    """
    Extract the generation_prompts and seo_metadata from pipeline output.
    Saves script_data.json for Remotion and seo_metadata.json for publishing.
    Returns (script_data_path, seo_metadata_path).
    """
    SCRIPT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    prompts_data = combined_output.get("generation_prompts", {})
    script_data_path = SCRIPT_DATA_DIR / "script_data.json"
    script_data_path.write_text(
        json.dumps(prompts_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    seo_metadata_path = None
    seo_data = combined_output.get("seo_metadata")
    if seo_data:
        seo_metadata_path = OUTPUT_DIR / "seo_metadata.json"
        seo_metadata_path.write_text(
            json.dumps(seo_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    return script_data_path, seo_metadata_path


# ============================================================
# Entry point
# ============================================================

def main():
    load_dotenv(PROJECT_ROOT / ".env")

    print("=" * 64)
    print("  Chucky AI — Department of the Unknown")
    print("  Full Pipeline: Brainstorm → Atmosphere → Casting")
    print("                 → Outline → Script → Final Cut")
    print("                 → Prompt Translation → SEO Metadata")
    print("=" * 64)
    print("\n  Mode: Autonomous (zero-click)\n")

    # Validate API key
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or api_key.startswith("your-"):
        print("[ERROR] ANTHROPIC_API_KEY is not set. Update your .env file.")
        sys.exit(1)

    # Run the full pipeline (no theme — Agent 1 self-generates)
    combined = run_pipeline()

    # Save combined output
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / "full_concept_output.json"
    output_path.write_text(
        json.dumps(combined, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\n[SAVED] Full output → {output_path}")

    # Save script_data.json for Remotion + seo_metadata.json for publishing
    script_path, seo_path = save_script_data(combined)
    print(f"\n✅ Script generated and saved to {script_path}")
    if seo_path:
        print(f"✅ SEO metadata saved to {seo_path}")

    # Append to persistent generation history
    gen_title = None
    gen_logline = ""
    gen_prompts = combined.get("generation_prompts", {})
    if isinstance(gen_prompts, dict) and gen_prompts.get("title"):
        gen_title = gen_prompts["title"]
    if not gen_title:
        brainstorm = combined.get("brainstorm", {})
        concepts = brainstorm.get("concepts", [])
        if concepts and isinstance(concepts[0], dict):
            gen_title = concepts[0].get("title", "Untitled")
            gen_logline = concepts[0].get("logline", "")
    if not gen_logline:
        brainstorm = combined.get("brainstorm", {})
        concepts = brainstorm.get("concepts", [])
        if concepts and isinstance(concepts[0], dict):
            gen_logline = concepts[0].get("logline", "")
    if gen_title:
        save_to_generation_history(gen_title, gen_logline)

    # Pretty-print all agents
    print("\n" + "=" * 64)
    print("  COMPLETE HORROR PRODUCTION PACKAGE")
    print("=" * 64)

    if "brainstorm" in combined:
        _print_brainstorm(combined["brainstorm"])
    if "atmosphere" in combined:
        _print_atmosphere(combined["atmosphere"])
    if "casting" in combined:
        _print_casting(combined["casting"])
    if "outline" in combined:
        _print_outline(combined["outline"])
    if "screenplay_v1" in combined:
        _print_screenplay(combined["screenplay_v1"])
    if "final_script" in combined:
        _print_final_script(combined["final_script"])
    if "generation_prompts" in combined:
        _print_generation_prompts(combined["generation_prompts"])
    if "seo_metadata" in combined:
        _print_seo_metadata(combined["seo_metadata"])

    print("\n" + "=" * 64)
    print("  Pipeline complete. 8 agents. 1 Chucky.")
    print("=" * 64)


if __name__ == "__main__":
    main()
