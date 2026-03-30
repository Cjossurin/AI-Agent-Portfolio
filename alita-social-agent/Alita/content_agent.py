"""
Content Creation Agent
- Generates social media posts, captions, emails, and more using RAG and style matching.
- For now, outputs are printed to the console for testing.
"""


import asyncio
import os
from dataclasses import dataclass
from typing import List, Optional
import httpx
from dotenv import load_dotenv
from prompt_templates import get_prompt_template

@dataclass
class ContentRequest:
    platform: str       # e.g., 'facebook', 'instagram', 'linkedin', 'twitter', 'tiktok', etc.
    content_type: str   # e.g., 'post', 'caption', 'story', 'reel', 'article', 'ad', etc.
    topic: str
    goal: str = 'views_engagement'  # e.g., 'views_engagement', 'follower_growth', 'conversions_sales'
    client_voice: Optional[str] = None  # Client's bio, style guide, tone settings
    rag_context: Optional[str] = None   # Retrieved facts/knowledge about the topic
    style_hint: Optional[str] = None    # Deprecated: Use client_voice instead
    batch_size: int = 1

@dataclass
class GeneratedContent:
    platform: str
    content: str
    style_used: Optional[str] = None
    topic: Optional[str] = None


class ContentCreationAgent:
    def __init__(self):
        load_dotenv()
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        self.model = os.getenv("CLAUDE_HAIKU_MODEL", "claude-haiku-4-5-20251001")
        self.api_url = "https://api.anthropic.com/v1/messages"

    async def generate_content(self, request: ContentRequest) -> List[GeneratedContent]:
        results = []
        async with httpx.AsyncClient(timeout=30) as client:
            for _ in range(request.batch_size):
                prompt = self._build_prompt(request)
                
                # === SCENE 2 SCREENCAST: AI/CLAUDE API CALL START ===
                headers = {
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                }
                data = {
                    "model": self.model,
                    "max_tokens": 512,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ]
                }
                try:
                    resp = await client.post(self.api_url, headers=headers, json=data)
                # === SCENE 2 SCREENCAST: AI/CLAUDE API CALL END ===
                    resp.raise_for_status()
                    content = resp.json()["content"][0]["text"].strip()
                    # === START META-COMMENTARY CLEANUP SECTION ===
                    # Clean up meta-commentary that Claude sometimes adds
                    content = self._clean_content(content)
                    # === STOP META-COMMENTARY CLEANUP SECTION ===
                    
                    # Clean up meta-commentary that Claude sometimes adds
                    content = self._clean_content(content)
                except Exception as e:
                    content = f"[ERROR] Claude API call failed: {e}"
                results.append(GeneratedContent(
                    platform=request.platform,
                    content=content,
                    style_used=request.style_hint,
                    topic=request.topic
                ))
        return results

    def _clean_content(self, content: str) -> str:
        """
        Remove meta-commentary and wrapper text that Claude sometimes adds.
        Examples: "Here's your Instagram post:", "Here's a draft:", etc.
        """
        import re
        
        # Remove common wrapper phrases at the start
        patterns = [
            r'^Here\'s (your |a |an |the )?.*?:\s*',
            r'^I\'ve (created|generated|written).*?:\s*',
            r'^(Sure|Absolutely|Of course)[,!].*?:\s*',
            r'^Below is.*?:\s*',
            r'^(Instagram|Facebook|LinkedIn|Twitter|TikTok) (post|caption|content):\s*',
        ]
        
        for pattern in patterns:
            content = re.sub(pattern, '', content, flags=re.IGNORECASE | re.MULTILINE)
        
        # Remove any leading/trailing quotes or backticks
        content = content.strip('`"\'')
        
        return content.strip()
        # === START META-COMMENTARY CLEANUP SECTION ===
        # Clean up meta-commentary that Claude sometimes adds
        # === STOP META-COMMENTARY CLEANUP SECTION ===

    def _build_prompt(self, request: ContentRequest) -> str:
        """
        Build the final prompt by:
        1. Loading the Master Prompt Template for the requested platform + content_type + goal
        2. Intelligently mapping our data to template placeholders
        3. Returning the complete prompt ready for the LLM
        """
        import re
        
        # Load the appropriate Master Prompt Template
        template = get_prompt_template(request.platform, request.content_type, request.goal)
        
        # Enhance the topic with goal-specific context if rag_context is missing
        if not request.rag_context:
            request.rag_context = f"Create compelling content about: {request.topic}. Focus on driving {request.goal.replace('_', ' ')}."
        
        # Extract all placeholders from the template (support both {$PLACEHOLDER} and {placeholder})
        placeholders = re.findall(r'\{\$?([A-Za-z_]+)\}', template)
        
        # Create a mapping of placeholder values
        values = {}
        for placeholder in placeholders:
            placeholder_lower = placeholder.lower()
            original_placeholder = placeholder  # Keep original case
            
            # Map common placeholders - try both with and without $ prefix
            value = None
            
            if 'topic' in placeholder_lower:
                value = request.topic
            # === SCENE 2 SCREENCAST: STYLE/BRAND VOICE CONFIGURATION START ===
            elif 'audience' in placeholder_lower or 'target' in placeholder_lower:
                value = request.client_voice or "General audience"
            elif 'brand' in placeholder_lower and 'voice' in placeholder_lower:
                value = request.client_voice or "Professional, friendly, authentic"
            elif 'context' in placeholder_lower or 'knowledge' in placeholder_lower or 'rag' in placeholder_lower:
                value = request.rag_context or request.topic
            elif 'voice' in placeholder_lower or 'style' in placeholder_lower or 'tone' in placeholder_lower:
                value = request.client_voice or "Professional, friendly tone"
            elif 'client' in placeholder_lower:
                value = request.client_voice or "Professional, friendly, authentic"
            # === SCENE 2 SCREENCAST: STYLE/BRAND VOICE CONFIGURATION END ===
            elif 'pain' in placeholder_lower or 'problem' in placeholder_lower:
                value = request.rag_context or "Common challenges in this area"
            elif 'product' in placeholder_lower or 'service' in placeholder_lower or 'solution' in placeholder_lower:
                value = request.rag_context or request.topic
            elif 'cta' in placeholder_lower or 'call_to_action' in placeholder_lower:
                value = "Learn more or get in touch"
            elif 'proof' in placeholder_lower or 'testimonial' in placeholder_lower:
                value = request.rag_context or "Proven results and client success"
            elif 'value' in placeholder_lower or 'benefit' in placeholder_lower:
                value = request.rag_context or request.topic
            else:
                # Default fallback
                value = request.rag_context or request.topic
            
            # Add both formats: {PLACEHOLDER}, {$PLACEHOLDER}, {placeholder}, {$placeholder}
            if value:
                values[original_placeholder] = value
                values[f'${original_placeholder}'] = value
                values[placeholder_lower] = value
                values[f'${placeholder_lower}'] = value
        
        # Replace all placeholders - handle both {PLACEHOLDER} and {$PLACEHOLDER} formats
        final_prompt = template
        
        # First pass: replace with $ prefix
        for placeholder in placeholders:
            if f'${placeholder}' in values:
                final_prompt = final_prompt.replace('{$' + placeholder + '}', values[f'${placeholder}'])
        
        # Second pass: replace without $ prefix
        for placeholder in placeholders:
            if placeholder in values:
                final_prompt = final_prompt.replace('{' + placeholder + '}', values[placeholder])
        
        # Simple reminder to output clean content (templates now have proper formatting instructions)
        final_prompt += """

**REMINDER:** Output ONLY the final content. No planning notes, no XML tags, no scratchpad. Ready to post immediately."""
        
        return final_prompt

# Simple test harness
async def main():
    agent = ContentCreationAgent()
    
    # Test multiple content_type + platform combinations
    test_requests = [
        ContentRequest(
            platform='instagram',
            content_type='reel',
            topic='AI for small business',
            goal='views_engagement',
            client_voice="Friendly, expert tone. Use simple language. Encourage questions. Add emojis sparingly.",
            rag_context="AI tools can automate tasks like email responses, social media scheduling, and customer support. Small businesses save 10+ hours/week on average.",
            batch_size=1
        ),
        ContentRequest(
            platform='linkedin',
            content_type='article',
            topic='The Future of AI in Marketing',
            goal='conversions_sales',
            client_voice="Professional, thought-leader tone. Data-driven. Industry insights.",
            rag_context="AI marketing tools increased conversion rates by 30% in 2025. Top use cases: personalization, predictive analytics, content generation.",
            batch_size=1
        ),
        ContentRequest(
            platform='twitter',
            content_type='thread',
            goal='follower_growth',
            topic='5 AI tools every entrepreneur needs',
            client_voice="Concise, actionable, helpful. Use bullet points. No fluff.",
            rag_context="Top AI tools: ChatGPT for writing, Midjourney for design, Zapier for automation, Claude for analysis, Grammarly for editing.",
            batch_size=1
        )
    ]
    
    print("Testing Master Prompt System with Content Type + Platform Matrix")
    print("="*70)
    
    for req in test_requests:
        posts = await agent.generate_content(req)
        for i, post in enumerate(posts, 1):
            print(f"\n[{req.platform.upper()}_{req.content_type.upper()}]")
            print(f"Topic: {req.topic}")
            print(f"Content:\n{post.content}")
            print("="*70)

if __name__ == "__main__":
    asyncio.run(main())
