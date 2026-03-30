"""Chucky AI — Department of the Unknown

Main orchestrator for the automated horror-short video pipeline.
Chains Agent 1 (Anomaly Researcher) → Agent 2 (Narrative Scriptwriter)
→ Agent 3 (Visual & Technical Director) → Agent 4 (Media Integrator)
→ Agent 5 (SEO & Metadata) → Agent 6 (Remotion Composer)
→ Agent 7 (Video Publisher).
"""

import argparse
import json
import logging
import re
import sys
from pathlib import Path

from dotenv import load_dotenv


def _ensure_utf8_console() -> None:
    """Best-effort UTF-8 console output for Windows terminals.

    Some shells default to cp1252 and crash when printing box-drawing
    characters or emoji. Reconfigure streams when available.
    """
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        # Non-fatal: keep default encoding if reconfigure is unavailable.
        pass

# ── Bootstrap ─────────────────────────────────────────────────────────
_ensure_utf8_console()
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-28s | %(levelname)-7s | %(message)s",
)
logger = logging.getLogger("chucky-ai")

# ── Agent imports ─────────────────────────────────────────────────────
from agents.brainstormer import IdeaGenerator        # noqa: E402
from agents.researcher import AnomalyResearcher    # noqa: E402
from agents.writer import NarrativeScriptwriter     # noqa: E402
from agents.director import VisualTechnicalDirector  # noqa: E402
from agents.integrator import MediaIntegrator        # noqa: E402
from agents.image_dark_comic import DarkComicImageGenerator  # noqa: E402
from agents.image_vintage import VintageIllustrationImageGenerator  # noqa: E402
from agents.seo import SEOMetadataAgent              # noqa: E402
from agents.captioner import Captioner               # noqa: E402
from agents.composer import RemotionComposer         # noqa: E402
from agents.publisher import VideoPublisher          # noqa: E402


_case_counter_path = Path("assets/.case_counter")


def _next_case_number() -> int:
    """Read and increment a persistent case counter stored in assets/."""
    Path("assets").mkdir(parents=True, exist_ok=True)
    if _case_counter_path.is_file():
        n = int(_case_counter_path.read_text().strip())
    else:
        # Seed from the number of existing case_ folders
        n = len(list(Path("assets").glob("case_*")))
    n += 1
    _case_counter_path.write_text(str(n))
    return n


def _make_case_id(name: str) -> str:
    """Turn a case name into a numbered, filesystem-safe ID like '04_Devils_Footprints'."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    slug = "_".join(word.capitalize() for word in slug.split("_") if word)
    num = _next_case_number()
    return f"{num:02d}_{slug}"


# ── Phase name → number mapping (for --resume) ───────────────────────
PHASE_MAP = {
    "captions": 4.5,
    "seo": 5,
    "render": 6,
    "publish": 7,
}


def resume_pipeline(case_id: str, from_phase: float) -> None:
    """Resume the pipeline from a given phase using existing assets on disk."""
    asset_dir = Path("assets") / f"case_{case_id}"
    if not asset_dir.is_dir():
        print(f"\n❌ Asset directory not found: {asset_dir}")
        print("   Available cases:")
        for d in sorted(Path("assets").glob("case_*")):
            print(f"     - {d.name.removeprefix('case_')}")
        sys.exit(1)

    phase_names = {4.5: "Captions", 5: "SEO", 6: "Render", 7: "Publish"}
    print(f"\n🔄 Resuming pipeline for case '{case_id}' from Phase {phase_names.get(from_phase, from_phase)}")
    print(f"   Assets: {asset_dir}\n")

    # ── Load existing data from disk ──────────────────────────────────
    def _load_json(filename: str):
        p = asset_dir / filename
        if p.is_file():
            data = json.loads(p.read_text(encoding="utf-8"))
            logger.info("Loaded %s", p)
            return data
        return None

    metadata = _load_json("metadata.json")
    captions_data = _load_json("captions.json")
    props = _load_json("remotion_props.json")

    # Reconstruct a minimal media_manifest from remotion_props
    media_manifest = None
    if props:
        blocks = []
        for seq in props.get("sequences", []):
            block = {
                "block_id": seq["blockId"],
                "motion_type": seq["motionType"],
                "image_path": seq["imagePath"],
                "audio_path": seq["audioPath"],
            }
            if "videoPath" in seq:
                block["video_path"] = seq["videoPath"]
            blocks.append(block)
        media_manifest = {
            "case_id": case_id,
            "asset_dir": str(asset_dir),
            "blocks": blocks,
            "chosen_style": props.get("chosenStyle", "dark_comic"),
        }

    # ── Phase 4.5 — Captions ──────────────────────────────────────────
    if from_phase <= 4.5:
        if media_manifest is None:
            print("❌ Cannot regenerate captions — no remotion_props.json found.")
            sys.exit(1)
        captioner = Captioner()
        logger.info("Regenerating word-level captions...")
        captions_data = captioner.generate_captions(case_id, media_manifest)
        print("─── Captions Output ──────────────────────────────────────")
        print(json.dumps(captions_data, indent=2, ensure_ascii=False))
        print("───────────────────────────────────────────────────────────\n")

    # ── Phase 5 — SEO & Metadata ──────────────────────────────────────
    if from_phase <= 5:
        if metadata is None:
            print("⚠️  No metadata.json found — skipping SEO.")
        else:
            print("─── Metadata (from disk) ─────────────────────────────────")
            print(json.dumps(metadata, indent=2, ensure_ascii=False))
            print("───────────────────────────────────────────────────────────\n")

    # ── Phase 6 — Remotion Render ─────────────────────────────────────
    if from_phase <= 6:
        if media_manifest is None:
            print("❌ Cannot render — no remotion_props.json found.")
            sys.exit(1)
        composer = RemotionComposer()
        logger.info("Building Remotion props and rendering video...")
        props_path = composer.build_video(case_id, media_manifest, captions_data)
        print("─── Render Complete ──────────────────────────────────────")
        print(f"  Props:  {props_path}")
        print(f"  Video:  out/case_{case_id}_final.mp4")
        print("───────────────────────────────────────────────────────────\n")

    # ── Phase 7 — Publish ─────────────────────────────────────────────
    if from_phase <= 7:
        if metadata is None:
            print("❌ Cannot publish — no metadata.json found in assets.")
            sys.exit(1)

        # Auto-rename: find any rendered video and rename to canonical _final.mp4
        out_dir = Path("out")
        canonical = out_dir / f"case_{case_id}_final.mp4"
        if not canonical.is_file():
            candidates = sorted(out_dir.glob(f"case_{case_id}*.mp4"))
            if candidates:
                candidates[0].rename(canonical)
                logger.info("Renamed %s → %s", candidates[0].name, canonical.name)
            else:
                print(f"❌ No rendered video found in {out_dir} for case '{case_id}'.")
                sys.exit(1)

        # Skip approval gate when resuming directly to publish
        if from_phase < 7:
            print("╔══════════════════════════════════════════════════════════╗")
            print("║               REVIEW BEFORE PUBLISHING                  ║")
            print("╚══════════════════════════════════════════════════════════╝")
            print(f"  Video:  {canonical}")
            print(f"  Case:   {case_id}")
            if metadata:
                yt = metadata.get("youtube_metadata", {})
                if yt:
                    print(f"  Title:  {yt.get('title', 'N/A')}")
            print()
            try:
                approval = input("  Publish to all platforms? [y/N]: ").strip().lower()
            except EOFError:
                approval = ""
            if approval not in ("y", "yes"):
                print(f"\n  ⏸  Publishing skipped. To publish later, run:")
                print(f"     python main.py --resume {case_id} --from publish")
                print()
                logger.info("=== Pipeline paused — user declined publishing ===")
                return

        publisher = VideoPublisher()
        logger.info("Publishing to social platforms...")
        publish_results = publisher.publish(case_id, metadata)
        print("─── Publish Results ──────────────────────────────────────")
        print(json.dumps(publish_results, indent=2, ensure_ascii=False))
        print("───────────────────────────────────────────────────────────\n")

    logger.info("=== Pipeline Complete ===")


def main() -> None:
    # ── Parse CLI arguments ───────────────────────────────────────────
    parser = argparse.ArgumentParser(
        description="Chucky AI — Department of the Unknown",
        epilog=(
            "Resume examples:\n"
            "  python main.py --resume the_oakville_blobs --from render\n"
            "  python main.py --resume the_oakville_blobs --from publish\n"
            "  python main.py --resume the_oakville_blobs --from captions\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("topic", nargs="?", default=None, help="Topic override")
    parser.add_argument(
        "--category",
        choices=[
            "real_world_unexplained", "unexplained_broadcasts",
            "urban_legends", "historical_encounters", "vanishings_cryptids",
        ],
        help="Force a specific story category instead of auto-rotation",
    )
    parser.add_argument(
        "--resume", metavar="CASE_ID",
        help="Resume pipeline for an existing case (e.g. 'the_oakville_blobs')",
    )
    parser.add_argument(
        "--from", dest="from_phase", default="render",
        choices=["captions", "seo", "render", "publish"],
        help="Phase to resume from (default: render)",
    )
    parser.add_argument(
        "--style",
        choices=["dark_comic", "vintage_illustration"],
        help="Force a specific art style instead of auto-selection",
    )
    args = parser.parse_args()

    if args.resume:
        phase_num = PHASE_MAP[args.from_phase]
        resume_pipeline(args.resume, phase_num)
        return

    logger.info("=== Chucky AI — Pipeline Start ===")

    # Phase 0 — Autonomous Brainstorming
    brainstormer = IdeaGenerator()

    if args.topic:
        topic = args.topic
        category = args.category
        logger.info("Manual topic override: %s (category: %s)", topic, category)
    else:
        topic, category = brainstormer.generate_topic(
            category_override=args.category,
        )
        logger.info("Brainstormer selected topic: %s (category: %s)", topic, category)

    print("\n─── Brainstormer Output ───────────────────────────────────")
    print(f"  Topic: {topic}")
    if category:
        print(f"  Category: {category}")
    print("───────────────────────────────────────────────────────────\n")

    # Phase 1 — Research
    researcher = AnomalyResearcher()

    logger.info("Researching topic: %s", topic)
    case_data = researcher.research_case(topic)

    # Save topic to memory so it's never repeated
    brainstormer.save_topic(topic, category)

    print("\n─── Research Output ───────────────────────────────────────")
    print(json.dumps(case_data, indent=2, ensure_ascii=False))
    print("───────────────────────────────────────────────────────────\n")

    # Phase 2 — Script Writing
    writer = NarrativeScriptwriter()

    logger.info("Writing narration script...")
    script_data = writer.write_script(case_data)

    print("─── Script Output ────────────────────────────────────────")
    print(json.dumps(script_data, indent=2, ensure_ascii=False))
    print("───────────────────────────────────────────────────────────\n")

    # Phase 3 — Visual Storyboard
    director = VisualTechnicalDirector()

    style_label = args.style or 'auto'
    logger.info("Creating visual storyboard (style: %s)...", style_label)
    storyboard_data = director.create_storyboard(script_data, force_style=args.style, category=category)

    chosen_style = storyboard_data.get("chosen_style", "unknown")
    logger.info("Director chose style: %s", chosen_style)

    print("─── Storyboard Output ────────────────────────────────────")
    print(f"  Auto-selected style: {chosen_style}")
    print(json.dumps(storyboard_data, indent=2, ensure_ascii=False))
    print("───────────────────────────────────────────────────────────\n")

    # Phase 4 — Media Generation
    case_id = _make_case_id(case_data.get("case_name", topic))

    # 4a) Images — dedicated style agent
    if chosen_style == "vintage_illustration":
        image_agent = VintageIllustrationImageGenerator()
    else:
        image_agent = DarkComicImageGenerator()

    logger.info("Generating images for case_%s (style=%s)...", case_id, chosen_style)
    image_results = image_agent.generate_images(storyboard_data, case_id)

    # 4b) Audio + scare videos — integrator
    integrator = MediaIntegrator()

    logger.info("Generating audio & scare videos for case_%s...", case_id)
    media_manifest = integrator.generate_media(storyboard_data, case_id, image_results=image_results)

    print("─── Media Manifest ───────────────────────────────────────")
    print(json.dumps(media_manifest, indent=2, ensure_ascii=False))
    print("───────────────────────────────────────────────────────────\n")

    # Phase 4.5 — Caption Generation
    captioner = Captioner()

    logger.info("Generating word-level captions...")
    captions_data = captioner.generate_captions(case_id, media_manifest)

    print("─── Captions Output ──────────────────────────────────────")
    print(json.dumps(captions_data, indent=2, ensure_ascii=False))
    print("───────────────────────────────────────────────────────────\n")

    # Phase 5 — SEO & Metadata
    seo = SEOMetadataAgent()

    logger.info("Generating upload metadata...")
    metadata = seo.generate_metadata(case_id, case_data, script_data)

    print("─── Metadata Output ──────────────────────────────────────")
    print(json.dumps(metadata, indent=2, ensure_ascii=False))
    print("───────────────────────────────────────────────────────────\n")

    # Phase 6 — Remotion Render
    composer = RemotionComposer()

    logger.info("Building Remotion props and rendering video...")
    props_path = composer.build_video(case_id, media_manifest, captions_data)

    print("─── Render Complete ──────────────────────────────────────")
    print(f"  Props:  {props_path}")
    print(f"  Video:  out/case_{case_id}_final.mp4")
    print("───────────────────────────────────────────────────────────\n")

    # ── Approval gate ─────────────────────────────────────────────────
    # Auto-rename: find any rendered video and rename to canonical _final.mp4
    out_dir = Path("out")
    canonical = out_dir / f"case_{case_id}_final.mp4"
    if not canonical.is_file():
        candidates = sorted(out_dir.glob(f"case_{case_id}*.mp4"))
        if candidates:
            candidates[0].rename(canonical)
            logger.info("Renamed %s → %s", candidates[0].name, canonical.name)
        else:
            print(f"❌ No rendered video found in {out_dir} for case '{case_id}'.")
            sys.exit(1)

    print("╔══════════════════════════════════════════════════════════╗")
    print("║               REVIEW BEFORE PUBLISHING                  ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print(f"  Video:  {canonical}")
    print(f"  Case:   {case_id}")
    if metadata:
        yt = metadata.get("youtube_metadata", {})
        if yt:
            print(f"  Title:  {yt.get('title', 'N/A')}")
    print()
    try:
        approval = input("  Publish to all platforms? [y/N]: ").strip().lower()
    except EOFError:
        approval = ""
    if approval not in ("y", "yes"):
        print(f"\n  ⏸  Publishing skipped. To publish later, run:")
        print(f"     python main.py --resume {case_id} --from publish")
        print()
        logger.info("=== Pipeline paused — user declined publishing ===")
        return

    # Phase 7 — Publish to Social Platforms
    publisher = VideoPublisher()

    logger.info("Publishing to social platforms...")
    publish_results = publisher.publish(case_id, metadata)

    print("─── Publish Results ──────────────────────────────────────")
    print(json.dumps(publish_results, indent=2, ensure_ascii=False))
    print("───────────────────────────────────────────────────────────\n")

    logger.info("=== Pipeline Complete ===")


if __name__ == "__main__":
    main()
