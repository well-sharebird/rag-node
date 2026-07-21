"""
Kafka client for message queue and event streaming
"""
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from typing import Dict, Any, Optional, List, Callable
import json
import asyncio
import logging

logger = logging.getLogger(__name__)


class KafkaClient:
    """Kafka client for async message processing"""

    def __init__(
        self,
        bootstrap_servers: str = None,
        consumer_group: str = None,
    ):
        from app.config import settings
        self.bootstrap_servers = bootstrap_servers or settings.kafka_bootstrap_servers
        self.consumer_group = consumer_group or settings.kafka_consumer_group
        self._producer: Optional[AIOKafkaProducer] = None
        self._consumers: Dict[str, AIOKafkaConsumer] = {}

    async def start(self):
        """Start Kafka producer"""
        if self._producer is None:
            self._producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                key_serializer=lambda k: k.encode('utf-8') if k else None
            )
            try:
                await self._producer.start()
                logger.info(f"Connected to Kafka: {self.bootstrap_servers}")
            except Exception as e:
                logger.warning(f"Kafka connection failed: {e}")
                self._producer = None

    async def stop(self):
        """Stop Kafka producer and consumers"""
        if self._producer:
            await self._producer.stop()
            self._producer = None

        for consumer in self._consumers.values():
            await consumer.stop()
        self._consumers.clear()

    @property
    def producer(self) -> Optional[AIOKafkaProducer]:
        return self._producer

    async def publish(
        self,
        topic: str,
        message: Dict[str, Any],
        key: Optional[str] = None
    ):
        """Publish a message to a topic"""
        if not self._producer:
            await self.start()
        if not self._producer:
            return

        try:
            await self._producer.send_and_wait(
                topic,
                value=message,
                key=key
            )
            logger.debug(f"Published to {topic}: {message.get('id', 'unknown')}")
        except Exception as e:
            logger.error(f"Failed to publish to {topic}: {e}")

    async def subscribe(
        self,
        topic: str,
        callback: Callable[[Dict[str, Any]], Any],
        auto_commit: bool = True
    ):
        """Subscribe to a topic and process messages"""
        if self._producer is None:
            await self.start()

        consumer = AIOKafkaConsumer(
            topic,
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.consumer_group,
            value_deserializer=lambda v: json.loads(v.decode('utf-8')),
            key_deserializer=lambda k: k.decode('utf-8') if k else None,
            auto_commit_enable=auto_commit
        )

        try:
            await consumer.start()
            self._consumers[topic] = consumer
            logger.info(f"Subscribed to topic: {topic}")

            async for msg in consumer:
                try:
                    await callback(msg.value)
                except Exception as e:
                    logger.error(f"Error processing message from {topic}: {e}")

        except Exception as e:
            logger.error(f"Consumer error for {topic}: {e}")
        finally:
            await consumer.stop()
            if topic in self._consumers:
                del self._consumers[topic]

    async def consume_batch(
        self,
        topic: str,
        max_messages: int = 10,
        timeout_ms: int = 5000
    ) -> List[Dict[str, Any]]:
        """Consume a batch of messages"""
        if topic not in self._consumers:
            consumer = AIOKafkaConsumer(
                topic,
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.consumer_group,
                value_deserializer=lambda v: json.loads(v.decode('utf-8')),
                auto_commit_enable=True
            )
            await consumer.start()
            self._consumers[topic] = consumer

        consumer = self._consumers[topic]
        messages = []

        try:
            async for msg in consumer:
                messages.append(msg.value)
                if len(messages) >= max_messages:
                    break
        except asyncio.TimeoutError:
            pass

        return messages

    async def get_topics(self) -> List[str]:
        """Get list of topics"""
        if not self._producer:
            return []

        try:
            metadata = await self._producer.client().update_metadata()
            return list(metadata.topics.keys())
        except Exception:
            return []

    async def create_topic(self, topic: str, num_partitions: int = 3, replication_factor: int = 1):
        """Create a topic"""
        from aiokafka.admin import NewTopic, AIOKafkaAdminClient

        admin = AIOKafkaAdminClient(bootstrap_servers=self.bootstrap_servers)
        try:
            await admin.start()
            new_topic = NewTopic(
                name=topic,
                num_partitions=num_partitions,
                replication_factor=replication_factor
            )
            await admin.create_topics([new_topic])
            logger.info(f"Created topic: {topic}")
        except Exception as e:
            logger.warning(f"Failed to create topic {topic}: {e}")
        finally:
            await admin.close()


# Document processing topics
class DocumentProcessingKafka(KafkaClient):
    """Specialized Kafka for document processing pipeline"""

    def __init__(self, bootstrap_servers: str):
        super().__init__(bootstrap_servers, consumer_group="document_processors")
        self.topics = {
            "pending": "documents.pending",
            "processing": "documents.processing",
            "completed": "documents.completed",
            "failed": "documents.failed"
        }

    async def setup_topics(self):
        """Create all document processing topics"""
        for topic in self.topics.values():
            await self.create_topic(topic)

    async def queue_document(self, doc_id: str, kb_id: str, action: str = "index"):
        """Queue a document for processing"""
        await self.publish(self.topics["pending"], {
            "doc_id": doc_id,
            "kb_id": kb_id,
            "action": action,
            "status": "pending",
            "timestamp": __import__("datetime").datetime.utcnow().isoformat()
        })

    async def mark_processing(self, doc_id: str, worker_id: str):
        """Mark document as being processed"""
        await self.publish(self.topics["processing"], {
            "doc_id": doc_id,
            "worker_id": worker_id,
            "status": "processing"
        })

    async def mark_completed(self, doc_id: str, result: Dict[str, Any]):
        """Mark document as completed"""
        await self.publish(self.topics["completed"], {
            "doc_id": doc_id,
            "status": "completed",
            **result
        })

    async def mark_failed(self, doc_id: str, error: str):
        """Mark document as failed"""
        await self.publish(self.topics["failed"], {
            "doc_id": doc_id,
            "status": "failed",
            "error": error
        })


# Global instance
_kafka_client: Optional[KafkaClient] = None


def get_kafka_client() -> KafkaClient:
    """Get or create Kafka client"""
    global _kafka_client
    if _kafka_client is None:
        _kafka_client = KafkaClient()
    return _kafka_client


async def initialize_kafka():
    """Initialize Kafka client"""
    client = get_kafka_client()
    await client.start()
    return client
