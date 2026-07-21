"""
Conversational memory service using Redis for context-aware Q&A.

Supports:
- Session-based conversation history
- Context window management
- Chat history summarization
"""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from typing import Optional
import redis.asyncio as aioredis

logger = logging.getLogger("app.services.memory")

# Default settings
MAX_HISTORY_LENGTH = 20  # Max messages per session
CONTEXT_WINDOW_TOKENS = 4000  # Approximate token budget for context
SESSION_TTL_SECONDS = 3600 * 2  # 2 hour session timeout


class ConversationMessage:
    """A single message in conversation history"""
    def __init__(self, role: str, content: str, sources: Optional[list] = None):
        self.role = role  # user | assistant | system
        self.content = content
        self.sources = sources or []
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "sources": self.sources,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConversationMessage":
        return cls(
            role=data.get("role", "user"),
            content=data.get("content", ""),
            sources=data.get("sources", []),
        )


class ConversationMemory:
    """
    Manages conversation history for a session using Redis.

    Usage:
        memory = ConversationMemory(redis, session_id)
        memory.add_user_message("What is RAG?")
        memory.add_assistant_message("RAG is...", [source1, source2])
        context = await memory.get_context_window(max_messages=5)
    """

    def __init__(self, redis: aioredis.Redis, session_id: str):
        self.redis = redis
        self.session_id = session_id
        self._key = f"conv:{session_id}"

    async def add_message(self, role: str, content: str, sources: Optional[list] = None):
        """Add a message to the conversation history"""
        msg = ConversationMessage(role, content, sources)
        try:
            await self.redis.rpush(self._key, json.dumps(msg.to_dict()))
            await self.redis.ltrim(self._key, -MAX_HISTORY_LENGTH, -1)
            await self.redis.expire(self._key, SESSION_TTL_SECONDS)
        except Exception as e:
            logger.debug("Failed to save conversation: %s", e)

    async def add_user_message(self, content: str):
        await self.add_message("user", content)

    async def add_assistant_message(self, content: str, sources: Optional[list] = None):
        await self.add_message("assistant", content, sources)

    async def add_system_message(self, content: str):
        await self.add_message("system", content)

    async def get_history(self, max_messages: int = 10) -> list[ConversationMessage]:
        """Get recent conversation history"""
        try:
            raw = await self.redis.lrange(self._key, -max_messages, -1)
            messages = []
            for entry in raw:
                try:
                    msg = ConversationMessage.from_dict(json.loads(entry))
                    messages.append(msg)
                except (json.JSONDecodeError, KeyError):
                    pass
            return messages
        except Exception as e:
            logger.debug("Failed to load conversation: %s", e)
            return []

    async def get_context_window(self, max_messages: int = 6) -> str:
        """
        Build a context window string for LLM prompt.

        Includes the last N messages formatted for LLM context.
        """
        messages = await self.get_history(max_messages)
        if not messages:
            return ""

        lines = ["[Conversation History]"]
        for msg in messages:
            role_label = {"user": "User", "assistant": "Assistant", "system": "System"}.get(msg.role, msg.role)
            content = msg.content[:500]  # Truncate long messages
            lines.append(f"{role_label}: {content}")
        lines.append("")  # Separator before current query

        return "\n".join(lines)

    async def get_last_query(self) -> Optional[str]:
        """Get the last user query for follow-up detection"""
        messages = await self.get_history(max_messages=5)
        for msg in reversed(messages):
            if msg.role == "user":
                return msg.content
        return None

    async def clear(self):
        """Clear conversation history"""
        try:
            await self.redis.delete(self._key)
        except Exception:
            pass

    async def is_first_turn(self) -> bool:
        """Check if this is the first message in the conversation"""
        try:
            length = await self.redis.llen(self._key)
            return length <= 1
        except Exception:
            return True
