"""
File Reading Utilities
Shared functions for extracting text from PDF, DOCX, TXT, and JSON files.
Used by both ingest.py and engagement_agent.py.
"""
import json
from pathlib import Path
from pypdf import PdfReader
from docx import Document


def extract_pdf_text(file_path: str) -> str:
    """Extract text from PDF file with robust error handling."""
    try:
        reader = PdfReader(file_path)
        text = ""
        
        for page_num, page in enumerate(reader.pages):
            try:
                page_text = page.extract_text()
                text += page_text + "\n"
            except Exception as page_error:
                print(f"⚠️  Could not read page {page_num + 1} of {Path(file_path).name}: {page_error}")
                continue
        
        return text.strip()
    except Exception as e:
        print(f"⚠️  Could not read file {Path(file_path).name}: {e}")
        return ""


def extract_docx_text(file_path: str) -> str:
    """Extract text from DOCX file."""
    try:
        doc = Document(file_path)
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        return text.strip()
    except Exception as e:
        print(f"❌ Error reading DOCX {file_path}: {e}")
        return ""


def extract_txt_text(file_path: str) -> str:
    """Extract text from TXT file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception as e:
        print(f"❌ Error reading TXT {file_path}: {e}")
        return ""


def extract_markdown_text(file_path: str) -> str:
    """
    Extract clean plain text from a Markdown (.md / .markdown) file.
    Strips all formatting tokens so the RAG index sees pure prose.
    """
    import re
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Fenced code blocks → keep inner content so code stays searchable
        content = re.sub(r'```[\w]*\n?([\s\S]*?)```', r'\1', content)
        # Inline code
        content = re.sub(r'`([^`]+)`', r'\1', content)
        # Headers (# ## ###…) → plain text
        content = re.sub(r'^#{1,6}\s+', '', content, flags=re.MULTILINE)
        # Bold / italic  (**text** / *text* / __text__ / _text_)
        content = re.sub(r'\*{1,3}([^*\n]+)\*{1,3}', r'\1', content)
        content = re.sub(r'_{1,3}([^_\n]+)_{1,3}', r'\1', content)
        # Images: ![alt](url)
        content = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', content)
        # Links: [text](url) → text
        content = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', content)
        # Blockquote markers
        content = re.sub(r'^>\s*', '', content, flags=re.MULTILINE)
        # Unordered list bullets
        content = re.sub(r'^[\-*+]\s+', '', content, flags=re.MULTILINE)
        # Ordered list numbers
        content = re.sub(r'^\d+\.\s+', '', content, flags=re.MULTILINE)
        # Horizontal rules
        content = re.sub(r'^[-*_]{3,}\s*$', '', content, flags=re.MULTILINE)
        # HTML tags that sometimes appear in MD
        content = re.sub(r'<[^>]+>', '', content)
        # Collapse 3+ consecutive blank lines to two
        content = re.sub(r'\n{3,}', '\n\n', content)

        return content.strip()
    except Exception as e:
        print(f"❌ Error reading Markdown {file_path}: {e}")
        return ""


def extract_json_text(file_path: str) -> str:
    """
    Extract text from Facebook/Instagram JSON exports.
    
    Format A: Direct Messages (e.g., message_1.json)
        - Root is a Dictionary {}
        - Contains key "messages" which is a List []
        - Each item has "sender_name" and "content"
        - Format: [DM] Sender: Content
    
    Format B: Post Comments (e.g., post_comments_1.json)
        - Root is a List []
        - Each item contains "string_map_data"
        - Inside "string_map_data", look for "Comment" -> "value"
        - Format: [COMMENT] Me: {value}
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        output_lines = []

        # Format A: Direct Messages
        if isinstance(data, dict) and "messages" in data and isinstance(data["messages"], list):
            messages = data["messages"]
            # Facebook exports messages newest-first, reverse for chronological order
            for message in reversed(messages):
                sender = message.get("sender_name", "Unknown")
                content = message.get("content", "")
                
                # Skip system/meta messages
                if not content or not content.strip():
                    continue
                skip_phrases = [
                    "Liked a message", "liked a message",
                    "sent an attachment", "Sent an attachment",
                    "Reacted", "reacted",
                    "You sent an attachment",
                    "started a video chat",
                    "missed a video chat",
                    "started sharing video",
                    "stopped sharing video"
                ]
                if any(phrase in content for phrase in skip_phrases):
                    continue
                    
                output_lines.append(f"[DM] {sender}: {content}")

        # Format B: Post Comments
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and "string_map_data" in item:
                    smd = item["string_map_data"]
                    if isinstance(smd, dict) and "Comment" in smd:
                        comment_obj = smd["Comment"]
                        if isinstance(comment_obj, dict):
                            value = comment_obj.get("value", "")
                            if value and value.strip():
                                output_lines.append(f"[COMMENT] Me: {value}")

        if output_lines:
            print(f"✅ Extracted {len(output_lines)} entries from {Path(file_path).name}")
            return "\n".join(output_lines)
        else:
            print(f"⚠️  No extractable text found in {Path(file_path).name}")
            return ""

    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON format in {Path(file_path).name}: {e}")
        return ""
    except Exception as e:
        print(f"❌ Error reading JSON {Path(file_path).name}: {e}")
        return ""


def extract_text_from_file(file_path: str) -> str:
    """
    Extract text from a file based on its extension.
    Supports .pdf, .docx, .txt, and .json files.
    
    Args:
        file_path: Path to the file
        
    Returns:
        Extracted text as string, or empty string if extraction fails
    """
    file_path_obj = Path(file_path)
    extension = file_path_obj.suffix.lower()
    
    if extension == ".pdf":
        return extract_pdf_text(str(file_path))
    elif extension == ".docx":
        return extract_docx_text(str(file_path))
    elif extension == ".txt":
        return extract_txt_text(str(file_path))
    elif extension in (".md", ".markdown"):
        return extract_markdown_text(str(file_path))
    elif extension == ".json":
        return extract_json_text(str(file_path))
    else:
        print(f"⚠️  Unsupported file type: {extension}")
        return ""


def load_texts_from_folder(folder_path: str, supported_extensions: list = None) -> str:
    """
    Recursively load and concatenate text from all supported files in a folder and its subfolders.
    Strictly ignores media files and only processes text-based formats.
    
    Args:
        folder_path: Path to the folder containing files
        supported_extensions: List of file extensions to process (default: ['.pdf', '.docx', '.txt', '.json'])
    Returns:
        Concatenated text from all files, or empty string if folder doesn't exist
    """
    import os
    if supported_extensions is None:
        supported_extensions = ['.pdf', '.docx', '.txt', '.md', '.markdown', '.json']

    # Media types to skip
    media_exts = {'.jpg', '.jpeg', '.png', '.gif', '.mp4', '.mov', '.webp', '.heic', '.avi', '.mkv', '.wav', '.mp3', '.ogg', '.html', '.htm', '.zip', '.rar', '.7z', '.tar', '.gz'}

    folder = Path(folder_path)
    if not folder.exists():
        return ""

    all_text = []
    text_file_count = 0
    media_file_count = 0
    skipped_file_count = 0

    for root, dirs, files in os.walk(folder):
        for fname in files:
            ext = Path(fname).suffix.lower()
            fpath = os.path.join(root, fname)
            # Media blocker
            if ext in media_exts:
                media_file_count += 1
                continue
            # Only process supported text formats
            if ext in supported_extensions:
                # For .json, check if it's Format A or Format B
                if ext == '.json':
                    try:
                        with open(fpath, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        # Format A: Direct Messages (dict with "messages" list)
                        is_format_a = isinstance(data, dict) and "messages" in data and isinstance(data["messages"], list)
                        # Format B: Post Comments (list with "string_map_data")
                        is_format_b = isinstance(data, list) and any(
                            isinstance(item, dict) and "string_map_data" in item for item in data
                        )
                        # Only process if it matches Format A or Format B
                        if not (is_format_a or is_format_b):
                            skipped_file_count += 1
                            continue
                    except Exception:
                        skipped_file_count += 1
                        continue
                text = extract_text_from_file(str(fpath))
                if text:
                    all_text.append(f"\n--- From {Path(fpath).name} ---\n{text}")
                    text_file_count += 1
            else:
                skipped_file_count += 1

    print(f"\n📄 Found {text_file_count} text files. Skipped {media_file_count} media files. Skipped {skipped_file_count} other files.")
    return "\n".join(all_text) if all_text else ""
