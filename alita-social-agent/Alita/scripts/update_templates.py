"""
Update prompt_templates.py with imported prompts from /prompts folder
"""
import os
import re
from import_prompts import import_all_prompts

def read_template_file() -> str:
    """Read current prompt_templates.py file"""
    with open("prompt_templates.py", "r", encoding="utf-8") as f:
        return f.read()

def update_template_content(file_content: str, platform: str, template_key: str, new_prompt: str) -> str:
    """Update a specific template placeholder with new prompt content"""
    
    # Build the section name (e.g., "facebook_post_views_engagement")
    full_template_key = f'"{template_key}"'
    
    # Find the template section for this platform
    platform_upper = platform.upper()
    platform_section_pattern = f"# =+ {platform_upper} TEMPLATES.*?={{"
    
    # Find the specific template within that section
    template_pattern = f'({full_template_key}:\\s*""")\n\\[PLACEHOLDER[^"]*"""'
    
    def replace_template(match):
        opening = match.group(1)
        # Clean and format the new prompt
        cleaned_prompt = new_prompt.strip()
        return f'{opening}\n{cleaned_prompt}\n"""'
    
    # Try to replace the template
    updated_content = re.sub(template_pattern, replace_template, file_content, flags=re.DOTALL)
    
    if updated_content != file_content:
        return updated_content
    else:
        print(f"⚠️  Template {platform}.{template_key} not found or already has content")
        return file_content

def update_all_templates():
    """Main function to update all templates"""
    
    # Import all prompts
    print("📥 Importing all prompt files...")
    imported_templates = import_all_prompts()
    
    if not imported_templates:
        print("❌ No templates imported!")
        return
    
    # Read current template file
    print("\n📖 Reading prompt_templates.py...")
    file_content = read_template_file()
    
    # Track updates
    updates_made = 0
    total_templates = 0
    
    # Update each template
    print("\n🔄 Updating templates...")
    
    for platform, templates in imported_templates.items():
        print(f"\n📝 Updating {platform.upper()} templates:")
        
        for template_key, prompt_content in templates.items():
            total_templates += 1
            
            old_content = file_content
            file_content = update_template_content(file_content, platform, template_key, prompt_content)
            
            if file_content != old_content:
                print(f"  ✅ Updated {template_key}")
                updates_made += 1
            else:
                print(f"  ⏭️  Skipped {template_key}")
    
    # Write updated file
    if updates_made > 0:
        print(f"\n💾 Writing updated prompt_templates.py...")
        with open("prompt_templates.py", "w", encoding="utf-8") as f:
            f.write(file_content)
        
        print(f"🎉 Successfully updated {updates_made}/{total_templates} templates!")
    else:
        print(f"\n🤷 No templates were updated (all may already have content)")
    
    print(f"\n📊 Final Summary:")
    print(f"   • Total prompt files: {sum(len(templates) for templates in imported_templates.values())}")
    print(f"   • Templates updated: {updates_made}")
    print(f"   • Templates skipped: {total_templates - updates_made}")

if __name__ == "__main__":
    update_all_templates()
