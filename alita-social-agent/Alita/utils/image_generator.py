from PIL import Image, ImageDraw, ImageFont
import os
import re

def generate_image(text, output_path, width=1080, height=1080):
    """
    Generate a professional-looking faceless image with text optimized for Instagram.
    Uses gradient background and better typography.
    """
    # Remove emojis from text (they don't render well in most fonts)
    emoji_pattern = re.compile("["
        u"\U0001F600-\U0001F64F"  # emoticons
        u"\U0001F300-\U0001F5FF"  # symbols & pictographs
        u"\U0001F680-\U0001F6FF"  # transport & map symbols
        u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
        u"\U00002500-\U00002BEF"  # chinese char
        u"\U00002702-\U000027B0"
        u"\U000024C2-\U0001F251"
        u"\U0001f926-\U0001f937"
        u"\U00010000-\U0010ffff"
        u"\u2640-\u2642" 
        u"\u2600-\u2B55"
        u"\u200d"
        u"\u23cf"
        u"\u23e9"
        u"\u231a"
        u"\ufe0f"  # dingbats
        u"\u3030"
        "]+", flags=re.UNICODE)
    text = emoji_pattern.sub(r'', text)
    
    # Create gradient background (dark blue to purple)
    img = Image.new('RGB', (width, height))
    draw = ImageDraw.Draw(img)
    
    # Create a gradient background
    for y in range(height):
        # Gradient from dark purple-blue to darker blue
        r = int(25 + (15 * y / height))
        g = int(25 + (20 * y / height))
        b = int(50 + (30 * y / height))
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    
    # Try to use better fonts, fallback to default
    try:
        # Try common Windows fonts
        main_font = ImageFont.truetype("arialbd.ttf", 56)  # Arial Bold
    except:
        try:
            main_font = ImageFont.truetype("arial.ttf", 56)
        except:
            main_font = ImageFont.load_default()
    
    # Truncate text intelligently - find last complete sentence within limit
    max_chars = 280  # Increased from 200
    if len(text) > max_chars:
        # Try to truncate at sentence boundary
        truncated = text[:max_chars]
        last_period = truncated.rfind('.')
        last_exclaim = truncated.rfind('!')
        last_question = truncated.rfind('?')
        last_sentence_end = max(last_period, last_exclaim, last_question)
        
        if last_sentence_end > 100:  # If we found a sentence within reasonable range
            truncated_text = text[:last_sentence_end + 1]
        else:
            # Truncate at last complete word
            last_space = truncated.rfind(' ')
            truncated_text = text[:last_space] + "..."
    else:
        truncated_text = text
    
    # Remove hashtags for cleaner image
    if '#' in truncated_text:
        truncated_text = truncated_text.split('#')[0].strip()
    
    # Wrap text with better width calculation
    chars_per_line = 28  # Optimized for readability
    lines = []
    words = truncated_text.split()
    current_line = ""
    
    for word in words:
        test_line = current_line + " " + word if current_line else word
        if len(test_line) <= chars_per_line:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
    
    # Limit to max lines to ensure it fits
    max_lines = 12
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:chars_per_line - 3] + "..."
    
    # Calculate total text height
    line_height = 70
    total_height = len(lines) * line_height
    
    # Add padding
    padding = 80
    y_text = (height - total_height) // 2
    
    # Draw text with shadow for better readability
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=main_font)
        w = bbox[2] - bbox[0]
        x = (width - w) // 2
        
        # Draw shadow
        draw.text((x + 3, y_text + 3), line, font=main_font, fill=(0, 0, 0, 128))
        # Draw main text
        draw.text((x, y_text), line, font=main_font, fill=(255, 255, 255))
        
        y_text += line_height
    
    # Create directory if it doesn't exist
    if os.path.dirname(output_path):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    img.save(output_path, quality=95)
    return output_path

# Example usage:
if __name__ == "__main__":
    sample_text = "Your AI-generated Instagram post goes here!"
    output_file = "temp/generated_post_image.jpg"
    generate_image(sample_text, output_file)
    print(f"Image saved to {output_file}")
