"""
Message Queue using Redis Streams
Lightweight alternative to Kafka for async document processing
"""
import json
import redis.asyncio as redis
from typing import Dict, Any, Optional, List
from datetime import datetime
import uuid


class RedisMessageQueue:
    """Redis Streams based message queue"""

    def __init__(self, redis_url: str = None):
        from app.config import settings
        self.redis_url = redis_url or settings.redis_url
        self._redis: Optional[redis.Redis] = None

    async def connect(self):
        """Connect to Redis"""
        if self._redis is None:
            self._redis = await redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )

    async def close(self):
        """Close Redis connection"""
        if self._redis:
            await self._redis.close()
            self._redis = None

    async def publish(self, stream: str, message: Dict[str, Any]) -> str:
        """
        Publish a message to a stream

        Args:
            stream: Stream name (e.g., 'documents:pending')
            message: Message data

        Returns:
            Message ID
        """
        await self.connect()

        # Add metadata
        message['_id'] = str(uuid.uuid4())
        message['_timestamp'] = datetime.utcnow().isoformat()

        # Serialize complex types
        serialized = {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v)
                      for k, v in message.items()}

        return await self._redis.xadd(stream, serialized)

    async def consume(
        self,
        stream: str,
        consumer_group: str,
        consumer_id: str,
        count: int = 10,
        block_ms: int = 5000
    ) -> List[Dict[str, Any]]:
        """
        Consume messages from a stream with consumer group

        Args:
            stream: Stream name
            consumer_group: Consumer group name
            consumer_id: Consumer ID
            count: Max messages to fetch
            block_ms: Block time in ms (0 = no block)

        Returns:
            List of messages
        """
        await self.connect()

        # Create consumer group if not exists
        try:
            await self._redis.xgroup_create(stream, consumer_group, id="0", mkstream=True)
        except redis.exceptions.ResponseError:
            pass  # Group already exists

        # Read messages
        messages = await self._redis.xreadgroup(
            groupname=consumer_group,
            consumername=consumer_id,
            streams={stream: ">"},
            count=count,
            block=block_ms
        )

        if not messages:
            return []

        result = []
        for stream_name, stream_messages in messages:
            for msg_id, fields in stream_messages:
                # Deserialize
                message = {}
                for k, v in fields.items():
                    if k.startswith('_'):
                        message[k] = v
                    else:
                        try:
                            message[k] = json.loads(v)
                        except (json.JSONDecodeError, TypeError):
                            message[k] = v
                message['_stream_id'] = msg_id
                result.append(message)

        return result

    async def acknowledge(self, stream: str, consumer_group: str, message_id: str):
        """Acknowledge message processing"""
        await self.connect()
        await self._redis.xack(stream, consumer_group, message_id)

    async def pending(
        self,
        stream: str,
        consumer_group: str
    ) -> Dict[str, Any]:
        """Get pending messages info"""
        await self.connect()

        info = await self._redis.xinfo_consumers(stream, consumer_group)
        pending = await self._redis.xpending_range(
            stream,
            consumer_group,
            min="-",
            max="+",
            count=100
        )

        return {
            "consumers": info,
            "pending": pending
        }

    async def claim(
        self,
        stream: str,
        consumer_group: str,
        consumer_id: str,
        min_idle_ms: int = 60000
    ) -> List[Dict[str, Any]]:
        """
        Claim stale messages from other consumers

        Args:
            stream: Stream name
            consumer_group: Consumer group
            consumer_id: Claiming consumer ID
            min_idle_ms: Minimum idle time to claim

        Returns:
            List of claimed messages
        """
        await self.connect()

        # Get pending message IDs
        pending = await self._redis.xpending_range(
            stream,
            consumer_group,
            min="-",
            max="+",
            count=100
        )

        claimed = []
        for msg in pending:
            if msg['time_since_delivered'] >= min_idle_ms:
                try:
                    result = await self._redis.xclaim(
                        stream,
                        consumer_group,
                        consumer_id,
                        min_idle_ms,
                        msg['message_id']
                    )
                    if result:
                        claimed.append(result[0][1])
                except Exception:
                    pass

        return claimed

    async def get_stream_info(self, stream: str) -> Dict[str, Any]:
        """Get stream information"""
        await self.connect()
        info = await self._redis.xinfo_stream(stream)
        return {
            "length": info.get('length', 0),
            "groups": info.get('groups', 0),
            "first_entry": info.get('first-entry'),
            "last_entry": info.get('last-entry')
        }

    async def trim_stream(self, stream: str, max_length: int):
        """Trim stream to max length"""
        await self.connect()
        await self._redis.xtrim(stream, max_length)


# Document processing queue
class DocumentProcessingQueue(RedisMessageQueue):
    """Specialized queue for document processing"""

    def __init__(self, redis_url: str):
        super().__init__(redis_url)
        self.pending_stream = "documents:pending"
        self.processing_stream = "documents:processing"
        self.completed_stream = "documents:completed"
        self.failed_stream = "documents:failed"

    async def queue_document(self, doc_id: str, kb_id: str, action: str = "index"):
        """Queue a document for processing"""
        return await self.publish(self.pending_stream, {
            "doc_id": doc_id,
            "kb_id": kb_id,
            "action": action,
            "status": "pending"
        })

    async def start_processing(self, consumer_id: str) -> List[Dict[str, Any]]:
        """Get documents to process"""
        return await self.consume(
            self.pending_stream,
            consumer_group="document_processors",
            consumer_id=consumer_id,
            count=10,
            block_ms=5000
        )

    async def mark_completed(self, doc_id: str, message_id: str, result: Dict[str, Any]):
        """Mark document as completed"""
        await self.acknowledge(self.pending_stream, "document_processors", message_id)
        await self.publish(self.completed_stream, {
            "doc_id": doc_id,
            "status": "completed",
            **result
        })

    async def mark_failed(self, doc_id: str, message_id: str, error: str):
        """Mark document as failed"""
        await self.acknowledge(self.pending_stream, "document_processors", message_id)
        await self.publish(self.failed_stream, {
            "doc_id": doc_id,
            "status": "failed",
            "error": error
        })

    async def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics"""
        try:
            pending_info = await self.get_stream_info(self.pending_stream)
            completed_info = await self.get_stream_info(self.completed_stream)
            failed_info = await self.get_stream_info(self.failed_stream)

            return {
                "pending": pending_info.get("length", 0),
                "completed": completed_info.get("length", 0),
                "failed": failed_info.get("length", 0)
            }
        except Exception as e:
            return {
                "error": str(e),
                "pending": 0,
                "completed": 0,
                "failed": 0
            }


# Global instance
_message_queue: Optional[DocumentProcessingQueue] = None


def get_message_queue(redis_url: str) -> DocumentProcessingQueue:
    """Get or create message queue instance"""
    global _message_queue
    if _message_queue is None:
        _message_queue = DocumentProcessingQueue(redis_url)
    return _message_queue
