"""
WhatsApp Business API Client
============================
Integration with WhatsApp Cloud API for business messaging.

FEATURES:
- Send template messages (business-initiated)
- Send/receive text messages
- Send media messages (images, videos, documents)
- Message template management
- Webhook event processing
- Business profile management

REQUIREMENTS:
- WhatsApp Business Account
- Phone number verified
- Message templates approved by Meta
- WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_ACCESS_TOKEN in .env
"""

import os
import httpx
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


@dataclass
class WhatsAppMessage:
    """Represents a WhatsApp message."""
    message_id: str
    from_number: str
    to_number: str
    message_type: str  # text, image, video, document, template
    content: str
    timestamp: datetime
    status: str = "sent"  # sent, delivered, read, failed


@dataclass
class MessageTemplate:
    """WhatsApp message template."""
    name: str
    language: str
    category: str  # UTILITY, MARKETING, AUTHENTICATION
    components: List[Dict[str, Any]]
    status: str = "PENDING"  # PENDING, APPROVED, REJECTED


class WhatsAppBusinessClient:
    """
    Client for WhatsApp Cloud API.
    
    Usage:
        client = WhatsAppBusinessClient()
        await client.send_text_message(to="1234567890", text="Hello!")
    """
    
    def __init__(
        self,
        phone_number_id: Optional[str] = None,
        access_token: Optional[str] = None,
        api_version: str = "v18.0"
    ):
        self.phone_number_id = phone_number_id or os.getenv("WHATSAPP_PHONE_NUMBER_ID")
        self.access_token = access_token or os.getenv("WHATSAPP_ACCESS_TOKEN")
        self.api_version = api_version
        self.base_url = f"https://graph.facebook.com/{api_version}"
        
        if not self.phone_number_id:
            raise ValueError("WHATSAPP_PHONE_NUMBER_ID not found in environment")
        if not self.access_token:
            raise ValueError("WHATSAPP_ACCESS_TOKEN not found in environment")
    
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with authentication."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
    
    # =========================================================================
    # SEND MESSAGES
    # =========================================================================
    
    async def send_text_message(
        self,
        to: str,
        text: str,
        preview_url: bool = False
    ) -> Dict[str, Any]:
        """
        Send a text message.
        
        Args:
            to: Recipient phone number (with country code, no +)
            text: Message text (up to 4096 characters)
            preview_url: Enable URL preview
        
        Returns:
            API response with message ID
        """
        endpoint = f"{self.base_url}/{self.phone_number_id}/messages"
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {
                "preview_url": preview_url,
                "body": text
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    endpoint,
                    headers=self._get_headers(),
                    json=payload
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            error_data = e.response.json() if e.response else {}
            return {
                "error": error_data.get("error", {}),
                "status_code": e.response.status_code
            }
        except Exception as e:
            return {"error": str(e)}
    
    async def send_template_message(
        self,
        to: str,
        template_name: str,
        language_code: str = "en",
        parameters: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Send a pre-approved template message.
        
        Templates are required for business-initiated conversations
        (when you message a user who hasn't messaged you in 24 hours).
        
        Args:
            to: Recipient phone number
            template_name: Name of approved template
            language_code: Language (e.g., "en", "es")
            parameters: List of parameter values for template placeholders
        
        Returns:
            API response
        """
        endpoint = f"{self.base_url}/{self.phone_number_id}/messages"
        
        # Build template component
        components = []
        if parameters:
            components.append({
                "type": "body",
                "parameters": [
                    {"type": "text", "text": param}
                    for param in parameters
                ]
            })
        
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
                "components": components
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    endpoint,
                    headers=self._get_headers(),
                    json=payload
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            error_data = e.response.json() if e.response else {}
            return {
                "error": error_data.get("error", {}),
                "status_code": e.response.status_code
            }
        except Exception as e:
            return {"error": str(e)}
    
    async def send_media_message(
        self,
        to: str,
        media_type: str,
        media_url: str,
        caption: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send an image, video, or document.
        
        Args:
            to: Recipient phone number
            media_type: "image", "video", or "document"
            media_url: Public URL of the media file
            caption: Optional caption
        
        Returns:
            API response
        """
        endpoint = f"{self.base_url}/{self.phone_number_id}/messages"
        
        media_object = {"link": media_url}
        if caption and media_type in ["image", "video"]:
            media_object["caption"] = caption
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": media_type,
            media_type: media_object
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    endpoint,
                    headers=self._get_headers(),
                    json=payload
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            error_data = e.response.json() if e.response else {}
            return {
                "error": error_data.get("error", {}),
                "status_code": e.response.status_code
            }
        except Exception as e:
            return {"error": str(e)}
    
    # =========================================================================
    # MESSAGE TEMPLATES
    # =========================================================================
    
    async def create_message_template(
        self,
        template: MessageTemplate
    ) -> Dict[str, Any]:
        """
        Create a new message template.
        Must be approved by Meta before use.
        
        Args:
            template: MessageTemplate object with all required fields
        
        Returns:
            API response with template ID
        """
        business_account_id = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID")
        if not business_account_id:
            return {"error": "WHATSAPP_BUSINESS_ACCOUNT_ID not configured"}
        
        endpoint = f"{self.base_url}/{business_account_id}/message_templates"
        
        payload = {
            "name": template.name,
            "language": template.language,
            "category": template.category,
            "components": template.components
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    endpoint,
                    headers=self._get_headers(),
                    json=payload
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            error_data = e.response.json() if e.response else {}
            return {
                "error": error_data.get("error", {}),
                "status_code": e.response.status_code
            }
        except Exception as e:
            return {"error": str(e)}
    
    async def get_message_templates(self) -> Dict[str, Any]:
        """
        Get all message templates for this business account.
        
        Returns:
            List of templates with their approval status
        """
        business_account_id = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID")
        if not business_account_id:
            return {"error": "WHATSAPP_BUSINESS_ACCOUNT_ID not configured"}
        
        endpoint = f"{self.base_url}/{business_account_id}/message_templates"
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    endpoint,
                    headers=self._get_headers()
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            return {"error": str(e)}
    
    # =========================================================================
    # BUSINESS PROFILE
    # =========================================================================
    
    async def get_business_profile(self) -> Dict[str, Any]:
        """Get WhatsApp Business profile information."""
        endpoint = f"{self.base_url}/{self.phone_number_id}/whatsapp_business_profile"
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    endpoint,
                    headers=self._get_headers(),
                    params={"fields": "about,address,description,email,profile_picture_url,websites,vertical"}
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            return {"error": str(e)}
    
    async def update_business_profile(
        self,
        about: Optional[str] = None,
        address: Optional[str] = None,
        description: Optional[str] = None,
        email: Optional[str] = None,
        vertical: Optional[str] = None,
        websites: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Update WhatsApp Business profile.
        
        Args:
            about: Business tagline (139 characters max)
            address: Business address
            description: Business description (256 characters max)
            email: Business email
            vertical: Industry category
            websites: List of website URLs
        
        Returns:
            API response
        """
        endpoint = f"{self.base_url}/{self.phone_number_id}/whatsapp_business_profile"
        
        payload = {
            "messaging_product": "whatsapp"
        }
        
        if about:
            payload["about"] = about
        if address:
            payload["address"] = address
        if description:
            payload["description"] = description
        if email:
            payload["email"] = email
        if vertical:
            payload["vertical"] = vertical
        if websites:
            payload["websites"] = websites
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    endpoint,
                    headers=self._get_headers(),
                    json=payload
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            return {"error": str(e)}
    
    # =========================================================================
    # WEBHOOK PROCESSING
    # =========================================================================
    
    def process_webhook_message(self, webhook_data: Dict[str, Any]) -> Optional[WhatsAppMessage]:
        """
        Process incoming webhook message.
        
        Args:
            webhook_data: Webhook payload from Meta
        
        Returns:
            WhatsAppMessage object or None if not a message event
        """
        try:
            entry = webhook_data.get("entry", [])[0]
            changes = entry.get("changes", [])[0]
            value = changes.get("value", {})
            
            # Check if it's a message event
            messages = value.get("messages", [])
            if not messages:
                return None
            
            message = messages[0]
            
            # Extract message data
            return WhatsAppMessage(
                message_id=message.get("id"),
                from_number=message.get("from"),
                to_number=value.get("metadata", {}).get("display_phone_number"),
                message_type=message.get("type"),
                content=message.get("text", {}).get("body", ""),
                timestamp=datetime.fromtimestamp(int(message.get("timestamp", 0))),
                status="received"
            )
        except Exception as e:
            print(f"Error processing webhook: {e}")
            return None


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def send_whatsapp_text(to: str, text: str) -> Dict[str, Any]:
    """Quick function to send a text message."""
    client = WhatsAppBusinessClient()
    return await client.send_text_message(to, text)


async def send_whatsapp_template(
    to: str,
    template_name: str,
    parameters: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Quick function to send a template message."""
    client = WhatsAppBusinessClient()
    return await client.send_template_message(to, template_name, parameters=parameters)


# =============================================================================
# EXAMPLE USAGE
# =============================================================================

async def example_usage():
    """Example of how to use the WhatsApp Business client."""
    
    # Initialize client
    client = WhatsAppBusinessClient()
    
    # Send a text message
    text_response = await client.send_text_message(
        to="1234567890",  # Replace with actual number (country code, no +)
        text="Hello from Alita AI! 👋"
    )
    print(f"Text message sent: {text_response}")
    
    # Send a template message
    template_response = await client.send_template_message(
        to="1234567890",
        template_name="welcome_message",
        parameters=["John", "https://example.com"]
    )
    print(f"Template sent: {template_response}")
    
    # Send an image
    image_response = await client.send_media_message(
        to="1234567890",
        media_type="image",
        media_url="https://example.com/image.jpg",
        caption="Check out our new product!"
    )
    print(f"Image sent: {image_response}")
    
    # Get business profile
    profile = await client.get_business_profile()
    print(f"Business profile: {profile}")
    
    # Get message templates
    templates = await client.get_message_templates()
    print(f"Templates: {templates}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_usage())
