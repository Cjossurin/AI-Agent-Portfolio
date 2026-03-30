"""
Client Profile Manager - Niche Selection & Multi-Client Management
====================================================================
Manages client profiles with niche-specific settings for all agents.

Features:
- Client niche selection from 50+ predefined niches
- Industry-specific templates and strategies
- Platform recommendations per niche
- Tone/voice presets per industry
- RAG knowledge base per client
- Voice matching integration

Each client gets:
- Unique niche (e.g., "travel_agency", "fitness_coaching", "ecommerce_fashion")
- Niche-specific content strategies
- Platform mix optimized for their industry
- Tone/style presets
- Custom knowledge base
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum


class ClientNiche(Enum):
    """50+ predefined client niches with industry-specific strategies."""
    
    # Business & Professional Services
    BUSINESS_COACHING = "business_coaching"
    EXECUTIVE_COACHING = "executive_coaching"
    CAREER_COACHING = "career_coaching"
    CONSULTING = "consulting"
    ACCOUNTING = "accounting"
    LEGAL_SERVICES = "legal_services"
    REAL_ESTATE = "real_estate"
    INSURANCE = "insurance"
    FINANCIAL_ADVISOR = "financial_advisor"
    
    # Health & Wellness
    FITNESS_COACHING = "fitness_coaching"
    PERSONAL_TRAINING = "personal_training"
    YOGA_INSTRUCTOR = "yoga_instructor"
    NUTRITION_COACHING = "nutrition_coaching"
    MENTAL_HEALTH = "mental_health"
    WELLNESS_BRAND = "wellness_brand"
    MEDICAL_PRACTICE = "medical_practice"
    DENTAL_PRACTICE = "dental_practice"
    
    # Creative & Entertainment
    CONTENT_CREATOR = "content_creator"
    INFLUENCER = "influencer"
    PHOTOGRAPHER = "photographer"
    VIDEOGRAPHER = "videographer"
    MUSICIAN = "musician"
    ARTIST = "artist"
    WRITER = "writer"
    PODCASTER = "podcaster"
    
    # E-commerce & Retail
    ECOMMERCE_FASHION = "ecommerce_fashion"
    ECOMMERCE_BEAUTY = "ecommerce_beauty"
    ECOMMERCE_TECH = "ecommerce_tech"
    ECOMMERCE_HOME = "ecommerce_home"
    DROPSHIPPING = "dropshipping"
    HANDMADE_PRODUCTS = "handmade_products"
    
    # Travel & Hospitality
    TRAVEL_AGENCY = "travel_agency"
    HOTEL = "hotel"
    RESTAURANT = "restaurant"
    CAFE = "cafe"
    EVENT_PLANNING = "event_planning"
    TOURISM = "tourism"
    
    # Education & Training
    ONLINE_COURSES = "online_courses"
    TUTORING = "tutoring"
    LANGUAGE_TEACHER = "language_teacher"
    SKILL_TRAINING = "skill_training"
    EDUCATIONAL_CONTENT = "educational_content"
    
    # Technology & SaaS
    SAAS_B2B = "saas_b2b"
    SAAS_B2C = "saas_b2c"
    APP_DEVELOPER = "app_developer"
    TECH_SUPPORT = "tech_support"
    DIGITAL_AGENCY = "digital_agency"
    
    # Lifestyle & Personal
    LIFESTYLE_BLOGGER = "lifestyle_blogger"
    PARENTING = "parenting"
    DATING_COACH = "dating_coach"
    RELATIONSHIP_COACH = "relationship_coach"
    MOTIVATIONAL_SPEAKER = "motivational_speaker"
    LIFE_COACH = "life_coach"
    
    # Other
    NONPROFIT = "nonprofit"
    LOCAL_BUSINESS = "local_business"
    FRANCHISE = "franchise"
    AUTOMOTIVE = "automotive"
    PET_SERVICES = "pet_services"
    HOME_SERVICES = "home_services"


# Niche-specific configuration
NICHE_CONFIGS = {
    ClientNiche.TRAVEL_AGENCY.value: {
        "platforms": ["instagram", "facebook", "tiktok", "youtube"],
        "content_mix": {"video": 40, "image": 40, "article": 10, "story": 10},
        "posting_frequency": 7,  # posts per week
        "tone": "casual, adventurous, inspiring",
        "keywords": ["travel", "vacation", "adventure", "explore", "wanderlust"],
        "optimal_times": ["9am", "1pm", "7pm"],
        "content_pillars": ["destination highlights", "travel tips", "customer stories", "deals/promotions"]
    },
    ClientNiche.FITNESS_COACHING.value: {
        "platforms": ["instagram", "youtube", "tiktok", "facebook"],
        "content_mix": {"video": 50, "image": 30, "article": 10, "story": 10},
        "posting_frequency": 10,
        "tone": "motivational, energetic, supportive",
        "keywords": ["fitness", "workout", "training", "health", "gains"],
        "optimal_times": ["6am", "12pm", "6pm"],
        "content_pillars": ["workout tutorials", "progress tracking", "nutrition tips", "motivation"]
    },
    ClientNiche.BUSINESS_COACHING.value: {
        "platforms": ["linkedin", "facebook", "instagram", "youtube"],
        "content_mix": {"article": 40, "video": 30, "image": 20, "post": 10},
        "posting_frequency": 5,
        "tone": "professional, insightful, authoritative",
        "keywords": ["business", "leadership", "strategy", "growth", "success"],
        "optimal_times": ["8am", "12pm", "5pm"],
        "content_pillars": ["leadership insights", "case studies", "business strategies", "client wins"]
    },
    ClientNiche.ECOMMERCE_FASHION.value: {
        "platforms": ["instagram", "tiktok", "facebook", "pinterest"],
        "content_mix": {"image": 50, "video": 30, "story": 15, "carousel": 5},
        "posting_frequency": 12,
        "tone": "trendy, stylish, aspirational",
        "keywords": ["fashion", "style", "outfit", "trending", "shopnow"],
        "optimal_times": ["10am", "2pm", "8pm"],
        "content_pillars": ["product showcases", "styling tips", "new arrivals", "customer photos"]
    },
    ClientNiche.CONTENT_CREATOR.value: {
        "platforms": ["youtube", "instagram", "tiktok", "twitter"],
        "content_mix": {"video": 60, "image": 20, "story": 15, "post": 5},
        "posting_frequency": 14,
        "tone": "authentic, relatable, entertaining",
        "keywords": ["content", "creator", "viral", "trending", "follow"],
        "optimal_times": ["7am", "3pm", "9pm"],
        "content_pillars": ["behind the scenes", "tutorials", "vlogs", "collaborations"]
    },
    ClientNiche.SAAS_B2B.value: {
        "platforms": ["linkedin", "twitter", "youtube", "blog"],
        "content_mix": {"article": 40, "video": 30, "image": 20, "post": 10},
        "posting_frequency": 5,
        "tone": "professional, data-driven, solution-focused",
        "keywords": ["saas", "software", "productivity" "automation", "ROI"],
        "optimal_times": ["9am", "1pm", "4pm"],
        "content_pillars": ["product features", "case studies", "industry insights", "how-to guides"]
    },
    ClientNiche.RESTAURANT.value: {
        "platforms": ["instagram", "facebook", "tiktok", "google"],
        "content_mix": {"image": 45, "video": 35, "story": 15, "post": 5},
        "posting_frequency": 10,
        "tone": "appetizing, friendly, inviting",
        "keywords": ["food", "restaurant", "delicious", "dining", "menu"],
        "optimal_times": ["11am", "2pm", "6pm"],
        "content_pillars": ["menu highlights", "chef specials", "customer reviews", "events"]
    },
    ClientNiche.REAL_ESTATE.value: {
        "platforms": ["facebook", "instagram", "linkedin", "youtube"],
        "content_mix": {"video": 40, "image": 35, "article": 15, "carousel": 10},
        "posting_frequency": 6,
        "tone": "professional, trustworthy, informative",
        "keywords": ["realestate", "property", "home", "listing", "market"],
        "optimal_times": ["8am", "12pm", "7pm"],
        "content_pillars": ["property listings", "market updates", "buyer tips", "neighborhood highlights"]
    }
}

# Add default config for niches not specifically configured
DEFAULT_NICHE_CONFIG = {
    "platforms": ["instagram", "facebook", "linkedin"],
    "content_mix": {"image": 40, "video": 30, "article": 20, "post": 10},
    "posting_frequency": 5,
    "tone": "professional, engaging, informative",
    "keywords": [],
    "optimal_times": ["9am", "1pm", "6pm"],
    "content_pillars": ["educational content", "tips & tricks", "behind the scenes", "customer success"]
}


@dataclass
class ClientProfile:
    """Complete client profile with niche and settings."""
    client_id: str
    client_name: str
    niche: str  # ClientNiche value
    business_description: str
    
    # Niche-specific settings (auto-populated from NICHE_CONFIGS)
    platforms: List[str]
    content_mix: Dict[str, int]
    posting_frequency: int
    tone: str
    keywords: List[str]
    optimal_times: List[str]
    content_pillars: List[str]
    
    # Additional settings
    business_name: Optional[str] = None  # Matches DB column; agents use this for RAG queries
    voice_profile_id: Optional[str] = None
    rag_knowledge_base_id: Optional[str] = None
    timezone: str = "UTC"
    language: str = "en"
    
    # Metadata
    created_at: str = None
    updated_at: str = None
    active: bool = True
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()
        if self.updated_at is None:
            self.updated_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ClientProfile':
        import dataclasses as _dc
        valid_fields = {f.name for f in _dc.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


class ClientProfileManager:
    """Manages client profiles with niche-based settings."""
    
    def __init__(self, storage_dir: str = "client_profiles"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._profile_cache: Dict[str, ClientProfile] = {}
        print(f"✅ Client Profile Manager initialized")
        print(f"📁 Storage: {self.storage_dir.absolute()}")
    
    def create_client_profile(
        self,
        client_id: str,
        client_name: str,
        niche: str,  # ClientNiche value
        business_description: str,
        custom_settings: Optional[Dict] = None
    ) -> ClientProfile:
        """
        Create a new client profile with niche-specific settings.
        
        Args:
            client_id: Unique client identifier
            client_name: Display name
            niche: Client niche (from ClientNiche enum)
            business_description: Brief description of the business
            custom_settings: Override niche defaults if needed
        
        Returns:
            ClientProfile with niche-optimized settings
        """
        print(f"\n🎨 Creating client profile for {client_name}...")
        print(f"   Niche: {niche}")
        
        # Get niche-specific config
        niche_config = NICHE_CONFIGS.get(niche, DEFAULT_NICHE_CONFIG).copy()
        
        # Apply custom overrides if provided
        if custom_settings:
            niche_config.update(custom_settings)
        
        # Create profile
        profile = ClientProfile(
            client_id=client_id,
            client_name=client_name,
            niche=niche,
            business_description=business_description,
            platforms=niche_config["platforms"],
            content_mix=niche_config["content_mix"],
            posting_frequency=niche_config["posting_frequency"],
            tone=niche_config["tone"],
            keywords=niche_config["keywords"],
            optimal_times=niche_config["optimal_times"],
            content_pillars=niche_config["content_pillars"]
        )
        
        # Save to disk
        self._save_profile(profile)
        
        # Cache in memory
        self._profile_cache[client_id] = profile
        
        print(f"✅ Client profile created!")
        print(f"   Platforms: {', '.join(profile.platforms)}")
        print(f"   Posting Frequency: {profile.posting_frequency}/week")
        print(f"   Tone: {profile.tone}")
        
        return profile
    
    def get_client_profile(self, client_id: str) -> Optional[ClientProfile]:
        """Get client profile by ID — checks JSON file first, then falls back to DB."""
        # Check cache
        if client_id in self._profile_cache:
            return self._profile_cache[client_id]
        
        # 1) Try JSON file on disk
        profile_file = self.storage_dir / f"{client_id}.json"
        if profile_file.exists():
            try:
                with open(profile_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                profile = ClientProfile.from_dict(data)
                self._profile_cache[client_id] = profile
                return profile
            except Exception as e:
                print(f"⚠️ Error loading JSON profile for {client_id}: {e}")

        # 2) Fall back to the DB client_profiles table (created during onboarding)
        try:
            from database.db import SessionLocal
            from database.models import ClientProfile as DBProfile
            db = SessionLocal()
            try:
                db_row = db.query(DBProfile).filter(DBProfile.client_id == client_id).first()
                if db_row:
                    niche_val = db_row.niche or "general business"
                    niche_config = NICHE_CONFIGS.get(niche_val, DEFAULT_NICHE_CONFIG).copy()

                    # Build a rich business description from all DB fields
                    desc_parts = [db_row.description or ""]
                    if db_row.services_products:
                        desc_parts.append(f"Services/Products: {db_row.services_products}")
                    if db_row.target_audience:
                        desc_parts.append(f"Target Audience: {db_row.target_audience}")
                    if db_row.unique_value_prop:
                        desc_parts.append(f"Unique Value: {db_row.unique_value_prop}")
                    if db_row.competitors:
                        desc_parts.append(f"Competitors: {db_row.competitors}")
                    full_desc = "\n".join(p for p in desc_parts if p)

                    profile = ClientProfile(
                        client_id=client_id,
                        client_name=db_row.business_name or client_id,
                        niche=niche_val,
                        business_description=full_desc or f"{db_row.business_name} — {niche_val}",
                        platforms=niche_config["platforms"],
                        content_mix=niche_config["content_mix"],
                        posting_frequency=niche_config["posting_frequency"],
                        tone=niche_config["tone"],
                        keywords=niche_config["keywords"],
                        optimal_times=niche_config["optimal_times"],
                        content_pillars=niche_config["content_pillars"],
                    )
                    # Overwrite business_name for easy access
                    profile.business_name = db_row.business_name or client_id

                    # Cache + persist to JSON so next lookup is instant
                    self._profile_cache[client_id] = profile
                    self._save_profile(profile)
                    print(f"✅ Loaded client profile for [{client_id}] from DB "
                          f"(niche={niche_val}, biz={db_row.business_name})")
                    return profile
            finally:
                db.close()
        except Exception as e:
            print(f"⚠️ DB fallback profile lookup failed for {client_id}: {e}")

        return None
    
    def update_client_profile(
        self,
        client_id: str,
        updates: Dict
    ) -> Optional[ClientProfile]:
        """Update existing client profile."""
        profile = self.get_client_profile(client_id)
        if not profile:
            return None
        
        # Update fields
        for key, value in updates.items():
            if hasattr(profile, key):
                setattr(profile, key, value)
        
        profile.updated_at = datetime.now().isoformat()
        
        # Save
        self._save_profile(profile)
        self._profile_cache[client_id] = profile
        
        return profile
    
    def list_all_profiles(self) -> List[Dict]:
        """List all client profiles."""
        profiles = []
        
        for profile_file in self.storage_dir.glob("*.json"):
            try:
                with open(profile_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                profiles.append({
                    "client_id": data["client_id"],
                    "client_name": data["client_name"],
                    "niche": data["niche"],
                    "active": data.get("active", True),
                    "created_at": data["created_at"]
                })
            except Exception as e:
                print(f"⚠️ Skipping invalid profile {profile_file.name}: {e}")
        
        return sorted(profiles, key=lambda x: x["created_at"], reverse=True)
    
    def get_available_niches(self) -> Dict[str, List[str]]:
        """Get all available niches organized by category."""
        categories = {
            "Business & Professional Services": [
                "business_coaching", "executive_coaching", "career_coaching",
                "consulting", "accounting", "legal_services", "real_estate",
                "insurance", "financial_advisor"
            ],
            "Health & Wellness": [
                "fitness_coaching", "personal_training", "yoga_instructor",
                "nutrition_coaching", "mental_health", "wellness_brand",
                "medical_practice", "dental_practice"
            ],
            "Creative & Entertainment": [
                "content_creator", "influencer", "photographer",
                "videographer", "musician", "artist", "writer", "podcaster"
            ],
            "E-commerce & Retail": [
                "ecommerce_fashion", "ecommerce_beauty", "ecommerce_tech",
                "ecommerce_home", "dropshipping", "handmade_products"
            ],
            "Travel & Hospitality": [
                "travel_agency", "hotel", "restaurant", "cafe",
                "event_planning", "tourism"
            ],
            "Education & Training": [
                "online_courses", "tutoring", "language_teacher",
                "skill_training", "educational_content"
            ],
            "Technology & SaaS": [
                "saas_b2b", "saas_b2c", "app_developer",
                "tech_support", "digital_agency"
            ],
            "Lifestyle & Personal": [
                "lifestyle_blogger", "parenting", "dating_coach",
                "relationship_coach", "motivational_speaker", "life_coach"
            ],
            "Other": [
                "nonprofit", "local_business", "franchise",
                "automotive", "pet_services", "home_services"
            ]
        }
        return categories
    
    def _save_profile(self, profile: ClientProfile):
        """Save profile to disk."""
        profile_file = self.storage_dir / f"{profile.client_id}.json"
        
        try:
            with open(profile_file, 'w', encoding='utf-8') as f:
                json.dump(profile.to_dict(), f, indent=2, ensure_ascii=False)
            print(f"💾 Saved profile to {profile_file}")
        except Exception as e:
            print(f"❌ Error saving profile: {e}")
            raise


if __name__ == "__main__":
    print("\n🧪 Testing Client Profile Manager...\n")
    
    # Initialize manager
    manager = ClientProfileManager()
    
    # Show available niches
    niches = manager.get_available_niches()
    print(f"\n📊 Available Niches ({sum(len(v) for v in niches.values())} total):")
    for category, niche_list in niches.items():
        print(f"\n{category}:")
        for niche in niche_list:
            print(f"  - {niche}")
    
    # Create test profiles for different niches
    test_profiles = [
        {
            "client_id": "travel_agency_01",
            "client_name": "Paradise Travels",
            "niche": ClientNiche.TRAVEL_AGENCY.value,
            "business_description": "Luxury travel agency specializing in Caribbean destinations"
        },
        {
            "client_id": "fitness_coach_01",
            "client_name": "FitLife Coaching",
            "niche": ClientNiche.FITNESS_COACHING.value,
            "business_description": "Online fitness coaching for busy professionals"
        },
        {
            "client_id": "saas_company_01",
            "client_name": "AutomateAI",
            "niche": ClientNiche.SAAS_B2B.value,
            "business_description": "B2B SaaS platform for marketing automation"
        }
    ]
    
    print("\n" + "="*70)
    print("Creating Test Client Profiles")
    print("="*70)
    
    for test_data in test_profiles:
        profile = manager.create_client_profile(**test_data)
        print(f"\n✅ {profile.client_name} ({profile.niche})")
        print(f"   Content Pillars: {', '.join(profile.content_pillars)}")
        print(f"   Best Times: {', '.join(profile.optimal_times)}")
    
    # List all profiles
    print("\n" + "="*70)
    print("All Client Profiles")
    print("="*70)
    all_profiles = manager.list_all_profiles()
    for profile_summary in all_profiles:
        print(f"\n- {profile_summary['client_name']} ({profile_summary['client_id']})")
        print(f"  Niche: {profile_summary['niche']}")
        print(f"  Status: {'Active' if profile_summary['active'] else 'Inactive'}")
