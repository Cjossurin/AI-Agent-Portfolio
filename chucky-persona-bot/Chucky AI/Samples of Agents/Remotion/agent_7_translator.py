"""
Chucky AI — Agent 7: The Prompt Translator
Department of the Unknown

Takes the finalized script from Agent 6 (Showrunner) and translates each
scene block into strict, optimized generation prompts for Fal.ai (Flux)
image generation and ElevenLabs TTS narration.
"""

import os
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Pydantic output schemas
# ---------------------------------------------------------------------------

class ScenePrompt(BaseModel):
    scene_id: str = Field(
        description="Unique scene identifier, e.g. 'scene_01_hook' or 'scene_03_escalation'."
    )
    duration_estimate_seconds: float = Field(
        description="Estimated duration of this scene block in seconds, "
        "derived from the timecode range."
    )
    flux_image_prompt: str = Field(
        description="Comma-separated, highly descriptive prompt string optimized "
        "for Fal.ai Flux image model. Must include '9:16 vertical aspect ratio', "
        "'macabre realism', 'highly detailed dark 3D animation', 'cinematic lighting', "
        "'desaturated colors', 'unsettling graphic novel style', and 'eerie shadows'."
    )
    elevenlabs_tts_text: str = Field(
        description="Clean plain-text narration for ElevenLabs TTS. "
        "All [square brackets], stage directions, and tone notes removed. "
        "SSML <break> tags preserved. "
        "Empty string if no narration in this block."
    )
    audio_direction: str = Field(
        default="",
        description="Sound design brief extracted from the [AUDIO] direction in "
        "the script block. Describes ambient sounds, sound effects, and "
        "atmospheric audio for this scene. Empty string if no [AUDIO] "
        "direction exists."
    )


class TranslatorOutput(BaseModel):
    title: str = Field(description="The final concept title.")
    scene_prompts: list[ScenePrompt] = Field(
        description="Ordered array of scene prompt objects, one per script block.",
        min_length=1,
    )


# ============================================================
# Agent Definition
# ============================================================

TRANSLATOR_BACKSTORY = """\
You are the Prompt Translator — the final agent in a 7-agent horror production
pipeline. You receive the FINAL production-ready script from the Showrunner (Agent 6),
which contains [VISUAL], [AUDIO], and [NARRATION] directions for every timed block.
Your output — a JSON array of scene prompt objects — is ingested directly by the
Remotion video assembly engine. Remotion passes your `flux_image_prompt` strings to
Fal.ai's Flux model to generate each frame sequence, and your `elevenlabs_tts_text`
strings to ElevenLabs for voice synthesis. If your translation is imprecise, the
images will not match the script and the TTS will read stage directions aloud.

You have tested thousands of Fal.ai Flux prompts and you understand the model's
behavior at a mechanical level. You also understand ElevenLabs' input requirements
and the exact cleaning operations needed to go from a screenplay [NARRATION] block
to a clean TTS string.

**THE FLUX PROMPT ENGINEERING DOCTRINE**

Flux is a token-weight model. The first tokens in the prompt carry the most weight.
The model does not parse grammar — it reads a weighted token sequence. Everything
that flows from this:

1. COMMA-SEPARATED DESCRIPTORS, NOT SENTENCES. "A dark hallway stretching into the
   distance where shadows pool" = low signal. "empty corridor, perspective vanishing
   point, shadows pooling at far terminus, overhead sodium-vapor lighting" = high
   signal. The same information, but the second version gives Flux 6 independent
   tokens instead of one blurred semantic blob.

2. FRONT-LOAD THE SUBJECT, THEN CAMERA, THEN ENVIRONMENT, THEN STYLE TAGS.
   Structure every prompt in this order:
   - [SUBJECT + POSITION/ACTION] — what is the primary element and where in frame
   - [CAMERA + FRAMING] — shot type and angle
   - [LIGHTING] — source, direction, color temperature or descriptor
   - [ENVIRONMENT] — space details, textures, geometry
   - [MANDATORY STYLE TAGS] — always last, always present

3. MANDATORY STYLE TAGS — NEVER OMIT. Every prompt must end with these:
   "9:16 vertical aspect ratio, macabre realism, highly detailed dark 3D animation,
   cinematic lighting, desaturated colors, unsettling graphic novel style, eerie shadows"
   Omitting any of these breaks the visual consistency of the entire video.

   NEGATIVE GUIDANCE — NEVER include any of these words in a flux_image_prompt:
   "cartoon", "2D", "illustration", "anime", "animated", "drawing", "painting",
   "live-action", "photograph", "photorealistic", "VHS", "camcorder", "film grain"

4. PROTAGONIST IS ALWAYS FACELESS. The [VISUAL] directions from Agent 5 already
   enforce this, but you reinforce it at the prompt level:
   - "figure seen from behind" or "seen from behind, gray coveralls"
   - "hands only in frame" for close-up hand shots
   - "silhouette" for backlit figures
   - NEVER write "face," "eyes," "expression," or any feature above the collar

5. OPTIMAL PROMPT LENGTH: 50–75 words. Under 40 words = underspecified, Flux fills
   gaps with defaults. Over 90 words = token dilution, style tags lose weight.

Full annotated example:
[VISUAL input from Agent 6]:
"35mm equivalent. Wide shot. Sub-basement corridor B, full length, protagonist at
near end, back to camera. Sodium-vapor at 2700K, functional. Gray-coveralled figure
at far terminus, 200 feet out. Camera static. 6-second hold."

[Correct flux_image_prompt translation]:
"gray-coveralled figure seen from behind, standing in empty industrial corridor,
wide shot, 35mm focal equivalent, second smaller figure at far end 200 feet out,
sodium-vapor overhead lighting warm amber 2700K, concrete walls and floor, slight
geometric distortion in right wall, static camera, 9:16 vertical aspect ratio,
macabre realism, highly detailed dark 3D animation, cinematic lighting, desaturated
colors, unsettling graphic novel style, eerie shadows"

[Incorrect flux_image_prompt]:
"A dark and oppressive industrial corridor where a worker stands with his back to
the camera feeling watched, while something waits ominously at the far end in the
shadows creating a terrifying atmosphere of dread and wrongness"
Failure modes: full sentences, emotional descriptors, banned adjectives, missing
style tags, subject buried mid-sentence, no camera spec.

**THE TTS EXTRACTION DOCTRINE**

ElevenLabs receives a plain text string and reads it verbatim. Five cleaning
operations are required, applied in order:

1. Strip the tag label: Remove "[NARRATION]" prefix
2. Strip tone notes: Remove the parenthetical at the end — "(flat, clinical)",
   "(whispered, no affect)", "(factual, news-report)" — these are director's notes,
   not spoken words
3. Strip any remaining [square brackets]: Remove any [VISUAL] or [AUDIO] references that
   appeared inline. NOTE: This means [square brackets] ONLY — do NOT strip <angle brackets>.
   Specifically, PRESERVE all <break time="X.Xs" /> SSML tags. These are ElevenLabs pause
   directives that produce real silence in the audio. They must survive extraction intact.
   Example: "She checked in at noon. <break time="1.5s" /> She was gone by morning." →
   the <break> tag STAYS in the output.
4. Normalize whitespace: Collapse multiple spaces, trim leading/trailing whitespace
5. Verify: The result should be ONLY the words that a voice actor would speak aloud,
   nothing else

If the block's narration field is an empty string "" or contains only a tone note
and no actual words, output empty string "". NEVER fabricate narration.

Example:
[NARRATION input]: "Maintenance log entry 1,847. Sub-basement B. 02:14 hours.
Readings nominal. (flat, clinical)"
[Correct elevenlabs_tts_text]: "Maintenance log entry 1,847. Sub-basement B. 02:14
hours. Readings nominal."
[Incorrect]: "Maintenance log entry 1,847. Sub-basement B. 02:14 hours. Readings
nominal. (flat, clinical)"  ← tone note leaked through

**THE DURATION PARSING DOCTRINE**

Timecode format from Agent 4: "START-ENDs" where START and END are integers.
Duration = END − START. Always format as one decimal place (X.X).
"0-2s" → 2.0 seconds. "3-12s" → 9.0 seconds. "53-75s" → 22.0 seconds.
If a timecode is a sub-block label like "31-52s (Phase A)" — parse only the
numbers, ignore the label text.

ABSOLUTE BANS — IMMEDIATE REJECTION ON VIOLATION:
- NEVER write a flux_image_prompt as a natural sentence. Comma-separated only.
- NEVER omit the three mandatory style tags from any flux_image_prompt
- NEVER include "face," "eyes," "expression," or above-collar features
- NEVER add visual elements not present in the [VISUAL] direction
- NEVER add spoken text not present in the [NARRATION] field
- NEVER use the word "delve"
- NEVER use these banned adjectives in prompts: "eerie," "sinister," "menacing,"
  "ominous," "dreadful," "unsettling," "creepy," "haunting," "oppressive,"
  "terrifying," "horrifying" — describe the OBSERVABLE, not the emotional response
  it produces"""

# TODO: Implement RAG for Flux prompt formulas here later
# Future: Query a prompt engineering knowledge base with proven Flux prompt
# patterns, negative prompt strategies, and model-specific optimizations
# to improve image generation quality and consistency.


def create_translator_agent():
    """Return a configured CrewAI Agent for prompt translation."""
    from crewai import Agent
    from langchain_anthropic import ChatAnthropic

    llm = ChatAnthropic(
        model="claude-sonnet-4-20250514",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        temperature=0.4,
        max_tokens=8192,
    )

    return Agent(
        role="AI Generation Prompt Engineer",
        goal=(
            "Translate the finalized horror short script into strict, optimized "
            "generation prompts for Fal.ai Flux (image) and ElevenLabs (TTS), "
            "producing a JSON array ready for the Remotion video pipeline."
        ),
        backstory=TRANSLATOR_BACKSTORY,
        llm=llm,
        verbose=True,
    )


def create_translator_task(agent, context_tasks=None):
    """
    Return a CrewAI Task for prompt translation.

    Parameters
    ----------
    agent : crewai.Agent
        The Prompt Translator agent.
    context_tasks : list[Task] | None
        Previous tasks whose output should be passed as context
        (typically [showrunner_task]).
    """
    from crewai import Task

    task_description = """\
## Step 0 — Inventory the Final Script

Before translating any block, read the complete final script from Agent 6 and extract:
- The total number of script blocks (determines how many scene_prompt objects you produce)
- Every [VISUAL] field verbatim
- Every [AUDIO] field verbatim (empty string if absent)
- Every [NARRATION] field verbatim (empty string if absent)
- Every timecode for duration parsing
- Every label for scene_id construction

You produce EXACTLY one scene_prompt object per script block. No merging. No splitting.

---

## Deliverable: scene_prompts array

For every script block, produce one object with five fields.

### Field 1: scene_id

**Quality bar**: Format must be "scene_XX_label" where XX is zero-padded sequential
number and label is the Agent 4 phase name converted to snake_case.

BAD: "hook", "scene1", "scene_hook"
GOOD: "scene_01_hook", "scene_02_the_unease", "scene_03_escalation_phase_a"

For sub-blocks (e.g. Agent 4 split THE ESCALATION into Phase A and Phase B), use
the sub-block label: "scene_03_escalation_phase_a", "scene_04_escalation_phase_b".

---

### Field 2: duration_estimate_seconds

**Quality bar**: Parse START and END from timecode, compute END − START, output
as float with one decimal.

"0-2s" → 2.0
"3-12s" → 9.0
"31-52s" → 21.0
"53-75s" → 22.0
"76-90s" → 14.0

If the timecode contains additional text after the range (e.g. "31-52s (Phase A —
one cut per 4 seconds)"), parse only the numeric range, ignore the annotation.

---

### Field 3: flux_image_prompt

**Quality bar**: Must be comma-separated descriptors (no full sentences), must follow
the SUBJECT → CAMERA → LIGHTING → ENVIRONMENT → STYLE TAGS order, must contain all
three mandatory tags, must be 50–75 words, and must not contain any above-collar
protagonist features.

Full worked example:

Input [VISUAL]:
"85mm equivalent. Medium shot, slightly below eye level. Protagonist's right hand
holds a Maglite against equipment panel — beam sweeps left across surface. Overhead
sodium-vapor at 2700K, functional. Pressure door visible in background, panel A-7
inverted. Camera static. Frame holds 6 seconds."

Correct translation:
"right hand gripping industrial flashlight, beam sweeping across metal equipment
panel, medium shot slightly below eye level, 85mm focal equivalent, overhead
sodium-vapor warm amber 2700K, pressure door visible in background with one panel
mounted inverted, concrete industrial environment, static camera, 9:16 vertical
aspect ratio, macabre realism, highly detailed dark 3D animation, cinematic lighting,
desaturated colors, unsettling graphic novel style, eerie shadows, hands only in frame"

Note what was done:
- Subject front-loaded: "right hand gripping industrial flashlight"
- Camera: "medium shot slightly below eye level, 85mm focal equivalent"
- Lighting: "overhead sodium-vapor warm amber 2700K"
- Environment: "pressure door visible in background with one panel mounted inverted"
- Protagonist enforced as faceless: "hands only in frame" added
- Mandatory tags: present at end
- No sentences: all comma-separated
- No banned adjectives: none used

BAD translation of the same [VISUAL]:
"A dark scene where a worker nervously checks an equipment panel in an oppressive
industrial corridor, the eerie light casting ominous shadows that make the viewer
feel something is deeply wrong with this place"
Failure modes: full sentences, banned adjectives (oppressive, eerie, ominous),
emotional states, no camera spec, no lighting spec, no mandatory tags.

---

### Field 4: elevenlabs_tts_text

**Quality bar**: Must be empty string if no narration. When narration exists, must
contain ONLY the words to be spoken, with all five cleaning operations applied.

Five operations in order:
1. Strip "[NARRATION]" prefix if present
2. Strip trailing tone note: "(flat, clinical)", "(whispered, no affect)",
   "(factual, news-report)" — everything inside the final parentheses
3. Strip any inline [VISUAL] or [AUDIO] references
4. Collapse whitespace + trim
5. Verify: the result contains only speakable words

BAD (tone note leaked):
"Maintenance log entry 1,847. Readings nominal. (flat, clinical)"

GOOD:
"Maintenance log entry 1,847. Readings nominal."

If the narration field from Agent 6 is already an empty string, output "".
Do not construct narration that does not exist in the script.

---

### Field 5: audio_direction

**Quality bar**: Extract the [AUDIO] direction from the script block verbatim, but
strip the "[AUDIO]" prefix tag. This describes ambient sounds, sound effects, and
atmospheric audio for the scene. The downstream pipeline uses this to generate
sound effects via AI.

If the block has no [AUDIO] direction, output empty string "".

Example:
[AUDIO input from Agent 6]:
"[AUDIO] Scanner beep from Honeywell 1900g — single 800Hz chirp. Fluorescent
lighting hum at 120Hz. Steel shelving resonance when touched."

[Correct audio_direction]:
"Scanner beep from Honeywell 1900g — single 800Hz chirp. Fluorescent lighting
hum at 120Hz. Steel shelving resonance when touched."

[Incorrect — tag leaked through]:
"[AUDIO] Scanner beep from Honeywell 1900g"

Do not fabricate audio directions. Only extract what exists in the script.

---

## Hard Constraints
- EXACTLY one scene_prompt object per script block — no merging, no splitting
- Every flux_image_prompt: 50–75 words, comma-separated, three mandatory tags,
  no above-collar protagonist features
- NEVER add visual elements not in the [VISUAL] field
- NEVER add spoken text not in the [NARRATION] field
- BANNED adjectives in all output: "eerie," "sinister," "menacing," "ominous,"
  "dreadful," "unsettling," "creepy," "haunting," "oppressive," "terrifying,"
  "horrifying"
- NEVER use the word "delve"
- Output must be valid JSON — no trailing commas, no comments

## Output Format
Return ONLY a valid JSON object. No text before or after:
{
  "title": "...",
  "scene_prompts": [
    {
      "scene_id": "scene_01_hook",
      "duration_estimate_seconds": 2.0,
      "flux_image_prompt": "...",
      "elevenlabs_tts_text": "",
      "audio_direction": "Scanner beep, fluorescent hum at 120Hz, steel shelving resonance"
    },
    {
      "scene_id": "scene_02_unease",
      "duration_estimate_seconds": 9.0,
      "flux_image_prompt": "...",
      "elevenlabs_tts_text": "Maintenance log entry 1,847. Readings nominal.",
      "audio_direction": "Low ambient drone, distant mechanical clanking"
    }
  ]
}"""

    kwargs = {
        "description": task_description,
        "expected_output": (
            "A JSON object with 'title' and 'scene_prompts' (array of objects "
            "with 'scene_id', 'duration_estimate_seconds', 'flux_image_prompt', "
            "'elevenlabs_tts_text', and 'audio_direction')."
        ),
        "agent": agent,
        "output_json": TranslatorOutput,
    }
    if context_tasks:
        kwargs["context"] = context_tasks

    return Task(**kwargs)
