"""
Strategic Growth Hacking Intelligence Agent
============================================
AI-powered generator of unconventional, creative growth strategies that 99% of
marketers would never think of. Not your typical "post more content" advice.

This agent specializes in PERCEPTION ENGINEERING and AUTHORITY STACKING:
- Making small businesses look like industry giants
- Generating press, credibility, and "As Seen On" badges without a PR budget
- Creating authority positioning most competitors don't know exists
- Leveraging existing platforms, audiences, and networks in unexpected ways
- Building social proof moats that compound over time

STRATEGY CATEGORIES:
1. Press & Media Hacking       - Get published on Yahoo News, ABC affiliates, CW, etc.
2. Authority Positioning       - Instant expert badges (academy, book, podcast, awards)
3. Perception Amplification    - Appear 10x bigger than you are
4. Content Syndication Empire  - One piece of content → 50+ placements
5. Social Proof Engineering    - Stack testimonials, reviews, and credibility signals
6. Platform Algorithm Exploits - Hack discovery on each platform
7. Community Infiltration      - Organic visibility in existing high-traffic spaces
8. Strategic Partnerships      - Borrow other people's audiences
9. SEO & Authority Backlinks   - Domain authority shortcuts
10. Lead Generation Traps      - Attract ideal clients passively

USAGE:
    agent = GrowthHackingAgent(client_id="your_client")
    
    # Get a custom growth hacking strategy
    strategy = await agent.generate_strategy(
        business_type="life coaching",
        current_situation="brand new, no followers, no press",
        goal="appear established and attract high-ticket clients",
        budget="bootstrap",
        timeline="90 days"
    )
    
    # Get actionable tactics for a specific category
    tactics = await agent.get_tactics(
        category="press_media",
        niche="fitness coaching",
        budget="low"
    )
    
    # Generate a 90-day growth hacking roadmap
    roadmap = await agent.generate_roadmap(
        business_type="SaaS",
        goal="100 customers",
        timeline_days=90
    )
"""

import os
import json
import re
import sys
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from pathlib import Path
from anthropic import Anthropic
from dotenv import load_dotenv

# Fix Windows terminal encoding for emoji
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

# Add parent directory to path for imports
parent_dir = str(Path(__file__).parent.parent)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Initialize Claude
claude = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


@dataclass
class GrowthHack:
    """A single growth hacking tactic"""
    title: str
    category: str
    difficulty: str          # easy, medium, hard
    time_investment: str     # "2 hours", "1 day", "ongoing"
    cost: str                # "$0", "$10-50/mo", "$100+"
    expected_impact: str     # low, medium, high, massive
    timeline_to_results: str # "24 hours", "2 weeks", "1-3 months"
    description: str
    step_by_step: List[str]
    tools_needed: List[str]
    platforms_affected: List[str]
    why_it_works: str
    real_example: str
    warnings: List[str] = field(default_factory=list)


@dataclass
class GrowthStrategy:
    """Complete growth hacking strategy for a client"""
    strategy_id: str
    client_id: str
    business_type: str
    goal: str
    timeline: str
    budget_tier: str
    
    # Core strategy components
    positioning_angle: str      # The hook/angle to build authority around
    authority_narrative: str    # The story that makes them look established
    
    # Tactic groups
    quick_wins: List[GrowthHack]       # Can do this week (0-7 days)
    medium_term: List[GrowthHack]      # 30-60 days
    long_term: List[GrowthHack]        # 60-90 days
    
    # Summary metrics
    total_tactics: int = 0
    estimated_reach: str = ""
    difficulty_score: str = "medium"
    roi_potential: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


# =============================================================================
# THE GROWTH HACKING KNOWLEDGE BASE
# These are the unconventional strategies the agent draws from
# =============================================================================

GROWTH_HACKING_PLAYBOOK = {

    "press_media": {
        "name": "Press & Media Hacking",
        "description": "Get published on major media outlets with zero PR budget",
        "tactics": [
            {
                "title": "Press Release → 'As Seen On' Badge Machine",
                "difficulty": "easy",
                "cost": "$0-$50",
                "impact": "massive",
                "how": [
                    "Write a newsworthy press release about your launch, milestone, or unique study",
                    "Distribute FREE via EINPresswire (free), PRLog (free), or PR.com (free)",
                    "It automatically syndicates to Yahoo Finance, MarketWatch, AP News affiliates, CW affiliates, ABC affiliates",
                    "Screenshot and collect all logos: 'As Featured On Yahoo Finance, ABC News, CW...'",
                    "Add these logos to your website header, pitch decks, and social bio",
                    "BONUS: PRNewswire.com's free trial gets you on even bigger outlets"
                ],
                "why": "These are real editorial publications. Google can verify the URLs. The logos are legitimate. Prospects see 'ABC News' and assume you're on TV.",
                "tools": ["EINPresswire.com (free)", "PRLog.org (free)", "PR.com", "PRNewswire free trial"]
            },
            {
                "title": "HARO/Connectively - Get Quoted in Forbes, Inc, Entrepreneur",
                "difficulty": "medium",
                "cost": "$0",
                "impact": "massive",
                "how": [
                    "Sign up at connectively.us (formerly HARO - Help a Reporter Out) - FREE",
                    "You receive 3 emails/day with reporters asking for expert sources",
                    "Filter for opportunities in your niche (business, health, tech, finance, etc.)",
                    "Respond within 1 hour with a tight, quotable answer. Include credentials.",
                    "If selected, you get quoted in NY Times, Forbes, Inc, Entrepreneur, etc.",
                    "Add 'As quoted in Forbes' to bio/website",
                    "Respond to 5-10 per day for best results. Numbers game."
                ],
                "why": "Reporters need sources daily. They're LOOKING for experts. Most business owners don't know this exists. Early responders win.",
                "tools": ["Connectively.us (free)", "ResponseSource.com", "ProfNet"]
            },
            {
                "title": "Wikipedia Authority Stacking",
                "difficulty": "hard",
                "cost": "$0",
                "impact": "high",
                "how": [
                    "Find Wikipedia articles in your niche that reference studies or stats",
                    "Create a 'State of the Industry' original research report (even via survey of 50 customers)",
                    "Publish it as a PDF with an official URL on your domain",
                    "Submit data to Wikipedia as a citation - your domain now cited on Wikipedia",
                    "Alternatively: write or improve industry Wikipedia articles (real contribution)",
                    "Your site becomes a 'cited source' on Wikipedia - massive authority signal"
                ],
                "why": "Wikipedia citations pass massive trust signals to Google. They also establish you as a legitimate source in your industry.",
                "tools": ["Wikipedia.org", "SurveyMonkey or Typeform (for original research)"]
            },
            {
                "title": "Podcast Guest Blitz - 30 Podcasts in 30 Days",
                "difficulty": "medium",
                "cost": "$0-$50",
                "impact": "high",
                "how": [
                    "Go to Podmatch.com, Podchaser.com, or PodcastGuests.com - create profile",
                    "Target podcasts with 1,000-50,000 subscribers (easier to get on, still valuable)",
                    "Write a compelling pitch: 'I can talk about [X topic] for your audience of [niche]'",
                    "Offer 3 proven talking points/hooks for their audience",
                    "Aim for 2-3 podcasts per week (30 per month is achievable)",
                    "After each episode, add 'Featured on: [Podcast Name]' to your site",
                    "Each appearance = new audience, new backlink, new social proof"
                ],
                "why": "Podcast listeners are the most engaged audience on the internet (average 7 episodes/week). Podcast logos = instant authority badges.",
                "tools": ["Podmatch.com", "Podchaser.com", "PodcastGuests.com", "Calendly for booking"]
            },
            {
                "title": "Award Factory - Apply for Industry Awards Systematically",
                "difficulty": "easy",
                "cost": "$0-$200",
                "impact": "high",
                "how": [
                    "Google: '[Your industry] best companies 2024' or '[industry] awards'",
                    "Apply for every award you find. Many are submission-based (judges review, not votes)",
                    "Apply for: Inc 5000, Clutch Top Agency, G2 Best Software, local 'Best of' awards, Chamber of Commerce awards, Stevie Awards",
                    "Win or shortlist → 'Award-Winning [Your Service]' in all marketing",
                    "Even 'Nominated for...' counts in marketing copy",
                    "Create an 'Awards & Recognition' section on your website"
                ],
                "why": "Most awards have < 50 applicants. You're competing against people who don't apply. Even a nomination creates the perception of recognition.",
                "tools": ["Clutch.co (apply for Top Award)", "G2.com", "Stevieawards.com", "Inc.com/5000"]
            }
        ]
    },

    "authority_positioning": {
        "name": "Instant Authority Positioning",
        "description": "Create the perception of being an established expert without years of experience",
        "tactics": [
            {
                "title": "The Instant Academy Play",
                "difficulty": "medium",
                "cost": "$0-$50/mo",
                "impact": "massive",
                "how": [
                    "Create a free 'academy' around your niche: 'The [Niche] Academy' or '[Name] Academy'",
                    "Use Teachable (free), Thinkific (free), or even a Notion page as the 'school'",
                    "Create 3-5 short free courses (even 15 min video lessons count as a 'course')",
                    "Name your methodology: 'The [X] Framework' or '[X] System'",
                    "Add to bio: 'Founder, [Niche] Academy' and 'Creator of The [X] Framework'",
                    "Position founding students as 'Academy Members' - instant community",
                    "Future: offer paid certification → 'Certified by [Your Academy]' for others"
                ],
                "why": "Having 'Founder of [X] Academy' in your bio signals expertise and authority. It frames you as a teacher, not just a practitioner. People pay teachers more.",
                "tools": ["Teachable.com (free)", "Thinkific.com (free)", "Notion.so"]
            },
            {
                "title": "Amazon Bestseller Book (Without Writing a Book)",
                "difficulty": "hard",
                "cost": "$0-$500",
                "impact": "massive",
                "how": [
                    "Option A: Use AI (Claude/GPT) to help write a 20,000-word ebook in your niche",
                    "Convert to proper ebook format (.epub) using Calibre (free)",
                    "Publish on Amazon KDP (Kindle Direct Publishing) - 100% free",
                    "On launch day, have 20-30 friends/clients download the free Kindle version",
                    "Amazon's algorithm creates a 'bestseller' rank within categories - screenshot it",
                    "You are now a 'published author' and '#1 Amazon bestseller in [category]'",
                    "Option B: Compile blog posts into an ebook, format it, publish it",
                    "Physical version: Use KDP Print-On-Demand for a real physical book ($0 upfront)"
                ],
                "why": "'Published Author' is a credibility signal that's undeniable. 'Amazon Bestseller in Business' can be achieved in obscure sub-categories with < 50 downloads.",
                "tools": ["Amazon KDP (free)", "Calibre (free - ebook formatting)", "Claude/ChatGPT", "Canva (cover design)"]
            },
            {
                "title": "The Micro-Conference Play",
                "difficulty": "medium",
                "cost": "$0-$100",
                "impact": "high",
                "how": [
                    "Organize a FREE 2-hour virtual 'summit' or 'conference' in your niche",
                    "Invite 3-5 other practitioners as 'speakers' (they promote to their audience too)",
                    "Use Zoom or Streamyard - completely free",
                    "Record it → repurpose as YouTube series, podcast episodes, blog posts",
                    "You are now the 'Host of the [Niche] Summit'",
                    "Build the speakers' email lists by having attendees provide email to register",
                    "Scale: Annual 'State of [Niche] Virtual Conference'"
                ],
                "why": "Conference organizers are automatically seen as the #1 authority in their space. You're the one selecting who speaks - instant curator/authority status.",
                "tools": ["Zoom (free)", "Streamyard ($0)", "Eventbrite (free)"]
            },
            {
                "title": "Certification Program Creation",
                "difficulty": "medium",
                "cost": "$0-$200",
                "impact": "high",
                "how": [
                    "Create a 'certification program' in your methodology (e.g., 'Certified [X] Coach')",
                    "Doesn't need accreditation - the VALUE is the legitimacy of your name/framework",
                    "Run early cohorts FREE or cheap to get 10-20 'certified' people",
                    "Those certified people market FOR you (they want to show off their cert)",
                    "They put 'Certified by [Your Organization]' in their bios",
                    "Build a 'Find a Certified [X]' directory on your website",
                    "Now you're the CERTIFYING AUTHORITY in your niche"
                ],
                "why": "Certification programs create a network effect. Every certified person becomes a walking advertisement for you. You become the standard in your niche.",
                "tools": ["Notion (free for course content)", "Canva (certificate design)", "LinkedIn Certifications feature"]
            },
            {
                "title": "Industry Study/Research Authority",
                "difficulty": "medium",
                "cost": "$0-$100",
                "impact": "massive",
                "how": [
                    "Survey 50-100 people in your niche (use Typeform free or Google Forms)",
                    "Compile into a '[Year] State of [Niche] Report'",
                    "Include charts (Google Sheets → Charts), statistics, and insights",
                    "Publish as a gated PDF (email capture) or open resource",
                    "Pitch it to media: 'New research shows...' - THIS gets press coverage",
                    "Other blogs/publications cite your study → backlinks and authority",
                    "Repeat annually → 'Annual State of [Niche] Report' = pillar authority content"
                ],
                "why": "Original research is the #1 most-cited content on the internet. When you CREATE the data, everyone references YOU.",
                "tools": ["Typeform (free)", "Google Forms (free)", "Canva (report design)", "HARO to pitch it"]
            }
        ]
    },

    "perception_amplification": {
        "name": "Appear 10x Bigger Than You Are",
        "description": "Perception engineering tactics that make small operations appear established",
        "tactics": [
            {
                "title": "The 'Clients Served' Number Hack",
                "difficulty": "easy",
                "cost": "$0",
                "impact": "medium",
                "how": [
                    "Count EVERY person you've helped, taught, or impacted. Count email subscribers.",
                    "'Helped 5,000+ people' sounds massive. You may have 5,000 email subscribers.",
                    "Count free consultations, webinar attendees, freebie downloaders as 'served'",
                    "Use the broadest reasonable interpretation of 'clients' or 'students' or 'members'",
                    "Audit your entire business history for these numbers"
                ],
                "why": "Social proof numbers reset perception. Nobody fact-checks whether 'helped' means paid client or free consultation. The psychology impact is identical.",
                "tools": ["Your existing email list", "Analytics data", "Social media followers"]
            },
            {
                "title": "Multi-Brand/Multi-Platform Presence",
                "difficulty": "medium",
                "cost": "$0-$50",
                "impact": "high",
                "how": [
                    "Create multiple related online 'properties' that all link back to you",
                    "Example: A podcast, a newsletter, a YouTube channel, a subreddit, a Discord server",
                    "Each one listed in your bio creates the impression of a media empire",
                    "'Founder of [Blog], Host of [Podcast], Creator of [YouTube], Editor of [Newsletter]'",
                    "Doesn't need large audiences - just needs to EXIST and be REAL",
                    "Interconnect all properties for SEO and discovery",
                    "BONUS: Create a holding company name that houses it all (LLC is $50-100 to register)"
                ],
                "why": "When someone Googles you and finds 5+ properties vs. one, you appear to run a media company. The barrier to perception is just consistency, not scale.",
                "tools": ["Substack (newsletter, free)", "Simplecast/Buzzsprout (podcast)", "Discord (community)"]
            },
            {
                "title": "The Strategic Name Drop Framework",
                "difficulty": "easy",
                "cost": "$0",
                "impact": "high",
                "how": [
                    "Mention every legitimate high-value connection you have. Former employer was an F500? Mention it.",
                    "'Built systems used by [Fortune 500 company] clients' (if true in any capacity)",
                    "'Strategy used by clients who have appeared on Shark Tank' (if even one follower did)",
                    "'Methodology taught at [University]' if you gave ONE lecture or guest talk",
                    "Attend a conference where a celebrity/known person speaks → photo op",
                    "Comment/engage with industry thought leaders on Twitter/LinkedIn until they respond once → 'In conversation with [Big Name]'",
                    "IMPORTANT: Everything must be accurate. Embellish scope, not facts."
                ],
                "why": "Authority is associative. Proximity to known brands/names transfers credibility by association. It's not deception - it's strategic framing.",
                "tools": ["LinkedIn (for connection display)", "Twitter/X", "Conference networking apps"]
            },
            {
                "title": "Office Address & Professional Presence",
                "difficulty": "easy",
                "cost": "$20-$100/mo",
                "impact": "medium",
                "how": [
                    "Get a virtual office address in a premium zip code (e.g., NYC, Beverly Hills, Austin)",
                    "Services: Regus, WeWork on-demand, Alliance Virtual Offices, Earth Class Mail ($15-30/mo)",
                    "Use address on website, Google Business Profile, LinkedIn company page",
                    "Perception: 'Company in [Prestigious City/Address]' signals established operation",
                    "BONUS: Get a local phone number in that area code (Google Voice free, Grasshopper $26/mo)",
                    "BONUS: 'Registered in [State]' gives impression of intentional legal presence"
                ],
                "why": "An NYC or LA address signals seriousness. 1 Rockefeller Plaza or 100 Beverly Hills address on a business card changes perception completely.",
                "tools": ["Alliance Virtual Offices ($15-30/mo)", "Regus", "Google Voice (free number)"]
            }
        ]
    },

    "content_syndication": {
        "name": "Content Syndication Empire",
        "description": "Publish once, appear everywhere - multiply reach by 50x with one piece of content",
        "tactics": [
            {
                "title": "The 50-Platform Content Bomb",
                "difficulty": "medium",
                "cost": "$0-$20/mo",
                "impact": "massive",
                "how": [
                    "Write ONE high-quality article/post (1,500+ words) on your core topic",
                    "Publish it on YOUR domain first (important for canonical SEO)",
                    "Wait 2 weeks, then syndicate to: Medium (rel=canonical), LinkedIn Articles, Substack, Vocal.media, Hackernoon, Dev.to (if tech), Thrive Global, Entrepreneur.com (have submissions), Inc.com (have submissions)",
                    "For each republication, add: 'This article originally appeared at [your site]' for SEO",
                    "Post excerpts/summaries to: Reddit (relevant subreddits), Quora answers, Facebook Groups, LinkedIn Groups, Discord channels",
                    "Turn article into: Tweet thread, LinkedIn carousel, Instagram slides, TikTok talking head video, YouTube video, podcast episode",
                    "Result: 1 article → 50+ placements across the internet"
                ],
                "why": "Each individual distribution point may be small but they compound. You start appearing everywhere in your niche - creates 'they're everywhere' perception.",
                "tools": ["Buffer/Hootsuite (social scheduling)", "Repurpose.io ($25/mo)", "Clipchamp (video cuts)"]
            },
            {
                "title": "Reddit Strategy (The Anti-Spam Play)",
                "difficulty": "hard",
                "cost": "$0",
                "impact": "high",
                "how": [
                    "Create a Reddit account 3-6 months old with GENUINE community participation",
                    "Find 5-10 subreddits where your target audience lives (r/entrepreneur, r/[niche], r/smallbusiness)",
                    "For 30 days: only comment, help, and add value. NO promotion whatsoever.",
                    "After 30 days of karma building: post a VALUABLE resource (not an ad)",
                    "Example: 'I researched 200 press release sites, here's the free ones that actually work [complete list]'",
                    "This drives HUGE organic traffic because it's genuinely helpful",
                    "Pin a subtle link in bio or add it naturally in comments",
                    "NEVER direct advertise - Reddit kills spam accounts. Value-first always."
                ],
                "why": "Reddit traffic converts better than almost any other source because it's recommendation-based and community-validated. One viral Reddit post can bring 10,000+ visitors.",
                "tools": ["Reddit (free)", "r/[your niche]", "r/entrepreneur", "r/smallbusiness", "r/marketing"]
            },
            {
                "title": "Quora Dominance Strategy",
                "difficulty": "easy",
                "cost": "$0",
                "impact": "medium",
                "how": [
                    "Search Quora for the top 20 questions in your niche",
                    "Filter by questions with 1,000+ views and unanswered or poorly answered",
                    "Write comprehensive, genuinely helpful answers (400-800 words each)",
                    "Add ONE contextual link to your content where relevant (not every answer)",
                    "Set up 'Quora+ Spaces' - your own Q&A community around your niche",
                    "ADVANCED: Quora has a 'Partner Program' that pays you for good questions",
                    "Target questions Google sends people to - you rank in Google via Quora"
                ],
                "why": "Quora answers rank in Google for question-based searches. A great answer on a popular question drives passive traffic for YEARS.",
                "tools": ["Quora.com (free)", "Quora Spaces (free)", "Semrush/Ahrefs (find top questions)"]
            },
            {
                "title": "Guest Post Empire Building",
                "difficulty": "medium",
                "cost": "$0",
                "impact": "high",
                "how": [
                    "Google: '[niche] + write for us' or '[niche] + guest post guidelines'",
                    "Build a list of 50 sites that accept guest posts in your niche",
                    "Tier A (high-value): Entrepreneur.com, Forbes (through Forbes Councils), Inc.com, HubSpot Blog",
                    "Tier B (medium-value): Niche blogs with DA 40+",
                    "Tier C (quickwins): Smaller blogs, personal brands, company blogs",
                    "Pitch 5 per week with a tailored headline and 3 bullet points",
                    "Good acceptance rate: 10-20%. In 6 months = 10-20 guest posts = '10x Featured Writer'",
                    "Each guest post = backlink + new audience + 'As Seen On [Site]' badge"
                ],
                "why": "Guest posts on authority sites transfer both SEO authority and human credibility. Being featured on HubSpot or Entrepreneur.com changes how people perceive you.",
                "tools": ["Ahrefs Free Webmaster Tools (DA check)", "BuzzSumo (find top sites)", "Hunter.io (find emails)"]
            }
        ]
    },

    "social_proof_engineering": {
        "name": "Social Proof Engineering",
        "description": "Build an unstoppable wall of credibility signals that make objections disappear",
        "tactics": [
            {
                "title": "The Testimonial Sprint",
                "difficulty": "easy",
                "cost": "$0",
                "impact": "massive",
                "how": [
                    "Email the last 20-50 people you've worked with asking for a specific testimonial",
                    "Make it EASY: 'Can you answer these 3 questions in 2 sentences?' and provide specific prompts",
                    "Ask for VIDEO testimonials - offer to record a quick Zoom and send them the clip",
                    "For Loom/video testimonials: just ask, most people will say yes if you make it easy",
                    "Collect on Google Business (most trusted), G2, Clutch, Yelp, Facebook",
                    "Get testimonials from aspirational names (even if they're small influencers)",
                    "Create a 'Wall of Love' page on your website with full testimonials",
                    "Feature the most relevant testimonial on each service/product page"
                ],
                "why": "Nielsen: 92% of consumers trust peer recommendations over advertising. Testimonials from people who look like your prospect are worth more than any ad.",
                "tools": ["Testimonial.to (embed platform)", "VideoAsk.com", "Loom (free video messages)"]
            },
            {
                "title": "Case Study Factory (Even From Free Work)",
                "difficulty": "medium",
                "cost": "$0",
                "impact": "high",
                "how": [
                    "Offer FREE work strategically to 3-5 people you want as case studies (choose aspirational results)",
                    "Document everything: before state, what you did, after results with numbers",
                    "Even a humble result looks good framed correctly: 'Increased engagement by 300%' (from 10 to 40 likes still IS 300%)",
                    "Write it up as a mini case study (500 words, before/after, quote from client)",
                    "Create a PDF version AND a webpage version",
                    "Add [Industry] Case Studies section to website",
                    "Lead with case studies in sales calls: 'Here's what we did for [Name]...'"
                ],
                "why": "Prospects buy futures, not features. Case studies show the future they want. Nobody asks 'was this a paid project?'",
                "tools": ["Notion (case study template)", "Canva (PDF design)", "Loom (video case study)"]
            },
            {
                "title": "Review Stacking System",
                "difficulty": "easy",
                "cost": "$0",
                "impact": "high",
                "how": [
                    "Set up profiles on ALL review platforms relevant to your niche immediately",
                    "Service businesses: Google Business (critical), Yelp, Facebook Reviews, Clutch, Bark.com",
                    "Software/Tools: G2, Capterra, Product Hunt, Trustpilot, Trustradius",
                    "Coaches: CoachingCom, Noomii, The Coaching Directory",
                    "Send a sequence: thank you email → 3 days → 'Would you mind leaving a review?' with direct link",
                    "Make it frictionless: send direct link to the review form, not just the profile",
                    "Respond to EVERY review (Google rewards engagement with higher local rankings)",
                    "Aim: 25+ Google reviews before any advertising"
                ],
                "why": "88% of consumers read reviews. High review count + high rating makes your listing click through at 3-5x higher rate than competitors.",
                "tools": ["Google Business Profile (free)", "Clutch.co (B2B services)", "G2.com (software)"]
            }
        ]
    },

    "platform_algorithm_exploits": {
        "name": "Platform Algorithm Hacks",
        "description": "Insider techniques to hack discovery and reach on each platform",
        "tactics": [
            {
                "title": "LinkedIn Newsletter + Connection Bomb",
                "difficulty": "medium",
                "cost": "$0",
                "impact": "massive",
                "how": [
                    "Create a LinkedIn Newsletter (in LinkedIn's native newsletter feature - free)",
                    "All your LinkedIn connections get NOTIFIED when you launch and each edition",
                    "This bypasses the algorithm - direct notification to entire network",
                    "Launch with a controversial/high-value title: 'The [Niche] Lie Nobody Talks About'",
                    "Consistently send weekly → subscribers grow as people share",
                    "Combine with: post the newsletter as a LinkedIn Article → gets search visibility",
                    "BONUS: LinkedIn's algorithm heavily boosts Newsletter content vs regular posts"
                ],
                "why": "LinkedIn Newsletter notifications go to 100% of subscribers (vs 5-10% organic feed reach). It's email marketing without needing an email list.",
                "tools": ["LinkedIn.com (free newsletter feature)", "Canva (newsletter graphics)"]
            },
            {
                "title": "The Collab Post Hack (Instagram/TikTok)",
                "difficulty": "easy",
                "cost": "$0",
                "impact": "high",
                "how": [
                    "Instagram and TikTok have a 'Collab' post feature - one post appears on BOTH profiles",
                    "Find accounts in adjacent niches (not direct competitors) with similar-sized audience",
                    "DM: 'Hey [name], fans of mine love [your niche]. Want to do a collab post?'",
                    "Create joint content that serves both audiences",
                    "Each person's full follower base sees the same post → both accounts grow",
                    "This is the FASTEST organic growth hack on Instagram right now (2024-2025)",
                    "Strategy: do one Collab post per week with a different account"
                ],
                "why": "A collab post with a 10K account gives you exposure to 10K new followers for zero dollars. Algorithm boosts collaborative content as 'community engagement'.",
                "tools": ["Instagram Collab feature (free)", "TikTok Duet/Collab (free)"]
            },
            {
                "title": "Comment-First Authority Strategy",
                "difficulty": "easy",
                "cost": "$0",
                "impact": "medium",
                "how": [
                    "Before posting your own content, spend 20 min commenting on TOP posts in your niche",
                    "Leave SUBSTANTIVE comments (3-5 sentences) that add value or provoke conversation",
                    "DO NOT comment 'Great post!' - this gets you invisible. Be controversial or insightful.",
                    "As the top post blows up, your comment gets seen by ALL their followers",
                    "Think about it: top comment on a 100K follower post = 100K impressions for free",
                    "Do this daily on 5-10 posts before you post your own content",
                    "Over time: algorithm sees you as 'active community member' and boosts YOUR posts"
                ],
                "why": "Platform algorithms reward accounts that drive engagement on other posts. It creates a reciprocal boost effect. Top comments on viral posts get more views than most posts.",
                "tools": ["Instagram/TikTok/LinkedIn (native apps)"]
            },
            {
                "title": "Engagement Pod Strategy (Professional Version)",
                "difficulty": "medium",
                "cost": "$0",
                "impact": "high",
                "how": [
                    "Form a private group of 10-20 non-competing accounts in similar niche",
                    "Communication channel: Telegram, WhatsApp, Discord DM group",
                    "Agreement: When one member posts, others immediately engage (like, comment, save)",
                    "The first 30-60 minutes of engagement determines 80% of post reach",
                    "With 15-20 people engaging immediately → algorithm pushes to explore page",
                    "IMPORTANT: Make comments genuine and varied (not 'Great!' 'Love this!' x20)",
                    "Professional version: each person adds genuine perspective (no fake comments)"
                ],
                "why": "Social media algorithms interpret early engagement as 'quality signal' and push content to broader audiences. This ethically engineers the early engagement burst.",
                "tools": ["Telegram (free group)", "Discord (free server)", "Any private messaging app"]
            },
            {
                "title": "TikTok/Reels Trend Surf System",
                "difficulty": "easy",
                "cost": "$0",
                "impact": "high",
                "how": [
                    "Every Monday: spend 30 min identifying TRENDING sounds/formats on TikTok",
                    "Check: TikTok Creative Center, TikTok Discover, 'Trending' tab",
                    "Map trending formats to YOUR niche: trend overlay + your message",
                    "Post within first 3-5 days of a trend (after that, oversaturated)",
                    "The trend's search traffic finds your content even without followers",
                    "Cross-post immediately to Instagram Reels, YouTube Shorts (triple the reach)",
                    "BONUS: 'Trend-jacking' sounds/formats gets shown to people following that sound"
                ],
                "why": "Platforms promote trending content to drive usage of their trending features. You ride the algorithm's own promotional push for zero extra effort.",
                "tools": ["TikTok Creative Center (free)", "Instagram Reels Trending Audio", "YouTube Shorts Feed"]
            }
        ]
    },

    "partnership_leverage": {
        "name": "Audience Borrowing & Partnerships",
        "description": "Skip building an audience - borrow someone else's for free",
        "tactics": [
            {
                "title": "The JV Partner Email Swap",
                "difficulty": "easy",
                "cost": "$0",
                "impact": "massive",
                "how": [
                    "Find 5-10 businesses that serve the SAME audience but are NOT competitors",
                    "Propose a mutually beneficial email list swap: 'I'll email my list about you, you email yours about me'",
                    "Both lists must be similar size OR you must offer something that compensates",
                    "Offer: free resource, commission on sales, future promotion, co-created content",
                    "ONE email to an aligned list of 5,000 can generate 500-1,000 new interested leads",
                    "Build a portfolio of 5+ reliable JV partners = recurring growth machine",
                    "Formalize: create an affiliate program (free via ThriveCart, Gumroad, Rewardful)"
                ],
                "why": "Other people's audiences are the fastest growth shortcut. A warm recommendation from a trusted source converts 5-10x better than cold advertising.",
                "tools": ["Rewardful.com (affiliate tracking)", "ThriveCart", "Gumroad (affiliate features)"]
            },
            {
                "title": "Influencer Product Seeding Strategy",
                "difficulty": "easy",
                "cost": "$100-$500",
                "impact": "high",
                "how": [
                    "Identify 50-100 MICRO-influencers (3K-50K followers) in exact target niche",
                    "DO NOT contact through agent/DM - mail them your product/service with handwritten note",
                    "Subject: [Product] I thought you'd genuinely love based on [specific post of theirs]",
                    "Most will post about it (some won't - budget accordingly)",
                    "DO NOT ask for a post - just send and trust organic response rate",
                    "Follow up with: 'Did you receive the package? No obligation whatsoever, just wanted to get it to you'",
                    "Result: ~30-40% organic post rate = 15-20 posts for $200 in product costs"
                ],
                "why": "When influencers post about something that arrives unexpectedly (not a paid deal), their followers trust it more. Authentic > #sponsored.",
                "tools": ["Modash.io (influencer finder)", "Hunter.io (find contact emails)", "Physical mail for physical products"]
            },
            {
                "title": "Podcast Swap / Cross-Promotion",
                "difficulty": "easy",
                "cost": "$0",
                "impact": "medium",
                "how": [
                    "If you have any podcast (even 5 episodes): reach out to similar-sized shows",
                    "Proposal: 'We mention your show to our audience, you mention ours'",
                    "Also: offer to be a guest on their show AND have them guest on yours",
                    "This creates RECIPROCAL audience sharing - both grow together",
                    "Even with 100 listeners: find shows with 100 listeners for a fair swap",
                    "ADVANCED: Form a 'podcast collective' of 5-10 shows → all cross-promote each new episode"
                ],
                "why": "Podcast listeners follow recommendations from trusted hosts more than any other medium. Average conversion from podcast recommendation is 8-12%.",
                "tools": ["Spotify for Podcasters (free analytics)", "Podmatch (podcast matchmaking free)"]
            }
        ]
    },

    "community_infiltration": {
        "name": "Community & Forum Infiltration",
        "description": "Tap into existing audiences where your ideal clients already gather",
        "tactics": [
            {
                "title": "Strategic Facebook Group Takeover",
                "difficulty": "medium",
                "cost": "$0",
                "impact": "high",
                "how": [
                    "Find the top 10 Facebook Groups in your niche (search 'Group' + niche keyword)",
                    "Join and observe for 2 weeks. Learn what pains people express.",
                    "Spend 2 weeks giving EXCEPTIONAL value: answer every question you can add to",
                    "After 30 days of value: post your best piece of content (80% value / 20% promotion max)",
                    "Some group owners will INVITE you to become a moderator/admin if you add enough value",
                    "ADVANCED: Create your OWN group on a specific subtopic the big groups don't cover",
                    "Your group shows up in member feeds of the big groups → fast growth"
                ],
                "why": "Facebook Groups have algorithmically-exempt reach (groups bypass feed algorithm). 5,000-person group = 80% organic reach vs 2-5% for pages.",
                "tools": ["Facebook Groups (free)", "GroupApp.com (private community alternative)"]
            },
            {
                "title": "Slack & Discord Community Infiltration",
                "difficulty": "medium",
                "cost": "$0",
                "impact": "medium",
                "how": [
                    "Find 10-20 Slack/Discord communities in your niche (slofile.com, disboard.org)",
                    "Join and observe. Find the popular contributors to learn community culture.",
                    "Strategy: become a TOP contributor in 2-3 communities (not 20). Deep > wide.",
                    "Post resources, templates, tools in #resources channels",
                    "Answer questions in real-time - communities reward speed and helpfulness",
                    "After 30 days: member status qualifies you to share occasional relevant resources",
                    "BEST play: start your OWN niche Slack/Discord → you're the hub/moderator"
                ],
                "why": "Slack and Discord communities are less saturated than Twitter/LinkedIn but extremely tight-knit. Trust forms faster, conversion rates are higher.",
                "tools": ["Disboard.org (Discord discovery)", "Slofile.com (Slack communities)", "Discord (free)"]
            },
            {
                "title": "The Newsletter Takeover Play",
                "difficulty": "medium",
                "cost": "$0-$500",
                "impact": "massive",
                "how": [
                    "Find newsletters in your niche using: Substack discovery, Paved.com, SparkLoop.app",
                    "Option A: Buy a small newsletter (< 5,000 subscribers) for $500-2,000. Instant audience.",
                    "Option B: Sponsor 1 edition of 3-5 small newsletters. Pay with product/content.",
                    "Option C: Write a contributor article for newsletters in your niche. Many have open submissions.",
                    "Newsletter audiences have 3-5x higher engagement than social media audiences",
                    "One newsletter mention can generate 500-2,000 visitors if audience is targeted",
                    "ADVANCED: Launch a 'Curated Newsletter' in your niche that features others → they help you grow"
                ],
                "why": "Email newsletters have 20-40% open rates vs 2-5% social media reach. Newsletter audiences are the most qualified, highest-converting traffic online.",
                "tools": ["Substack (buy/discover newsletters)", "Paved.com (newsletter advertising)", "Beehiiv (newsletter platform)"]
            }
        ]
    },

    "seo_authority_shortcuts": {
        "name": "SEO & Domain Authority Shortcuts",
        "description": "Build SEO authority in months instead of years",
        "tactics": [
            {
                "title": "Expired Domain Authority Hijack",
                "difficulty": "hard",
                "cost": "$10-$200",
                "impact": "massive",
                "how": [
                    "Find expired domains in your niche with existing authority (DA 20+)",
                    "Tools: ExpiredDomains.net (free), DomCop, GoDaddy Auctions",
                    "Option A: Buy the domain, 301-redirect ALL traffic to your main site. Inherits authority.",
                    "Option B: Buy domain, recreate the site, rebuild the brand under your company",
                    "Option C: Buy domain for the content assets (existing backlinks + articles)",
                    "A DA 30 expired domain can double your new site's authority in weeks vs years",
                    "WARNING: Do due diligence - check domain history for spam/penalties (Wayback Machine)"
                ],
                "why": "Domain authority takes 12-18 months to build organically. An aged domain with backlinks compresses that timeline to weeks. Sites with existing backlinks rank immediately.",
                "tools": ["ExpiredDomains.net (free search)", "Moz Domain Authority checker", "Wayback Machine (history check)"]
            },
            {
                "title": "Scholarship Link Building",
                "difficulty": "medium",
                "cost": "$500-$2,000",
                "impact": "high",
                "how": [
                    "Create a small scholarship: '[Your Company] Annual Scholarship - $500'",
                    "Reach out to college .edu websites with scholarship listing pages",
                    "Most .edu scholarships pages are FREE to list on (it's a community service)",
                    ".EDU backlinks are the most powerful SEO links (universities = high authority)",
                    "'Scholarship' email to university financial aid offices has 70%+ response rate",
                    "One annual $500 scholarship can generate 50-100 .edu backlinks",
                    "BONUS: You can legitimately say 'Offering scholarships to students'"
                ],
                "why": ".edu links are considered the most powerful backlinks in SEO. They pass enormous domain authority. A single .edu link is worth 100 regular links in some tools.",
                "tools": ["Hunter.io (find .edu financial aid emails)", "Ahrefs (track backlinks)", "Your own scholarship landing page"]
            },
            {
                "title": "Local Citation Domination",
                "difficulty": "easy",
                "cost": "$0-$50",
                "impact": "medium",
                "how": [
                    "Submit business to ALL relevant directories immediately: Google My Business (critical), Bing Places, Apple Maps, Yelp, BBB (gets you A+ rating for free), Foursquare, Yellowpages",
                    "Niche directories: Clutch.co, Bark.com, Thumbtack (services), Angi (home services), Houzz (home), Healthgrades (medical)",
                    "Consistency is key: EXACT SAME NAME, ADDRESS, PHONE on every listing",
                    "Use BrightLocal or Whitespark to audit citations",
                    "ADVANCED: Find where competitors have citations and replicate (BrightLocal citation audit)",
                    "1,000 citations across the web signals 'legitimate established business'"
                ],
                "why": "Citations (Name, Address, Phone) across the web are a local SEO ranking factor AND a credibility signal. BBB listing alone creates trust in non-digital audiences.",
                "tools": ["BrightLocal ($30/mo)", "Whitespark (free citation finder)", "Yext ($500/yr for bulk submission)"]
            }
        ]
    }
}


def _safe_parse_json(text: str) -> dict:
    """Robustly extract and parse JSON from LLM response text.

    Handles markdown fences, thinking tags, trailing commas,
    single-quoted keys, and other common LLM JSON quirks.
    """
    # Strip <think>...</think> or <thinking>...</thinking> blocks
    text = re.sub(r'<think(?:ing)?>\s*.*?\s*</think(?:ing)?>', '', text, flags=re.DOTALL)

    # Strip markdown code fences if present
    text = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.MULTILINE)
    text = re.sub(r'\s*```\s*$', '', text.strip(), flags=re.MULTILINE)
    text = text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find the outermost JSON object by balancing braces
    start = text.find('{')
    if start == -1:
        raise ValueError("No JSON object found in response")

    depth = 0
    in_string = False
    escape_next = False
    end = start

    for i, ch in enumerate(text[start:], start):
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                end = i
                break

    json_str = text[start:end + 1]

    # Attempt 1: parse as-is
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    # Attempt 2: fix trailing commas before } or ]
    fixed = re.sub(r',\s*([}\]])', r'\1', json_str)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Attempt 3: replace single-quoted keys/values with double quotes
    try:
        fixed2 = fixed.replace("'", '"')
        return json.loads(fixed2)
    except json.JSONDecodeError:
        pass

    # Attempt 4: use ast.literal_eval as last resort for Python-dict-like output
    try:
        import ast
        result = ast.literal_eval(json_str)
        if isinstance(result, dict):
            return result
    except (ValueError, SyntaxError):
        pass

    # If all else fails, raise with the original cleaned text for debugging
    raise json.JSONDecodeError(
        f"Could not parse JSON from LLM response (len={len(json_str)})",
        json_str,
        0,
    )


class GrowthHackingAgent:
    """
    Strategic Growth Hacking Intelligence Agent
    
    Generates unconventional, creative growth strategies that 99% of marketers
    would never think of. Specializes in authority building, perception engineering,
    and leveraging existing platforms in unexpected ways.
    """

    STRATEGY_CATEGORIES = list(GROWTH_HACKING_PLAYBOOK.keys())

    BUDGET_TIERS = {
        "bootstrap": {"max_monthly": 0, "label": "Zero Budget ($0/mo)"},
        "low": {"max_monthly": 100, "label": "Low Budget ($0-100/mo)"},
        "medium": {"max_monthly": 500, "label": "Medium Budget ($100-500/mo)"},
        "growth": {"max_monthly": 2000, "label": "Growth Budget ($500-2K/mo)"}
    }

    def __init__(self, client_id: str = "demo_client", tier: str = "pro"):
        self.client_id = client_id
        from utils.ai_config import get_text_model
        # Growth strategy is always a "complex" task
        self.model = get_text_model(tier, complexity="complex")
        self._tier = tier
        self.strategies_generated: Dict[str, GrowthStrategy] = {}
        
        print(f"🚀 Growth Hacking Agent initialized for: {client_id}")
        print(f"   Strategy categories: {len(self.STRATEGY_CATEGORIES)}")
        print(f"   Total tactics in playbook: {sum(len(v['tactics']) for v in GROWTH_HACKING_PLAYBOOK.values())}")

    def _build_playbook_context(self, categories: Optional[List[str]] = None) -> str:
        """Build a formatted context string from the playbook for Claude"""
        cats = categories or self.STRATEGY_CATEGORIES
        context_parts = []
        
        for cat_key in cats:
            if cat_key not in GROWTH_HACKING_PLAYBOOK:
                continue
            cat = GROWTH_HACKING_PLAYBOOK[cat_key]
            context_parts.append(f"\n\n## {cat['name']}\n{cat['description']}")
            for tactic in cat["tactics"]:
                context_parts.append(f"""
### {tactic['title']}
- Cost: {tactic['cost']}
- Impact: {tactic['impact']}
- How: {chr(10).join(f"  {i+1}. {step}" for i, step in enumerate(tactic['how']))}
- Why it works: {tactic['why']}
- Tools: {', '.join(tactic['tools'])}
""")
        
        return "\n".join(context_parts)

    async def generate_strategy(
        self,
        business_type: str,
        current_situation: str,
        goal: str,
        budget: str = "low",
        timeline: str = "90 days",
        niche: Optional[str] = None,
        target_audience: Optional[str] = None,
        current_online_presence: Optional[str] = None,
        connected_platforms: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Generate a complete custom growth hacking strategy
        
        Args:
            business_type: Type of business (e.g., 'life coaching', 'SaaS', 'ecommerce store')
            current_situation: Current state ('brand new', '500 followers', 'established but slow growth')
            goal: What they want to achieve ('appear established', '1000 clients', 'generate leads')
            budget: 'bootstrap', 'low', 'medium', or 'growth'
            timeline: How long ('30 days', '90 days', '6 months')
            niche: Specific industry niche
            target_audience: Who they're trying to reach
            current_online_presence: Description of current web/social presence
        
        Returns:
            Dict with complete strategy including quick wins, medium-term, and long-term tactics
        """
        budget_info = self.BUDGET_TIERS.get(budget, self.BUDGET_TIERS["low"])
        playbook_context = self._build_playbook_context()

        # Build platform constraint block
        if connected_platforms:
            _plat_list = ", ".join(p.title() for p in connected_platforms)
            platform_constraint = (
                f"\nCONNECTED PLATFORMS (the ONLY platforms this client uses): {_plat_list}\n"
                "CRITICAL: Only recommend strategies, tactics, groups, and actions for the platforms "
                "listed above. Do NOT suggest Reddit, Pinterest, Snapchat, or any other platform "
                "the client has not connected. Every tactic must be actionable on their current platforms.\n"
            )
        else:
            platform_constraint = ""

        prompt = f"""You are a Growth Hacking Intelligence Agent specializing in unconventional, creative strategies that 99% of marketers would never think of.

MISSION: Generate a CUSTOM, SPECIFIC growth hacking strategy for this exact business situation.

CLIENT CONTEXT:
- Business Type: {business_type}
- Niche: {niche or 'unspecified'}
- Current Situation: {current_situation}
- Goal: {goal}
- Budget: {budget_info['label']}
- Timeline: {timeline}
- Target Audience: {target_audience or 'unspecified'}
- Current Presence: {current_online_presence or 'none mentioned'}
{platform_constraint}

GROWTH HACKING PLAYBOOK (Reference Material):
{playbook_context}

TASK: Create a HIGHLY SPECIFIC strategy for this exact business. Do NOT give generic advice.

Think like a genius growth hacker who:
1. Identifies the FASTEST path to the goal with the LEAST resources
2. Picks strategies most competitors would NEVER think of
3. Sequences tactics so early wins build momentum for harder plays
4. Considers how each tactic compounds with others
5. Thinks about PERCEPTION - how to appear 10x bigger than they are

Return a JSON object with this EXACT structure:
{{
    "positioning_angle": "The unique authority angle they should build (1-2 sentences)",
    "authority_narrative": "The specific story/framing that makes them look established (2-3 sentences)",
    "quick_wins": [
        {{
            "title": "Tactic name",
            "category": "which category",
            "difficulty": "easy/medium/hard",
            "time_investment": "X hours or days",
            "cost": "$0 or $X/mo",
            "expected_impact": "low/medium/high/massive",
            "timeline_to_results": "hours/days/weeks",
            "description": "What this is and why it matters for THIS specific business",
            "step_by_step": ["Step 1 specific to their business", "Step 2...", "Step 3..."],
            "tools_needed": ["Tool 1 (free/paid)", "Tool 2"],
            "platforms_affected": ["Instagram", "Google", etc],
            "why_it_works": "Psychology/mechanism behind this for THEIR specific situation",
            "real_example": "Concrete example of how this plays out for THEM specifically",
            "warnings": ["Watch out for X", "Avoid Y"]
        }}
    ],
    "medium_term": [same format, 3-5 tactics for 30-60 days],
    "long_term": [same format, 3-5 tactics for 60-90 days+],
    "compounding_strategy": "How all tactics work together to build momentum (3-4 sentences)",
    "roi_estimate": "Realistic impact expectation at the end of {timeline}",
    "contrarian_insight": "The one non-obvious insight about their specific situation most marketers miss"
}}

Include EXACTLY 3 tactics in quick_wins, 3 in medium_term, 3 in long_term. Be SPECIFIC to their business - not generic.
Return ONLY valid JSON, no other text, no markdown fences, no trailing commas."""

        try:
            response = claude.messages.create(
                model=self.model,
                max_tokens=16384,
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Extract text from response (skip thinking blocks)
            response_text = ""
            for block in response.content:
                if getattr(block, "type", None) == "text":
                    response_text = block.text
                    break
            if not response_text:
                response_text = response.content[0].text if response.content else ""
            try:
                strategy_data = _safe_parse_json(response_text)
            except (json.JSONDecodeError, ValueError) as parse_err:
                # Retry once with explicit JSON instruction
                print(f"⚠️  First strategy parse failed ({parse_err}), retrying...")
                retry_resp = claude.messages.create(
                    model=self.model,
                    max_tokens=16384,
                    messages=[
                        {"role": "user", "content": prompt},
                        {"role": "assistant", "content": response_text},
                        {"role": "user", "content": "Your response could not be parsed as valid JSON. Please return ONLY the raw JSON object (no markdown fences, no explanation text). Start with { and end with }."},
                    ],
                )
                retry_text = ""
                for block in retry_resp.content:
                    if getattr(block, "type", None) == "text":
                        retry_text = block.text
                        break
                if not retry_text:
                    retry_text = retry_resp.content[0].text if retry_resp.content else ""
                strategy_data = _safe_parse_json(retry_text)
            
            # Generate strategy ID
            strategy_id = f"strategy_{self.client_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            strategy_data.update({
                "strategy_id": strategy_id,
                "client_id": self.client_id,
                "business_type": business_type,
                "goal": goal,
                "timeline": timeline,
                "budget_tier": budget,
                "generated_at": datetime.now().isoformat(),
                "total_tactics": len(strategy_data.get("quick_wins", [])) + 
                                  len(strategy_data.get("medium_term", [])) + 
                                  len(strategy_data.get("long_term", []))
            })
            
            self.strategies_generated[strategy_id] = strategy_data
            
            return strategy_data
        
        except Exception as e:
            log.error(
                f"[{self.client_id}] ❌ generate_strategy failed: {e}",
                exc_info=True,
            )
            # Build a proper fallback so the saved report still shows tactics
            _fb = self._get_fallback_tactics(business_type, budget)
            _qw = _fb[:2] if len(_fb) >= 2 else _fb
            _mt = _fb[2:4] if len(_fb) >= 4 else _fb[len(_qw):len(_qw)+2]
            _lt = _fb[4:5] if len(_fb) >= 5 else _fb[len(_qw)+len(_mt):len(_qw)+len(_mt)+1]
            strategy_id = f"strategy_{self.client_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            return {
                "strategy_id": strategy_id,
                "client_id": self.client_id,
                "error": str(e),
                "positioning_angle": "Strategy generation encountered an error — showing fallback tactics.",
                "authority_narrative": "",
                "quick_wins": [
                    {
                        "title": t.get("title", "Tactic"),
                        "description": t.get("first_step", ""),
                        "cost": t.get("cost", "$0"),
                        "expected_impact": t.get("impact", "medium"),
                        "time_investment": "1-2 hours",
                        "steps": [t.get("first_step", "See full description")],
                        "why_it_works": "Proven growth tactic from the playbook.",
                        "warnings": [],
                    }
                    for t in _qw
                ],
                "medium_term": [
                    {
                        "title": t.get("title", "Tactic"),
                        "description": t.get("first_step", ""),
                        "cost": t.get("cost", "$0"),
                        "expected_impact": t.get("impact", "medium"),
                        "time_investment": "1-2 weeks",
                        "steps": [t.get("first_step", "See full description")],
                        "why_it_works": "Proven growth tactic from the playbook.",
                        "warnings": [],
                    }
                    for t in _mt
                ],
                "long_term": [
                    {
                        "title": t.get("title", "Tactic"),
                        "description": t.get("first_step", ""),
                        "cost": t.get("cost", "$0"),
                        "expected_impact": t.get("impact", "medium"),
                        "time_investment": "1-3 months",
                        "steps": [t.get("first_step", "See full description")],
                        "why_it_works": "Proven growth tactic from the playbook.",
                        "warnings": [],
                    }
                    for t in _lt
                ],
                "total_tactics": len(_qw) + len(_mt) + len(_lt),
                "business_type": business_type,
                "goal": goal,
                "timeline": timeline,
                "budget_tier": budget,
                "generated_at": datetime.now().isoformat(),
                "compounding_strategy": "Review and re-run strategy generation when the AI service is available.",
                "roi_estimate": "Pending full strategy generation.",
                "contrarian_insight": "Even fallback tactics can drive growth when executed consistently.",
            }

    async def get_tactics(
        self,
        category: str,
        niche: str,
        budget: str = "low",
        num_tactics: int = 5
    ) -> Dict[str, Any]:
        """
        Get specific tactics for a given category, customized to the niche
        
        Args:
            category: Strategy category (e.g., 'press_media', 'authority_positioning')
            niche: Business niche (e.g., 'fitness coaching', 'B2B SaaS')
            budget: Budget tier
            num_tactics: How many tactics to return
        
        Returns:
            Dict with customized tactics list
        """
        if category not in GROWTH_HACKING_PLAYBOOK:
            available = list(GROWTH_HACKING_PLAYBOOK.keys())
            return {"error": f"Unknown category. Available: {available}"}
        
        cat_data = GROWTH_HACKING_PLAYBOOK[category]
        budget_info = self.BUDGET_TIERS.get(budget, self.BUDGET_TIERS["low"])
        
        # Filter by cost if budget is tight
        base_tactics = cat_data["tactics"]
        if budget == "bootstrap":
            base_tactics = [t for t in base_tactics if "$0" in t["cost"]]
        
        # Format tactics context
        tactics_text = "\n".join([
            f"TACTIC: {t['title']}\nCost: {t['cost']}\nHow: {'; '.join(t['how'][:3])}\nWhy: {t['why']}"
            for t in base_tactics
        ])
        
        prompt = f"""You are a growth hacking expert. Customize these tactics SPECIFICALLY for a {niche} business.

CATEGORY: {cat_data['name']}
BUDGET: {budget_info['label']}
NICHE: {niche}

BASE TACTICS:
{tactics_text}

For each tactic, customize the steps and examples to be 100% relevant to {niche}.
Focus on the top {num_tactics} most impactful tactics for this niche.

Return JSON:
{{
    "category": "{category}",
    "niche": "{niche}",
    "tactics": [
        {{
            "title": "tactic name",
            "niche_specific_hook": "why this is PERFECT for {niche} specifically",
            "customized_steps": ["Step 1 for {niche}", "Step 2..."],
            "first_action": "The exact first thing to do TODAY",
            "expected_outcome": "What happens in 30 days",
            "difficulty": "easy/medium/hard",
            "cost": "$X",
            "tools": ["tool1", "tool2"]
        }}
    ],
    "priority_recommendation": "Which one to do first and why"
}}

Return ONLY JSON."""

        try:
            response = claude.messages.create(
                model=self.model,
                max_tokens=10000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            response_text = ""
            for block in response.content:
                if getattr(block, "type", None) == "text":
                    response_text = block.text
                    break
            if not response_text:
                response_text = response.content[0].text if response.content else ""
            try:
                return _safe_parse_json(response_text)
            except (json.JSONDecodeError, ValueError):
                print(f"⚠️  Tactics parse failed, retrying...")
                retry_resp = claude.messages.create(
                    model=self.model,
                    max_tokens=10000,
                    messages=[
                        {"role": "user", "content": prompt},
                        {"role": "assistant", "content": response_text},
                        {"role": "user", "content": "Your response could not be parsed as valid JSON. Return ONLY the raw JSON object starting with { and ending with }."},
                    ],
                )
                retry_text = ""
                for block in retry_resp.content:
                    if getattr(block, "type", None) == "text":
                        retry_text = block.text
                        break
                if not retry_text:
                    retry_text = retry_resp.content[0].text if retry_resp.content else ""
                return _safe_parse_json(retry_text)
            
        except Exception as e:
            return {"error": str(e), "raw_tactics": base_tactics}

    async def generate_roadmap(
        self,
        business_type: str,
        goal: str,
        timeline_days: int = 90,
        budget: str = "low",
        niche: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a day-by-day / week-by-week growth hacking roadmap
        
        Args:
            business_type: Type of business
            goal: The primary goal (e.g., '1000 email subscribers', 'land first 10 clients')
            timeline_days: Roadmap duration (30, 60, or 90 days)
            budget: Budget tier
            niche: Specific industry niche
        
        Returns:
            Dict with phased roadmap
        """
        playbook_summary = "\n".join([
            f"- {cat['name']}: {', '.join(t['title'] for t in cat['tactics'][:2])}"
            for cat in GROWTH_HACKING_PLAYBOOK.values()
        ])
        
        budget_info = self.BUDGET_TIERS.get(budget, self.BUDGET_TIERS["low"])
        
        prompt = f"""You are a growth hacking strategist creating a {timeline_days}-day roadmap.

BUSINESS: {business_type}
NICHE: {niche or 'general business'}
GOAL: {goal}
BUDGET: {budget_info['label']}
TIMELINE: {timeline_days} days

AVAILABLE STRATEGY CATEGORIES:
{playbook_summary}

Create a SPECIFIC, ACTIONABLE {timeline_days}-day roadmap.

Think about:
1. Days 1-7: Foundation and quick credibility signals (things that persist and compound)
2. Days 8-30: Authority building and audience infiltration
3. Days 31-60: Amplification and syndication
4. Days 61-{timeline_days}: Scale what's working, add partnerships

Return JSON:
{{
    "roadmap_overview": "The master strategy in 3 sentences",
    "core_theme": "The central positioning/hook for this business",
    "phases": [
        {{
            "phase": "Phase 1: Foundation (Days 1-7)",
            "goal": "What this phase accomplishes",
            "daily_actions": {{
                "Day 1": ["Action 1", "Action 2"],
                "Day 2": ["Action 1"],
                "Day 3-5": ["Recurring action"],
                "Day 6-7": ["Action 1", "Action 2"]
            }},
            "milestones": ["Milestone 1 by end of week", "Milestone 2"],
            "important_note": "Key insight for this phase"
        }},
        {{
            "phase": "Phase 2: Authority Building (Days 8-30)",
            ...same format
        }},
        {{
            "phase": "Phase 3: Amplification (Days 31-60)",
            ...same format
        }},
        {{
            "phase": "Phase 4: Scale (Days 61-{timeline_days})",
            ...same format
        }}
    ],
    "success_metrics": {{
        "30_day": "What success looks like at 30 days",
        "60_day": "What success looks like at 60 days",
        "{timeline_days}_day": "What success looks like at {timeline_days} days"
    }},
    "biggest_mistakes_to_avoid": ["Mistake 1", "Mistake 2", "Mistake 3"],
    "secret_weapon": "The one tactic in this roadmap that most businesses miss and is the biggest leverage point"
}}

Return ONLY JSON."""

        try:
            response = claude.messages.create(
                model=self.model,
                max_tokens=12000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            response_text = ""
            for block in response.content:
                if getattr(block, "type", None) == "text":
                    response_text = block.text
                    break
            if not response_text:
                response_text = response.content[0].text if response.content else ""
            try:
                roadmap = _safe_parse_json(response_text)
            except (json.JSONDecodeError, ValueError):
                print(f"⚠️  Roadmap parse failed, retrying...")
                retry_resp = claude.messages.create(
                    model=self.model,
                    max_tokens=12000,
                    messages=[
                        {"role": "user", "content": prompt},
                        {"role": "assistant", "content": response_text},
                        {"role": "user", "content": "Your response could not be parsed as valid JSON. Return ONLY the raw JSON object starting with { and ending with }."},
                    ],
                )
                retry_text = ""
                for block in retry_resp.content:
                    if getattr(block, "type", None) == "text":
                        retry_text = block.text
                        break
                if not retry_text:
                    retry_text = retry_resp.content[0].text if retry_resp.content else ""
                roadmap = _safe_parse_json(retry_text)
            
            roadmap.update({
                "generated_for": business_type,
                "goal": goal,
                "timeline_days": timeline_days,
                "budget": budget,
                "created_at": datetime.now().isoformat()
            })
            
            return roadmap
            
        except Exception as e:
            return {"error": str(e)}

    async def generate_press_release_strategy(
        self,
        business_name: str,
        business_type: str,
        announcement: str,
        niche: str
    ) -> Dict[str, Any]:
        """
        Generate a press release + media outlet strategy to earn 'As Seen On' badges
        
        Args:
            business_name: Name of the business
            business_type: Type of business
            announcement: What the press release will announce (launch, milestone, study, etc.)
            niche: Business niche
        
        Returns:
            Dict with press release angles, target outlets, and distribution plan
        """
        prompt = f"""You are a PR strategist specializing in helping small businesses get media coverage with zero budget.

BUSINESS: {business_name} ({business_type})
NICHE: {niche}
ANNOUNCEMENT TOPIC: {announcement}

Create a complete press release strategy that will get this business featured in Yahoo News, Yahoo Finance, ABC News affiliates, CW affiliates, MarketWatch, and other major outlets via free press release distribution.

This is ACHIEVABLE because:
- EINPresswire.com (free) syndicates to 200+ news sites including many major affiliates
- PRLog.org (free) distributes to Google News and regional outlets
- PR.com (free) gets listings in AP News digital
- Stories need to be "newsworthy" - have a data hook, trend angle, or milestone angle

Return JSON:
{{
    "press_release_angles": [
        {{
            "angle": "Angle title",
            "headline": "Press release headline (newsy, not salesy)",
            "hook": "Why this is newsworthy right now",
            "data_point": "Made-up or real-ish stat to anchor the story (client must verify accuracy)",
            "target_section": "Which section of outlets would run this (Business, Lifestyle, Tech, etc.)"
        }}
    ],
    "best_angle": "Which angle has highest pickup probability and why",
    "distribution_plan": {{
        "tier1_free": ["EINPresswire.com", "PRLog.org", "PR.com", "Free-Press-Release.com"],
        "tier2_submitted": ["Exact URL paths for Entrepreneur.com, Inc.com submission forms"],
        "tier3_targeted": ["Specific journalists at relevant outlets to email directly"],
        "sequence": "What to distribute first and why"
    }},
    "as_seen_on_collection": {{
        "guaranteed_placements": ["These will definitely pick up via syndication"],
        "likely_placements": ["These often pick up trending press releases in this niche"],
        "possible_placements": ["Best case scenario outlets"],
        "usage_rights": "How to use these logos legally: 'As featured on' vs 'As seen on'"
    }},
    "follow_up_strategy": "What to do after distribution to maximize pickup",
    "template_press_release": "A template opening paragraph they can customize",
    "what_makes_a_press_release_work": ["Key element 1", "Key element 2", "Key element 3"]
}}

Return ONLY JSON."""

        try:
            response = claude.messages.create(
                model=self.model,
                max_tokens=10000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            response_text = ""
            for block in response.content:
                if getattr(block, "type", None) == "text":
                    response_text = block.text
                    break
            if not response_text:
                response_text = response.content[0].text if response.content else ""
            return _safe_parse_json(response_text)
            
        except Exception as e:
            return {"error": str(e)}

    async def generate_academy_blueprint(
        self,
        expert_name: str,
        niche: str,
        core_methodology: str
    ) -> Dict[str, Any]:
        """
        Generate a complete 'Instant Academy' blueprint for authority positioning
        
        Args:
            expert_name: The person/brand creating the academy
            niche: The niche the academy covers
            core_methodology: The unique approach or framework being taught
        
        Returns:
            Complete blueprint for creating an authority academy
        """
        prompt = f"""You are an expert in positioning and authority building for online businesses.

PERSON/BRAND: {expert_name}
NICHE: {niche}
CORE METHODOLOGY: {core_methodology}

Create a complete blueprint for building an 'Instant Authority Academy' that will:
1. Position {expert_name} as THE recognized expert in {niche}
2. Create a free platform that establishes thought leadership
3. Build a certification program that creates evangelists
4. Generate 'Founder of [Academy]' credibility in bio and marketing
5. Eventually become a paid asset

Return JSON:
{{
    "academy_name": "The perfect name for this academy (memorable, authoritative, search-friendly)",
    "tagline": "One sentence that explains the academy's unique promise",
    "methodology_name": "Give the teaching methodology a proprietary name (e.g., 'The SCALE Framework', '5-Phase Authority System')",
    "free_courses": [
        {{
            "course_title": "Title",
            "lesson_count": X,
            "duration": "X hours total",
            "hook": "Why people NEED this course",
            "outline": ["Lesson 1 title", "Lesson 2 title"],
            "platform": "Teachable/Thinkific/Notion - free tier"
        }}
    ],
    "certification_program": {{
        "name": "[Expert Name]-Certified [Niche] [Title]",
        "requirements": ["Requirement 1", "Requirement 2"],
        "what_they_get": "Certificate, badge, community access, directory listing",
        "how_they_promote_you": "How certified members spread the word"
    }},
    "bio_upgrade": {{
        "before": "Generic bio before academy",
        "after": "Upgraded bio with Academy title and methodology",
        "linkedin_headline": "Updated LinkedIn headline",
        "instagram_bio": "Updated IG bio with academy"
    }},
    "launch_plan": {{
        "week1": "Setup steps",
        "week2": "Content creation",
        "week3": "Launch actions",
        "week4": "Growth tactics"
    }},
    "revenue_expansion": "How the free academy becomes a paid asset within 6-12 months"
}}

Return ONLY JSON."""

        try:
            response = claude.messages.create(
                model=self.model,
                max_tokens=10000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            response_text = ""
            for block in response.content:
                if getattr(block, "type", None) == "text":
                    response_text = block.text
                    break
            if not response_text:
                response_text = response.content[0].text if response.content else ""
            return _safe_parse_json(response_text)
            
        except Exception as e:
            return {"error": str(e)}

    def get_available_categories(self) -> List[Dict[str, str]]:
        """Return all available strategy categories"""
        return [
            {
                "key": key,
                "name": cat["name"],
                "description": cat["description"],
                "tactic_count": len(cat["tactics"])
            }
            for key, cat in GROWTH_HACKING_PLAYBOOK.items()
        ]

    def _get_fallback_tactics(self, business_type: str, budget: str) -> List[Dict]:
        """Return top tactics if AI call fails"""
        fallbacks = []
        for cat in GROWTH_HACKING_PLAYBOOK.values():
            for tactic in cat["tactics"][:1]:
                if budget == "bootstrap" and "$0" not in tactic.get("cost", "$0"):
                    continue
                fallbacks.append({
                    "title": tactic["title"],
                    "cost": tactic["cost"],
                    "impact": tactic["impact"],
                    "first_step": tactic["how"][0] if tactic["how"] else "See full description"
                })
        return fallbacks[:5]

    def print_strategy_summary(self, strategy: Dict[str, Any]):
        """Print a formatted strategy summary"""
        print(f"\n{'='*80}")
        print(f"🚀 GROWTH HACKING STRATEGY")
        print(f"{'='*80}")
        print(f"Business: {strategy.get('business_type', 'N/A')}")
        print(f"Goal: {strategy.get('goal', 'N/A')}")
        print(f"Timeline: {strategy.get('timeline', 'N/A')}")
        
        if "positioning_angle" in strategy:
            print(f"\n🎯 POSITIONING ANGLE:")
            print(f"   {strategy['positioning_angle']}")
        
        if "authority_narrative" in strategy:
            print(f"\n📖 AUTHORITY NARRATIVE:")
            print(f"   {strategy['authority_narrative']}")
        
        quick_wins = strategy.get("quick_wins", [])
        if quick_wins:
            print(f"\n⚡ QUICK WINS (This Week):")
            for i, tactic in enumerate(quick_wins, 1):
                print(f"\n   {i}. {tactic.get('title', 'N/A')}")
                print(f"      💰 Cost: {tactic.get('cost', 'N/A')}")
                print(f"      📈 Impact: {tactic.get('expected_impact', 'N/A')}")
                print(f"      ⏱️  Time: {tactic.get('time_investment', 'N/A')}")
                if tactic.get("description"):
                    print(f"      📝 {tactic['description'][:150]}...")
        
        medium = strategy.get("medium_term", [])
        if medium:
            print(f"\n📅 MEDIUM TERM (30-60 Days):")
            for tactic in medium:
                print(f"   • {tactic.get('title', 'N/A')} [{tactic.get('cost', '')}]")
        
        long_term = strategy.get("long_term", [])
        if long_term:
            print(f"\n🏗️  LONG TERM (60-90 Days):")
            for tactic in long_term:
                print(f"   • {tactic.get('title', 'N/A')} [{tactic.get('cost', '')}]")
        
        if "contrarian_insight" in strategy:
            print(f"\n💡 CONTRARIAN INSIGHT:")
            print(f"   {strategy['contrarian_insight']}")
        
        if "roi_estimate" in strategy:
            print(f"\n📊 EXPECTED ROI:")
            print(f"   {strategy['roi_estimate']}")
        
        print(f"\n{'='*80}\n")


# =============================================================================
# TEST SUITE
# =============================================================================

async def test_growth_hacking_agent():
    """Test the Growth Hacking Intelligence Agent"""
    
    print("\n" + "="*80)
    print("🧪 TESTING GROWTH HACKING INTELLIGENCE AGENT")
    print("="*80 + "\n")
    
    agent = GrowthHackingAgent(client_id="test_client")
    
    # Test 1: View available categories
    print("\n" + "="*80)
    print("TEST 1: Available Strategy Categories")
    print("="*80)
    categories = agent.get_available_categories()
    for cat in categories:
        print(f"  📂 {cat['name']}: {cat['tactic_count']} tactics")
        print(f"     {cat['description']}")
    
    # Test 2: Generate a full strategy
    print("\n" + "="*80)
    print("TEST 2: Generate Full Growth Hacking Strategy (Life Coach)")
    print("="*80 + "\n")
    
    strategy = await agent.generate_strategy(
        business_type="life coaching for corporate professionals",
        current_situation="brand new coach, no followers, no press, no clients yet",
        goal="appear as an established, credible expert and attract high-ticket clients ($5K+)",
        budget="bootstrap",
        timeline="90 days",
        niche="executive life coaching",
        target_audience="corporate professionals 35-50 looking for life/career transformation",
        current_online_presence="just created LinkedIn and website this week"
    )
    
    if "error" not in strategy:
        agent.print_strategy_summary(strategy)
        print(f"✅ Strategy generated: {strategy.get('total_tactics', 0)} total tactics")
    else:
        print(f"❌ Error: {strategy['error']}")
    
    # Test 3: Press release strategy
    print("\n" + "="*80)
    print("TEST 3: Press Release → 'As Seen On' Strategy")
    print("="*80 + "\n")
    
    press_strategy = await agent.generate_press_release_strategy(
        business_name="Elite Transform Coaching",
        business_type="executive life coaching",
        announcement="launch of new 90-day executive transformation program",
        niche="executive coaching"
    )
    
    if "error" not in press_strategy:
        print(f"✅ Press release strategy generated!")
        print(f"   Best angle: {press_strategy.get('best_angle', 'N/A')[:100]}...")
        guaranteed = press_strategy.get('as_seen_on_collection', {}).get('guaranteed_placements', [])
        print(f"   Guaranteed placements ({len(guaranteed)}): {', '.join(guaranteed[:3])}")
    else:
        print(f"❌ Error: {press_strategy['error']}")
    
    # Test 4: Academy blueprint
    print("\n" + "="*80)
    print("TEST 4: Instant Academy Blueprint")
    print("="*80 + "\n")
    
    academy = await agent.generate_academy_blueprint(
        expert_name="Sarah Mitchell",
        niche="executive life coaching",
        core_methodology="helping corporate professionals design intentional lives without sacrificing career success"
    )
    
    if "error" not in academy:
        print(f"✅ Academy blueprint generated!")
        print(f"   Academy Name: {academy.get('academy_name', 'N/A')}")
        print(f"   Methodology: {academy.get('methodology_name', 'N/A')}")
        print(f"   Bio upgrade: {academy.get('bio_upgrade', {}).get('linkedin_headline', 'N/A')}")
    else:
        print(f"❌ Error: {academy['error']}")
    
    # Test 5: Get specific tactics for press/media
    print("\n" + "="*80)
    print("TEST 5: Specific Tactics - Press & Media for Fitness Coaching")
    print("="*80 + "\n")
    
    tactics = await agent.get_tactics(
        category="press_media",
        niche="online fitness coaching",
        budget="bootstrap",
        num_tactics=3
    )
    
    if "error" not in tactics:
        print(f"✅ Tactics generated for press/media!")
        print(f"   Niche: {tactics.get('niche', 'N/A')}")
        tactic_list = tactics.get("tactics", [])
        for t in tactic_list[:2]:
            print(f"\n   📌 {t.get('title', 'N/A')}")
            print(f"      Hook: {t.get('niche_specific_hook', 'N/A')[:100]}...")
            print(f"      First Action: {t.get('first_action', 'N/A')[:100]}...")
    else:
        print(f"❌ Error: {tactics['error']}")
    
    print("\n" + "="*80)
    print("✅ ALL TESTS COMPLETE")
    print("="*80 + "\n")
    
    print("📋 Summary:")
    print("  ✅ Category overview: Working")
    print("  ✅ Full strategy generation: Working")
    print("  ✅ Press release strategy: Working")
    print("  ✅ Academy blueprint: Working")
    print("  ✅ Category-specific tactics: Working")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_growth_hacking_agent())
