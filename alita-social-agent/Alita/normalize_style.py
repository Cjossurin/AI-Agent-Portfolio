"""
Style Normalization Script
Converts messy chat logs into clean training data for style matching.

Usage:
1. Drop your raw chat logs (PDF, DOCX, TXT, JSON) into raw_style_inputs/
2. Run: python normalize_style.py
3. Find normalized output in style_references/demo_client/normalized_samples.txt

Supports:
- Facebook/Instagram chat exports (.json)
- PDF chat screenshots (.pdf)
- Word documents (.docx)
- Plain text files (.txt)
"""
import os
import sys
from pathlib import Path
from anthropic import Anthropic
from dotenv import load_dotenv

# Add utils to path
sys.path.append('utils')
from file_reader import load_texts_from_folder

load_dotenv()


def normalize_style_samples(raw_text: str, client: Anthropic, owner_name: str = "Prince Jossurin") -> str:
    """
    Use Claude to clean and format messy chat logs into training data.
    
    Args:
        raw_text: Raw chat log text
        client: Anthropic client instance
        owner_name: The name of the account owner (YOU) in the chat logs
        
    Returns:
        Normalized and formatted chat samples
    """
    system_prompt = f"""You are a precise Data Formatter for chat logs. Your task is to extract meaningful conversation exchanges.

CRITICAL RULES:
1. The OWNER (the person whose style we're learning) is: "{owner_name}"
2. Everyone else in the chat is the "Other Person"

DATA FORMAT:
- Lines starting with "[DM] {owner_name}:" are messages FROM the owner (these become "My Reply")
- Lines starting with "[DM] [Any Other Name]:" are messages from others (these become "Context")
- Lines starting with "[COMMENT] Me:" are comments FROM the owner (these become "My Reply")

YOUR TASK:
For each meaningful exchange, extract pairs where:
- "Context" = What the OTHER person said (the message that prompted a response)
- "My Reply" = What {owner_name} said in response

OUTPUT FORMAT (use exactly this format):
Context: [message from other person]
My Reply: [response from {owner_name}]

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

Extract AT LEAST 30-50 quality exchanges if available. Focus on the BEST examples that showcase {owner_name}'s unique communication style."""

    print(f"\n🤖 Sending to Claude for normalization (Owner: {owner_name})...")
    
    # Use Sonnet for high-quality data normalization
    model = os.getenv("CLAUDE_SONNET_MODEL", "claude-sonnet-4-5-20250929")
    
    response = client.messages.create(
        model=model,
        max_tokens=8000,
        messages=[{
            "role": "user",
            "content": f"{system_prompt}\n\n---RAW CHAT LOG START---\n{raw_text}\n---RAW CHAT LOG END---"
        }]
    )
    
    normalized_text = response.content[0].text
    print("✅ Normalization complete!")
    
    return normalized_text


def detect_owner_name(raw_text: str) -> str:
    """
    Try to detect the most frequent sender name in the DM data.
    Falls back to environment variable or default.
    """
    import re
    from collections import Counter
    
    # Find all sender names in [DM] format
    dm_pattern = r'\[DM\] ([^:]+):'
    names = re.findall(dm_pattern, raw_text)
    
    if names:
        # Count occurrences
        name_counts = Counter(names)
        # Get the most common names
        most_common = name_counts.most_common(5)
        print("\n📊 Detected senders in chat data:")
        for name, count in most_common:
            print(f"   - {name}: {count} messages")
        
        # Return the most frequent sender (likely the owner)
        return most_common[0][0]
    
    return None


def main():
    """Main execution function."""
    print("\n" + "="*60)
    print("📝 STYLE NORMALIZATION SCRIPT")
    print("="*60)
    
    # Initialize Anthropic client
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ Error: ANTHROPIC_API_KEY not found in .env")
        sys.exit(1)
    
    client = Anthropic(api_key=api_key)
    
    # Get owner name from env or use default
    owner_name = os.getenv("STYLE_OWNER_NAME", "Prince Jossurin")
    
    # Input folder
    input_folder = "raw_style_inputs"
    input_path = Path(input_folder)
    
    # Create input folder if it doesn't exist
    if not input_path.exists():
        print(f"📁 Creating {input_folder}/ folder...")
        input_path.mkdir(parents=True, exist_ok=True)
    
    print(f"\n📂 Reading files from {input_folder}/...")
    
    # Load all text from input folder
    raw_text = load_texts_from_folder(input_folder)
    
    if not raw_text or raw_text.strip() == "":
        print(f"\n❌ Error: No files found in {input_folder}/")
        print(f"💡 Add your chat logs to {input_folder}/ and run again:")
        print(f"   - Facebook/Instagram exports: message_1.json")
        print(f"   - PDF screenshots: chat_screenshots.pdf")
        print(f"   - Other formats: .docx, .txt")
        sys.exit(1)
    
    # Count files
    file_count = 0
    for ext in ['.pdf', '.docx', '.txt', '.json']:
        file_count += len(list(input_path.glob(f"*{ext}")))
    
    print(f"✅ Read {file_count} file(s)")
    print(f"📊 Total characters: {len(raw_text)}")
    
    # Try to auto-detect owner name from data
    detected_name = detect_owner_name(raw_text)
    if detected_name:
        print(f"\n🔍 Auto-detected owner: {detected_name}")
        # Ask for confirmation or use env var
        if os.getenv("STYLE_OWNER_NAME"):
            owner_name = os.getenv("STYLE_OWNER_NAME")
            print(f"📌 Using configured owner from .env: {owner_name}")
        else:
            owner_name = detected_name
            print(f"📌 Using detected owner: {owner_name}")
    else:
        print(f"\n📌 Using default owner: {owner_name}")
    
    # Normalize with Claude
    normalized_text = normalize_style_samples(raw_text, client, owner_name)
    
    # Output setup
    output_dir = Path("style_references") / "demo_client"
    output_file = output_dir / "normalized_samples.txt"
    
    # Create output directory if needed
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save normalized text
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(normalized_text)
    
    print("\n" + "="*60)
    print(f"✅ Read {file_count} file(s).")
    print(f"✅ Normalized style samples saved to {output_file}")
    print("="*60)
    print("\n💡 Next steps:")
    print("   1. Review the normalized samples")
    print("   2. Restart your bot: python webhook_receiver.py")
    print("   3. The bot will use these samples to match your style!\n")


if __name__ == "__main__":
    main()
