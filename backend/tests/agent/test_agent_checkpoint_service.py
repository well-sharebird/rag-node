"""
Agent Checkpoint 服务测试
测试 LangGraph CheckpointSaver 的数据库持久化功能

注意：DatabaseCheckpointSaver 设计为同步接口（被 LangGraph 同步调用），
需要使用同步数据库驱动。本测试使用 psycopg2（同步驱动）进行测试。
"""
import asyncio
import sys
import uuid
from datetime import datetime

sys.path.insert(0, '.')

from sqlalchemy import create_engine, select, delete
from sqlalchemy.orm import sessionmaker

from app.models.agent import AgentConfig, AgentMemory
from app.services.agent_checkpoint_service import DatabaseCheckpointSaver

# 使用同步驱动
DATABASE_URL = "postgresql://postgres:postgres123@100.4.14.19:5432/rag_db"


class TestDatabaseCheckpointSaver:
    """数据库 CheckpointSaver 测试类"""

    def __init__(self):
        self.engine = None
        self.session = None
        self.test_agent_id = None
        self.test_user_id = 1

    def setup(self):
        """设置测试环境"""
        print("\n" + "=" * 60)
        print("设置测试环境 - Checkpoint 服务")
        print("=" * 60)

        # 创建同步引擎和 session
        self.engine = create_engine(DATABASE_URL, echo=False)
        SessionLocal = sessionmaker(bind=self.engine)
        self.session = SessionLocal()

        # 创建测试 Agent
        self.test_agent_id = str(uuid.uuid4())
        agent = AgentConfig(
            id=self.test_agent_id,
            user_id=self.test_user_id,
            name="Checkpoint 测试助手",
            description="用于测试 Checkpoint 服务的 Agent",
            agent_type="single",
            default_model_config={
                "provider": "local_qwen",
                "model": "qwen3.5-397b-a17b",
                "temperature": 0.7,
                "max_tokens": 4096,
            },
            system_prompt="你是一个测试助手。",
            status="active",
        )
        self.session.add(agent)
        self.session.commit()
        print(f"✓ 测试 Agent 创建成功：{self.test_agent_id[:8]}...")

        # 创建 CheckpointSaver
        self.checkpoint_saver = DatabaseCheckpointSaver(self.session)
        print(f"✓ CheckpointSaver 创建成功")

    def teardown(self):
        """清理测试环境"""
        print("\n" + "=" * 60)
        print("清理测试环境")
        print("=" * 60)

        try:
            # 删除 Agent
            self.session.execute(
                delete(AgentConfig).where(AgentConfig.id == self.test_agent_id)
            )
            self.session.commit()
            print("✓ 测试数据已清理")
        except Exception as e:
            self.session.rollback()
            print(f"✗ 清理失败：{e}")
        finally:
            self.session.close()
            self.engine.dispose()

    def test_put_checkpoint(self):
        """测试保存 Checkpoint"""
        print("\n" + "=" * 60)
        print("测试：保存 Checkpoint")
        print("=" * 60)

        # 使用正确的 thread_id 格式："{user_id}:{agent_id}:{session_id}"
        session_id = f"test_session_{uuid.uuid4().hex[:8]}"
        thread_id = f"{self.test_user_id}:{self.test_agent_id}:{session_id}"
        checkpoint_ns = str(uuid.uuid4())
        checkpoint_id = str(uuid.uuid4())

        checkpoint = {
            "channel_values": {
                "messages": [
                    {"type": "human", "content": "你好"},
                    {"type": "ai", "content": "你好！有什么可以帮助你的？"},
                ]
            },
            "channel_versions": {"__root__": 2},
            "versions_seen": {},
            "pending_sends": [],
        }

        config = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

        try:
            # 保存 checkpoint
            saved_checkpoint = self.checkpoint_saver.put(config, checkpoint, {"source": "input"}, {})

            print(f"✓ Checkpoint 保存成功")
            print(f"  thread_id: {thread_id}")
            print(f"  checkpoint_id: {checkpoint_id[:8]}...")

            return thread_id, checkpoint_ns, checkpoint_id
        except Exception as e:
            print(f"✗ Checkpoint 保存失败：{e}")
            import traceback
            traceback.print_exc()
            return None, None, None

    def test_get_checkpoint(self, thread_id: str, checkpoint_ns: str):
        """测试获取 Checkpoint"""
        print("\n" + "=" * 60)
        print("测试：获取 Checkpoint")
        print("=" * 60)

        try:
            config = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                }
            }

            checkpoint = self.checkpoint_saver.get(config)

            if checkpoint:
                print(f"✓ Checkpoint 获取成功")
                channel_values = checkpoint.get("channel_values", {})
                messages = channel_values.get("messages", [])
                print(f"  消息数：{len(messages)}")
                if messages:
                    first_msg = messages[0]
                    if isinstance(first_msg, dict):
                        print(f"  第一条：{first_msg.get('content', '')[:30]}...")
                    else:
                        print(f"  第一条：{str(first_msg)[:30]}...")
            else:
                print(f"⚠ 未找到 Checkpoint")

            return checkpoint is not None
        except Exception as e:
            print(f"✗ Checkpoint 获取失败：{e}")
            import traceback
            traceback.print_exc()
            return False

    def test_list_checkpoints(self, thread_id: str):
        """测试列出 Checkpoints"""
        print("\n" + "=" * 60)
        print("测试：列出 Checkpoints")
        print("=" * 60)

        try:
            # 使用 thread_id 前缀匹配
            config = {
                "configurable": {
                    "thread_id": thread_id,
                }
            }

            checkpoints = list(self.checkpoint_saver.list(config))

            print(f"✓ Checkpoint 列表获取成功")
            print(f"  数量：{len(checkpoints)}")

            return len(checkpoints)
        except Exception as e:
            print(f"✗ Checkpoint 列表获取失败：{e}")
            import traceback
            traceback.print_exc()
            return 0

    def test_update_checkpoint_metadata(self, thread_id: str, checkpoint_ns: str, checkpoint_id: str):
        """测试更新 Checkpoint 元数据"""
        print("\n" + "=" * 60)
        print("测试：更新 Checkpoint 元数据")
        print("=" * 60)

        checkpoint = {
            "channel_values": {"messages": [{"type": "human", "content": "测试"}]},
            "channel_versions": {"__root__": 1},
            "versions_seen": {},
            "pending_sends": [],
        }

        config = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

        try:
            # 更新元数据
            self.checkpoint_saver.put(
                config,
                checkpoint,
                {"source": "loop", "step": 1},
                {"user_id": self.test_user_id}
            )

            print(f"✓ Checkpoint 元数据更新成功")
            return True
        except Exception as e:
            print(f"✗ Checkpoint 元数据更新失败：{e}")
            import traceback
            traceback.print_exc()
            return False

    def run_all_tests(self):
        """运行所有测试"""
        self.setup()

        try:
            # 测试保存
            thread_id, checkpoint_ns, checkpoint_id = self.test_put_checkpoint()

            if thread_id:
                # 测试获取
                self.test_get_checkpoint(thread_id, checkpoint_ns)

                # 测试列表
                self.test_list_checkpoints(thread_id)

                # 测试元数据更新
                self.test_update_checkpoint_metadata(thread_id, checkpoint_ns, checkpoint_id)

            print("\n" + "=" * 60)
            print("所有 Checkpoint 服务测试完成 ✅")
            print("=" * 60)

        except AssertionError as e:
            print(f"\n❌ 测试失败：{e}")
        except Exception as e:
            print(f"\n❌ 测试异常：{e}")
            import traceback
            traceback.print_exc()
        finally:
            self.teardown()


def main():
    """运行测试"""
    tester = TestDatabaseCheckpointSaver()
    tester.run_all_tests()


if __name__ == "__main__":
    main()
