"""
Conversation Memory System
- Platform-compliant memory for DM conversations
- Short-term, session-based storage with automatic expiry
- User consent tracking and data minimization
- GDPR and platform policy compliant

COMPLIANCE NOTES:
- Only stores messages for active conversations (last 24 hours by default)
- Automatically expires and deletes old conversations
- Requires user consent before storing any data
- Minimal data retention: only what's needed for context
- No sharing or external processing without explicit consent
"""

import os
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from dataclasses import dataclass, asdict
import json


@dataclass
class Message:
    """Represents a single message in a conversation"""
    sender: str  # 'user' or 'agent'
    text: str
    timestamp: datetime
    
    def to_dict(self):
        return {
            'sender': self.sender,
            'text': self.text,
            'timestamp': self.timestamp.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            sender=data['sender'],
            text=data['text'],
            timestamp=datetime.fromisoformat(data['timestamp'])
        )


@dataclass
class ConversationSession:
    """Represents a conversation session with memory"""
    thread_id: str
    user_id: str
    messages: List[Message]
    consent_given: bool
    created_at: datetime
    last_activity: datetime
    expires_at: datetime
    
    def to_dict(self):
        return {
            'thread_id': self.thread_id,
            'user_id': self.user_id,
            'messages': [m.to_dict() for m in self.messages],
            'consent_given': self.consent_given,
            'created_at': self.created_at.isoformat(),
            'last_activity': self.last_activity.isoformat(),
            'expires_at': self.expires_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            thread_id=data['thread_id'],
            user_id=data['user_id'],
            messages=[Message.from_dict(m) for m in data['messages']],
            consent_given=data['consent_given'],
            created_at=datetime.fromisoformat(data['created_at']),
            last_activity=datetime.fromisoformat(data['last_activity']),
            expires_at=datetime.fromisoformat(data['expires_at'])
        )


class ConversationMemory:
    """
    Manages conversation memory for DM threads.
    
    Key Features:
    - Session-based storage (in-memory with optional persistence)
    - Automatic expiry after TTL (default: 24 hours)
    - User consent tracking
    - Data minimization (only recent messages)
    - Platform-compliant cleanup
    """
    
    def __init__(self, ttl_hours: int = 24, max_messages: int = 20):
        """
        Initialize conversation memory.
        
        Args:
            ttl_hours: Time-to-live for conversation sessions (default: 24 hours)
            max_messages: Maximum messages to retain per session (default: 20)
        """
        self.ttl_hours = ttl_hours
        self.max_messages = max_messages
        self.sessions: Dict[str, ConversationSession] = {}
    
    def add_message(self, thread_id: str, user_id: str, sender: str, text: str, 
                   consent_given: bool = False) -> None:
        """
        Add a message to conversation memory.
        
        Args:
            thread_id: Unique identifier for the conversation thread
            user_id: User's platform ID
            sender: 'user' or 'agent'
            text: Message content
            consent_given: Whether user has consented to memory storage
        """
        now = datetime.utcnow()
        
        # Get or create session
        if thread_id not in self.sessions:
            self.sessions[thread_id] = ConversationSession(
                thread_id=thread_id,
                user_id=user_id,
                messages=[],
                consent_given=consent_given,
                created_at=now,
                last_activity=now,
                expires_at=now + timedelta(hours=self.ttl_hours)
            )
        
        session = self.sessions[thread_id]
        
        # Update consent if provided
        if consent_given:
            session.consent_given = True
        
        # Only store if consent is given
        if not session.consent_given:
            return
        
        # Add message
        message = Message(sender=sender, text=text, timestamp=now)
        session.messages.append(message)
        
        # Limit message count (data minimization)
        if len(session.messages) > self.max_messages:
            session.messages = session.messages[-self.max_messages:]
        
        # Update activity timestamp
        session.last_activity = now
        session.expires_at = now + timedelta(hours=self.ttl_hours)
    
    def get_conversation_context(self, thread_id: str, max_messages: Optional[int] = None) -> List[Message]:
        """
        Retrieve conversation history for context.
        
        Args:
            thread_id: Conversation thread ID
            max_messages: Max messages to return (defaults to self.max_messages)
        
        Returns:
            List of recent messages (empty if no consent or expired)
        """
        # Clean up expired sessions first
        self.cleanup_expired()
        
        if thread_id not in self.sessions:
            return []
        
        session = self.sessions[thread_id]
        
        # Only return if consent given and not expired
        if not session.consent_given or datetime.utcnow() > session.expires_at:
            return []
        
        messages = session.messages
        if max_messages:
            messages = messages[-max_messages:]
        
        return messages
    
    def format_context_for_prompt(self, thread_id: str, max_messages: Optional[int] = None) -> str:
        """
        Format conversation history as a prompt-ready string.
        
        Args:
            thread_id: Conversation thread ID
            max_messages: Max messages to include
        
        Returns:
            Formatted conversation history string
        """
        messages = self.get_conversation_context(thread_id, max_messages)
        
        if not messages:
            return "No previous conversation context available."
        
        formatted = "Recent conversation history:\n\n"
        for msg in messages:
            formatted += f"{msg.sender.upper()}: {msg.text}\n"
        
        return formatted.strip()
    
    def cleanup_expired(self) -> int:
        """
        Remove expired conversation sessions.
        
        Returns:
            Number of sessions cleaned up
        """
        now = datetime.utcnow()
        expired = [tid for tid, session in self.sessions.items() 
                  if now > session.expires_at]
        
        for tid in expired:
            del self.sessions[tid]
        
        return len(expired)
    
    def revoke_consent(self, thread_id: str) -> None:
        """
        Revoke consent and delete conversation data for a thread.
        
        Args:
            thread_id: Thread to delete
        """
        if thread_id in self.sessions:
            del self.sessions[thread_id]
    
    def get_stats(self) -> dict:
        """Get memory statistics (for monitoring/debugging)"""
        active_sessions = len(self.sessions)
        total_messages = sum(len(s.messages) for s in self.sessions.values())
        consented_sessions = sum(1 for s in self.sessions.values() if s.consent_given)
        
        return {
            'active_sessions': active_sessions,
            'total_messages': total_messages,
            'consented_sessions': consented_sessions,
            'ttl_hours': self.ttl_hours,
            'max_messages': self.max_messages
        }


# Global instance (in-memory)
# For production, consider Redis or database backend
conversation_memory = ConversationMemory(ttl_hours=24, max_messages=20)


# Example usage and testing
if __name__ == "__main__":
    memory = ConversationMemory(ttl_hours=24, max_messages=10)
    
    # Simulate a conversation
    thread_id = "thread_123"
    user_id = "user_456"
    
    # User sends first message (no consent yet)
    memory.add_message(thread_id, user_id, "user", "Hi, can you help me?", consent_given=False)
    print("Without consent:", memory.get_conversation_context(thread_id))
    
    # User gives consent
    memory.add_message(thread_id, user_id, "user", "Yes, I agree to use memory", consent_given=True)
    memory.add_message(thread_id, user_id, "agent", "Great! How can I help you today?")
    memory.add_message(thread_id, user_id, "user", "I need help with my social media posts")
    memory.add_message(thread_id, user_id, "agent", "I can help with that. What platform?")
    
    # Get context
    context = memory.format_context_for_prompt(thread_id)
    print("\nFormatted context:\n", context)
    
    # Stats
    print("\nMemory stats:", memory.get_stats())
    
    # Cleanup
    print(f"\nCleaned up {memory.cleanup_expired()} expired sessions")
