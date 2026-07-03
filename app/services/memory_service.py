"""
Memory Service

Manages conversation history in Redis.
Stores messages as JSON strings and enforces a TTL so old sessions expire.
"""
import json
import structlog
from app.db.redis_client import get_redis_client
from app.llm.base import LLMMessage
from app.config.settings import get_settings

logger = structlog.get_logger()


class MemoryService:
    """Handles loading and saving conversation history."""
    
    def __init__(self):
        self.redis = get_redis_client()
        self.settings = get_settings()
    
    def _get_key(self, session_id: str) -> str:
        return f"chat_history:{session_id}"
    
    async def get_history(self, session_id: str) -> list[LLMMessage]:
        """Load conversation history for a session."""
        key = self._get_key(session_id)
        data = await self.redis.lrange(key, 0, -1)
        
        messages = []
        for item in data:
            msg_dict = json.loads(item)
            messages.append(LLMMessage(**msg_dict))
            
        return messages
    
    async def save_turn(self, session_id: str, user_msg: str, assistant_msg: str) -> None:
        """Save a user query and assistant response to history."""
        key = self._get_key(session_id)
        
        user_msg_obj = LLMMessage(role="user", content=user_msg).model_dump()
        assistant_msg_obj = LLMMessage(role="assistant", content=assistant_msg).model_dump()
        
        # Push to Redis list
        await self.redis.rpush(key, json.dumps(user_msg_obj))
        await self.redis.rpush(key, json.dumps(assistant_msg_obj))
        
        # Trim list to last 10 messages (5 turns) to save memory
        await self.redis.ltrim(key, -10, -1)
        
        # Set TTL so history expires if unused
        await self.redis.expire(key, self.settings.session_ttl_seconds)