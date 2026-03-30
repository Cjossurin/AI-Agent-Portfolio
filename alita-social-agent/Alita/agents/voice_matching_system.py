"""
Voice Matching System - Multi-Client Voice Profile Management
Stores and manages unique writing styles for each client.

Features:
- Multi-client voice profiles (each client gets unique voice DNA)
- Quality scoring (0-100) for voice samples
- Voice profile validation
- Dashboard-ready API endpoints
- Integration with engagement agents
"""
import os
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()


@dataclass
class VoiceProfile:
    """Represents a client's unique voice profile."""
    client_id: str
    owner_name: str
    style_dna: str  # The normalized voice samples
    quality_score: float  # 0-100 quality score
    sample_count: int  # Number of samples used
    created_at: str
    updated_at: str
    metadata: Dict = None  # Additional info (platforms, languages, etc.)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'VoiceProfile':
        """Create from dictionary."""
        return cls(**data)


class VoiceMatchingSystem:
    """Manages voice profiles for multiple clients."""
    
    def __init__(self, storage_dir: str = "voice_profiles"):
        """
        Initialize Voice Matching System.
        
        Args:
            storage_dir: Directory to store voice profiles
        """
        self.claude_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Model configuration
        self.sonnet_model = os.getenv("CLAUDE_SONNET_MODEL", "claude-sonnet-4-5-20250929")
        
        # Cache for loaded profiles (in-memory for fast access)
        self._profile_cache: Dict[str, VoiceProfile] = {}
        
        print(f"✅ Voice Matching System initialized")
        print(f"📁 Storage: {self.storage_dir.absolute()}")
    
    def create_voice_profile(
        self, 
        client_id: str, 
        raw_samples: str, 
        owner_name: str = "Client",
        metadata: Dict = None
    ) -> VoiceProfile:
        """
        Create a new voice profile from raw writing samples.
        
        Args:
            client_id: Unique client identifier
            raw_samples: Raw text samples (chat logs, posts, etc.)
            owner_name: Name of the person whose voice we're learning
            metadata: Additional metadata (platform, language, etc.)
        
        Returns:
            VoiceProfile with quality score and normalized samples
        """
        print(f"\n🎨 Creating voice profile for {client_id}...")
        print(f"📊 Raw samples: {len(raw_samples)} characters")
        
        # Generate style DNA using Claude
        style_dna = self._normalize_samples(raw_samples, owner_name)
        
        # Calculate quality score
        quality_score = self._calculate_quality_score(style_dna, raw_samples)
        
        # Count samples
        sample_count = len([line for line in raw_samples.split('\n') if line.strip()])
        
        # Create profile
        now = datetime.now().isoformat()
        profile = VoiceProfile(
            client_id=client_id,
            owner_name=owner_name,
            style_dna=style_dna,
            quality_score=quality_score,
            sample_count=sample_count,
            created_at=now,
            updated_at=now,
            metadata=metadata or {}
        )
        
        # Save to disk
        self._save_profile(profile)
        
        # Cache in memory
        self._profile_cache[client_id] = profile
        
        print(f"✅ Voice profile created!")
        print(f"   Quality Score: {quality_score:.1f}/100")
        print(f"   Sample Count: {sample_count}")
        
        return profile
    
    def update_voice_profile(
        self, 
        client_id: str, 
        additional_samples: str
    ) -> VoiceProfile:
        """
        Update existing voice profile with new samples.
        
        Args:
            client_id: Client identifier
            additional_samples: New writing samples to add
        
        Returns:
            Updated VoiceProfile
        """
        print(f"\n🔄 Updating voice profile for {client_id}...")
        
        # Load existing profile
        profile = self.get_voice_profile(client_id)
        if not profile:
            raise ValueError(f"No voice profile found for {client_id}")
        
        # Combine old and new samples
        combined_samples = f"{profile.style_dna}\n\n{additional_samples}"
        
        # Re-normalize
        style_dna = self._normalize_samples(combined_samples, profile.owner_name)
        
        # Recalculate quality
        quality_score = self._calculate_quality_score(style_dna, combined_samples)
        
        # Update profile
        profile.style_dna = style_dna
        profile.quality_score = quality_score
        profile.sample_count += len([line for line in additional_samples.split('\n') if line.strip()])
        profile.updated_at = datetime.now().isoformat()
        
        # Save
        self._save_profile(profile)
        self._profile_cache[client_id] = profile
        
        print(f"✅ Voice profile updated!")
        print(f"   New Quality Score: {quality_score:.1f}/100")
        
        return profile
    
    def get_voice_profile(self, client_id: str) -> Optional[VoiceProfile]:
        """
        Get voice profile for a client.
        Priority: cache → DB → disk file.
        """
        # Check cache first
        if client_id in self._profile_cache:
            return self._profile_cache[client_id]
        
        # Try PostgreSQL (survives Railway redeploys)
        try:
            from database.db import SessionLocal
            from database.models import ClientProfile as _CP
            db = SessionLocal()
            try:
                prof = db.query(_CP).filter(_CP.client_id == client_id).first()
                if prof and getattr(prof, "voice_profile_json", None):
                    data = json.loads(prof.voice_profile_json)
                    profile = VoiceProfile.from_dict(data)
                    self._profile_cache[client_id] = profile
                    return profile
            finally:
                db.close()
        except Exception as e:
            print(f"⚠️  VoiceMatchingSystem: DB lookup failed for {client_id}: {e}")

        # Load from disk (fallback)
        profile_file = self.storage_dir / f"{client_id}.json"
        if not profile_file.exists():
            return None
        
        try:
            with open(profile_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            profile = VoiceProfile.from_dict(data)
            self._profile_cache[client_id] = profile
            # Back-fill DB
            self._backfill_voice_to_db(client_id, data)
            return profile
            
        except Exception as e:
            print(f"❌ Error loading profile for {client_id}: {e}")
            return None

    def _backfill_voice_to_db(self, client_id: str, data: dict):
        """Back-fill voice profile from file into PostgreSQL."""
        try:
            from database.db import SessionLocal
            from database.models import ClientProfile as _CP
            db = SessionLocal()
            try:
                prof = db.query(_CP).filter(_CP.client_id == client_id).first()
                if prof:
                    prof.voice_profile_json = json.dumps(data)
                    db.commit()
            finally:
                db.close()
        except Exception:
            pass
    
    def list_all_profiles(self) -> List[Dict]:
        """
        List all voice profiles with summary info.
        
        Returns:
            List of profile summaries
        """
        profiles = []
        
        for profile_file in self.storage_dir.glob("*.json"):
            try:
                with open(profile_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                profiles.append({
                    "client_id": data["client_id"],
                    "owner_name": data["owner_name"],
                    "quality_score": data["quality_score"],
                    "sample_count": data["sample_count"],
                    "created_at": data["created_at"],
                    "updated_at": data["updated_at"]
                })
            except Exception as e:
                print(f"⚠️ Skipping invalid profile {profile_file.name}: {e}")
        
        return sorted(profiles, key=lambda x: x["updated_at"], reverse=True)
    
    def delete_voice_profile(self, client_id: str) -> bool:
        """
        Delete a voice profile.
        
        Args:
            client_id: Client identifier
        
        Returns:
            True if deleted, False if not found
        """
        profile_file = self.storage_dir / f"{client_id}.json"
        
        if not profile_file.exists():
            return False
        
        try:
            profile_file.unlink()
            if client_id in self._profile_cache:
                del self._profile_cache[client_id]
            print(f"✅ Deleted voice profile for {client_id}")
            return True
        except Exception as e:
            print(f"❌ Error deleting profile: {e}")
            return False
    
    def validate_profile(self, client_id: str) -> Tuple[bool, str, float]:
        """
        Validate a voice profile's quality and usability.
        
        Args:
            client_id: Client identifier
        
        Returns:
            Tuple of (is_valid, message, quality_score)
        """
        profile = self.get_voice_profile(client_id)
        
        if not profile:
            return False, f"Profile not found for {client_id}", 0.0
        
        # Quality thresholds
        MIN_SAMPLES = 10
        MIN_QUALITY = 60.0
        
        if profile.sample_count < MIN_SAMPLES:
            return False, f"Not enough samples ({profile.sample_count}/{MIN_SAMPLES} required)", profile.quality_score
        
        if profile.quality_score < MIN_QUALITY:
            return False, f"Quality too low ({profile.quality_score:.1f}/{MIN_QUALITY} required)", profile.quality_score
        
        return True, f"Profile is valid and ready to use", profile.quality_score
    
    def get_style_context_for_prompt(self, client_id: str) -> str:
        """
        Get formatted style context for AI prompts.
        
        Args:
            client_id: Client identifier
        
        Returns:
            Formatted style context string for prompts
        """
        profile = self.get_voice_profile(client_id)
        
        if not profile:
            return ""
        
        # Check if profile is valid
        is_valid, message, score = self.validate_profile(client_id)
        
        if not is_valid:
            print(f"⚠️ Using low-quality profile for {client_id}: {message}")
        
        return f"""### VOICE MATCHING INSTRUCTIONS
You must write in the exact style of {profile.owner_name}. Study these examples carefully and mimic the tone, vocabulary, sentence structure, and personality.

Quality Score: {profile.quality_score:.1f}/100
Samples Analyzed: {profile.sample_count}

--- BEGIN STYLE SAMPLES ---
{profile.style_dna}
--- END STYLE SAMPLES ---

CRITICAL: Match this voice exactly. Use similar:
- Sentence length and structure
- Vocabulary and slang
- Emojis and expressions
- Tone (casual/formal, friendly/professional)
- Personality markers (humor, empathy, directness)
"""
    
    # === PRIVATE METHODS ===
    
    def _normalize_samples(self, raw_text: str, owner_name: str) -> str:
        """Normalize raw samples using Claude."""
        system_prompt = f"""You are a precise Data Formatter for chat logs. Your task is to extract meaningful conversation exchanges.

CRITICAL RULES:
1. The OWNER (the person whose style we're learning) is: "{owner_name}"
2. Everyone else in the chat is the "Other Person"

DATA FORMAT:
- Lines starting with "[DM] {owner_name}:" are messages FROM the owner (these become "My Reply")
- Lines starting with "[DM] [Any Other Name]:" are messages from others (these become "Context")
- Lines starting with "[COMMENT] Me:" are comments FROM the owner (these become "My Reply")
- Lines starting with "[POST]:" are posts FROM the owner (these become "My Reply" with no context)

YOUR TASK:
For each meaningful exchange, extract pairs where:
- "Context" = What the OTHER person said (the message that prompted a response)
- "My Reply" = What {owner_name} said in response

For posts with no context:
- "My Post" = What {owner_name} posted (no context needed)

OUTPUT FORMAT (use exactly this format):
Context: [message from other person]
My Reply: [response from {owner_name}]

OR for standalone posts:
My Post: [content from {owner_name}]

QUALITY FILTERS - SKIP these:
- One-word replies ("ok", "yes", "lol", "nice", "damn")
- System messages ("Liked a message", "sent an attachment", "Reacted")
- Messages without substance
- Exchanges where Context and Reply would be identical (impossible - they're different people!)

QUALITY FILTERS - INCLUDE these:
- Replies showing personality, humor, or wit
- Advice or helpful responses
- Longer, substantive messages (2+ sentences preferred)
- Unique expressions or slang that show voice
- Travel stories, life updates, plans
- Posts showing authentic voice

Extract AT LEAST 30-50 quality exchanges if available. Focus on the BEST examples that showcase {owner_name}'s unique communication style."""

        print(f"🤖 Normalizing samples with Claude...")
        
        response = self.claude_client.messages.create(
            model=self.sonnet_model,
            max_tokens=8000,
            messages=[{
                "role": "user",
                "content": f"{system_prompt}\n\n---RAW SAMPLES START---\n{raw_text}\n---RAW SAMPLES END---"
            }]
        )
        
        return response.content[0].text
    
    def _calculate_quality_score(self, style_dna: str, raw_samples: str) -> float:
        """
        Calculate quality score for voice profile (0-100).
        
        Factors:
        - Number of samples (more is better)
        - Average message length (longer is better)
        - Diversity of vocabulary (more unique words is better)
        - Consistency of style (measured by Claude)
        """
        print(f"📊 Calculating quality score...")
        
        # Factor 1: Sample count (0-30 points)
        lines = [line for line in style_dna.split('\n') if 'My Reply:' in line or 'My Post:' in line]
        sample_count = len(lines)
        sample_score = min(30, (sample_count / 50) * 30)  # 50+ samples = max points
        
        # Factor 2: Average length (0-25 points)
        if lines:
            avg_length = sum(len(line) for line in lines) / len(lines)
            length_score = min(25, (avg_length / 100) * 25)  # 100+ char avg = max points
        else:
            length_score = 0
        
        # Factor 3: Vocabulary diversity (0-25 points)
        words = style_dna.lower().split()
        unique_words = len(set(words))
        diversity_score = min(25, (unique_words / 200) * 25)  # 200+ unique words = max points
        
        # Factor 4: Consistency analysis by Claude (0-20 points)
        consistency_score = self._analyze_consistency(style_dna)
        
        total_score = sample_score + length_score + diversity_score + consistency_score
        
        print(f"   Sample Count: {sample_score:.1f}/30")
        print(f"   Avg Length: {length_score:.1f}/25")
        print(f"   Vocabulary: {diversity_score:.1f}/25")
        print(f"   Consistency: {consistency_score:.1f}/20")
        print(f"   TOTAL: {total_score:.1f}/100")
        
        return round(total_score, 1)
    
    def _analyze_consistency(self, style_dna: str) -> float:
        """Use Claude to analyze style consistency."""
        try:
            prompt = f"""Analyze these writing samples for consistency. Rate the style consistency from 0-20:

- 20: Extremely consistent voice, clear personality, identifiable style
- 15: Mostly consistent, some variation but clear patterns
- 10: Moderate consistency, recognizable but mixed styles
- 5: Low consistency, very mixed styles
- 0: No consistency, completely random

Samples:
{style_dna[:2000]}  

Reply with ONLY a number 0-20."""

            response = self.claude_client.messages.create(
                model=self.sonnet_model,
                max_tokens=10,
                messages=[{"role": "user", "content": prompt}]
            )
            
            score_text = response.content[0].text.strip()
            score = float(score_text)
            return min(20, max(0, score))
            
        except Exception as e:
            print(f"⚠️ Consistency analysis failed: {e}")
            return 10.0  # Default middle score
    
    def _save_profile(self, profile: VoiceProfile):
        """Save profile to PostgreSQL (primary) and disk (cache)."""
        data = profile.to_dict()

        # 1. Write to PostgreSQL (survives Railway redeploys)
        try:
            from database.db import SessionLocal
            from database.models import ClientProfile as _CP
            db = SessionLocal()
            try:
                prof = db.query(_CP).filter(_CP.client_id == profile.client_id).first()
                if prof:
                    prof.voice_profile_json = json.dumps(data)
                    db.commit()
                    print(f"💾 Voice profile saved to DB for {profile.client_id}")
            finally:
                db.close()
        except Exception as e:
            print(f"⚠️  Voice profile DB save failed: {e}")

        # 2. Write to filesystem cache
        profile_file = self.storage_dir / f"{profile.client_id}.json"
        try:
            with open(profile_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"💾 Voice profile cached to {profile_file}")
        except Exception as e:
            print(f"⚠️  Voice profile file save failed: {e}")


if __name__ == "__main__":
    print("\n🧪 Testing Voice Matching System...\n")
    
    # Initialize system
    vms = VoiceMatchingSystem()
    
    # Example: Create a voice profile
    raw_samples = """
    [DM] Prince Jossurin: Yo what's good! Just got back from Miami, the vibes were insane 🔥
    [DM] Friend: That's awesome! How was the weather?
    [DM] Prince Jossurin: Bro it was perfect. Like 80 degrees every day, hit the beach like 5 times lol
    [DM] Friend: Jealous! I'm stuck in cold weather
    [DM] Prince Jossurin: Nah you gotta come next time fr. I'll show you all the spots
    [COMMENT] Me: This is exactly what I needed today! Love the energy 💯
    [POST]: Just launched my new project! Been grinding on this for months and it's finally here. Big thanks to everyone who supported 🙏
    """
    
    profile = vms.create_voice_profile(
        client_id="demo_client",
        raw_samples=raw_samples,
        owner_name="Prince Jossurin",
        metadata={"platform": "instagram", "language": "en"}
    )
    
    print("\n" + "="*60)
    print("VOICE PROFILE CREATED")
    print("="*60)
    print(f"Client: {profile.client_id}")
    print(f"Quality: {profile.quality_score}/100")
    print(f"Samples: {profile.sample_count}")
    
    # Validate profile
    is_valid, message, score = vms.validate_profile("demo_client")
    print(f"\nValidation: {message}")
    
    # Get style context for prompts
    style_context = vms.get_style_context_for_prompt("demo_client")
    print(f"\nStyle Context Length: {len(style_context)} characters")
