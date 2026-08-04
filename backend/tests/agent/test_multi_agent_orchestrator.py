"""
多 Agent 编排器测试
测试增强后的多 Agent 编排能力：
1. Supervisor 模式 - 基于 LLM 决策分配任务
2. Round Robin 模式 - 顺序轮询执行
3. Voting 模式 - 多 Agent 投票决策
4. Custom 模式 - 自定义编排逻辑
"""
import asyncio
import sys
import uuid
from datetime import datetime

sys.path.insert(0, '.')

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, delete

from app.models.agent import AgentConfig
from app.services.multi_agent_orchestrator import (
    MultiAgentOrchestrator,
    OrchestrationMode,
    SupervisorOrchestrator,
    RoundRobinOrchestrator,
    VotingOrchestrator,
)

DATABASE_URL = "postgresql+asyncpg://postgres:postgres123@100.4.14.19:5432/rag_db"


class MockModelGateway:
    """模拟模型网关"""

    async def get_model_by_name(self, name: str):
        from app.schemas.chat import ModelConfig
        return ModelConfig(
            provider="local_qwen",
            model="qwen3.5-397b-a17b",
            temperature=0.7,
            max_tokens=4096,
            base_url="http://100.4.14.19:8000",
            api_key="not-needed",
        )


class MockSkillRegistry:
    """模拟技能注册表"""

    def get_tool(self, skill_id: str):
        return None


async def test_round_robin_orchestrator():
    """测试 Round Robin 模式编排器"""
    print("=" * 70)
    print("多 Agent 编排测试 - Round Robin 模式")
    print("=" * 70)

    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # 创建 3 个子 Agent 配置
    worker_ids = []
    user_id = 1

    async with async_session() as session:
        # ========== Step 1: 创建 Worker Agents ==========
        print("\n[Step 1] 创建 Worker Agents...")
        worker_roles = [
            ("researcher", "研究助手", "负责信息搜集和分析"),
            ("writer", "写作助手", "负责内容创作和编辑"),
            ("reviewer", "审核助手", "负责质量检查和优化"),
        ]

        for role, name, desc in worker_roles:
            agent_id = str(uuid.uuid4())
            worker_ids.append(agent_id)

            agent = AgentConfig(
                id=agent_id,
                user_id=user_id,
                name=name,
                description=desc,
                agent_type="single",
                default_model_config={
                    "provider": "local_qwen",
                    "model": "qwen3.5-397b-a17b",
                    "temperature": 0.7,
                    "max_tokens": 4096,
                },
                system_prompt=f"你是一个{name}。{desc}",
                enabled_skills=[],
                mcp_servers=[],
                status="active",
            )
            session.add(agent)

        await session.commit()
        print(f"✓ 创建 {len(worker_ids)} 个 Worker Agent")

        # ========== Step 2: 创建主 Agent 配置（Round Robin 模式） ==========
        print("\n[Step 2] 创建主 Agent 配置（Round Robin 模式）...")
        main_agent_id = str(uuid.uuid4())

        main_agent = AgentConfig(
            id=main_agent_id,
            user_id=user_id,
            name="流水线助手",
            description="使用 Round Robin 模式协调多个专家",
            agent_type="multi",
            default_model_config={
                "provider": "local_qwen",
                "model": "qwen3.5-397b-a17b",
                "temperature": 0.7,
                "max_tokens": 4096,
            },
            system_prompt="你是一个多 Agent 编排系统。",
            multi_agent_config={
                "mode": "round_robin",
                "workers": [
                    {
                        "agent_id": worker_ids[0],
                        "role": "researcher",
                        "description": "研究助手",
                        "task_prompt": "请分析以下问题并提供相关信息：",
                    },
                    {
                        "agent_id": worker_ids[1],
                        "role": "writer",
                        "description": "写作助手",
                        "task_prompt": "请根据以下信息撰写内容：",
                    },
                    {
                        "agent_id": worker_ids[2],
                        "role": "reviewer",
                        "description": "审核助手",
                        "task_prompt": "请审核以下内容并提出改进建议：",
                    },
                ],
                "max_iterations": 3,
            },
            status="active",
        )
        session.add(main_agent)
        await session.commit()
        print(f"✓ 主 Agent 创建成功，ID: {main_agent_id[:8]}...")

        # ========== Step 3: 执行 Round Robin 编排 ==========
        print("\n[Step 3] 执行 Round Robin 编排...")
        try:
            mock_gateway = MockModelGateway()
            mock_registry = MockSkillRegistry()

            orchestrator = MultiAgentOrchestrator(
                db=session,
                model_gateway=mock_gateway,
                skill_registry=mock_registry,
            )

            # 获取主 Agent 配置
            result = await session.execute(
                select(AgentConfig).where(AgentConfig.id == main_agent_id)
            )
            main_agent_config = result.scalar_one_or_none()

            response = await orchestrator.orchestrate(
                agent_config=main_agent_config,
                user_id=user_id,
                query="请帮我写一段关于人工智能的简介",
            )

            print(f"✓ Round Robin 编排完成")
            print(f"  run_id: {response.get('run_id', 'N/A')[:8]}...")
            print(f"  mode: {response.get('mode', 'N/A')}")
            print(f"  worker 数量：{len(response.get('agent_results', {}))}")
            print(f"  最终响应长度：{len(response.get('final_response', ''))}")

            # 检查每个 worker 的结果
            for worker_id, worker_result in response.get('agent_results', {}).items():
                if 'error' in worker_result:
                    print(f"    Worker {worker_id[:8]}...: ❌ {worker_result['error'][:50]}...")
                else:
                    print(f"    Worker {worker_id[:8]}...: ✅ 成功")

        except Exception as e:
            print(f"✗ 编排失败：{e}")
            import traceback
            traceback.print_exc()

        # ========== 清理 ==========
        print("\n[清理] 删除测试数据...")
        try:
            await session.execute(
                delete(AgentConfig).where(AgentConfig.id == main_agent_id)
            )
            for wid in worker_ids:
                await session.execute(
                    delete(AgentConfig).where(AgentConfig.id == wid)
                )
            await session.commit()
            print(f"✓ 测试数据已清理")
        except Exception as e:
            await session.rollback()
            print(f"✗ 清理失败：{e}")

    print("\n" + "=" * 70)
    print("Round Robin 模式测试完成")
    print("=" * 70)


async def test_voting_orchestrator():
    """测试 Voting 模式编排器"""
    print("\n" + "=" * 70)
    print("多 Agent 编排测试 - Voting 模式")
    print("=" * 70)

    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # 创建 3 个子 Agent 配置
    worker_ids = []
    user_id = 1

    async with async_session() as session:
        # ========== Step 1: 创建 Worker Agents ==========
        print("\n[Step 1] 创建 Worker Agents...")
        worker_names = ["评审 A", "评审 B", "评审 C"]

        for name in worker_names:
            agent_id = str(uuid.uuid4())
            worker_ids.append(agent_id)

            agent = AgentConfig(
                id=agent_id,
                user_id=user_id,
                name=name,
                description=f"独立评审员 {name}",
                agent_type="single",
                default_model_config={
                    "provider": "local_qwen",
                    "model": "qwen3.5-397b-a17b",
                    "temperature": 0.7,
                    "max_tokens": 4096,
                },
                system_prompt=f"你是{name}。请独立、客观地评审问题。",
                enabled_skills=[],
                mcp_servers=[],
                status="active",
            )
            session.add(agent)

        await session.commit()
        print(f"✓ 创建 {len(worker_ids)} 个评审 Agent")

        # ========== Step 2: 创建主 Agent 配置（Voting 模式） ==========
        print("\n[Step 2] 创建主 Agent 配置（Voting 模式）...")
        main_agent_id = str(uuid.uuid4())

        main_agent = AgentConfig(
            id=main_agent_id,
            user_id=user_id,
            name="投票决策助手",
            description="使用 Voting 模式进行多专家独立评审",
            agent_type="multi",
            default_model_config={
                "provider": "local_qwen",
                "model": "qwen3.5-397b-a17b",
                "temperature": 0.7,
                "max_tokens": 4096,
            },
            system_prompt="你是一个多 Agent 投票系统。",
            multi_agent_config={
                "mode": "voting",
                "workers": [
                    {"agent_id": worker_ids[0], "role": "reviewer_a"},
                    {"agent_id": worker_ids[1], "role": "reviewer_b"},
                    {"agent_id": worker_ids[2], "role": "reviewer_c"},
                ],
            },
            status="active",
        )
        session.add(main_agent)
        await session.commit()

        # ========== Step 3: 执行 Voting 编排 ==========
        print("\n[Step 3] 执行 Voting 编排（并行执行）...")
        try:
            mock_gateway = MockModelGateway()
            mock_registry = MockSkillRegistry()

            orchestrator = MultiAgentOrchestrator(
                db=session,
                model_gateway=mock_gateway,
                skill_registry=mock_registry,
            )

            result = await session.execute(
                select(AgentConfig).where(AgentConfig.id == main_agent_id)
            )
            main_agent_config = result.scalar_one_or_none()

            response = await orchestrator.orchestrate(
                agent_config=main_agent_config,
                user_id=user_id,
                query="评估以下方案是否可行：在公司内部推行 4 天工作制",
            )

            print(f"✓ Voting 编排完成")
            print(f"  run_id: {response.get('run_id', 'N/A')[:8]}...")
            print(f"  mode: {response.get('mode', 'N/A')}")
            print(f"  投票数：{response.get('vote_count', 0)}")
            print(f"  最终响应长度：{len(response.get('final_response', ''))}")

        except Exception as e:
            print(f"✗ 编排失败：{e}")
            import traceback
            traceback.print_exc()

        # ========== 清理 ==========
        print("\n[清理] 删除测试数据...")
        try:
            await session.execute(
                delete(AgentConfig).where(AgentConfig.id == main_agent_id)
            )
            for wid in worker_ids:
                await session.execute(
                    delete(AgentConfig).where(AgentConfig.id == wid)
                )
            await session.commit()
            print(f"✓ 测试数据已清理")
        except Exception as e:
            await session.rollback()
            print(f"✗ 清理失败：{e}")

    print("\n" + "=" * 70)
    print("Voting 模式测试完成")
    print("=" * 70)


async def test_supervisor_orchestrator():
    """测试 Supervisor 模式编排器"""
    print("\n" + "=" * 70)
    print("多 Agent 编排测试 - Supervisor 模式")
    print("=" * 70)

    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    worker_ids = []
    user_id = 1

    async with async_session() as session:
        # 创建 Worker Agents
        print("\n[Step 1] 创建 Worker Agents...")
        workers = [
            ("代码审查员", "负责代码质量检查"),
            ("文档撰写员", "负责技术文档编写"),
        ]

        for name, desc in workers:
            agent_id = str(uuid.uuid4())
            worker_ids.append(agent_id)

            agent = AgentConfig(
                id=agent_id,
                user_id=user_id,
                name=name,
                description=desc,
                agent_type="single",
                default_model_config={
                    "provider": "local_qwen",
                    "model": "qwen3.5-397b-a17b",
                    "temperature": 0.7,
                    "max_tokens": 4096,
                },
                system_prompt=f"你是{name}。{desc}",
                status="active",
            )
            session.add(agent)

        await session.commit()
        print(f"✓ 创建 {len(worker_ids)} 个 Worker")

        # 创建主 Agent（Supervisor 模式）
        print("\n[Step 2] 创建主 Agent 配置（Supervisor 模式）...")
        main_agent_id = str(uuid.uuid4())

        main_agent = AgentConfig(
            id=main_agent_id,
            user_id=user_id,
            name="主管助手",
            description="使用 Supervisor 模式协调多个专家",
            agent_type="multi",
            default_model_config={
                "provider": "local_qwen",
                "model": "qwen3.5-397b-a17b",
                "temperature": 0.7,
                "max_tokens": 4096,
            },
            system_prompt="你是一个主管，负责协调团队成员完成任务。",
            multi_agent_config={
                "mode": "supervisor",
                "workers": [
                    {
                        "agent_id": worker_ids[0],
                        "role": "code_reviewer",
                        "description": "代码审查专家",
                    },
                    {
                        "agent_id": worker_ids[1],
                        "role": "doc_writer",
                        "description": "文档撰写专家",
                    },
                ],
                "max_iterations": 2,
            },
            status="active",
        )
        session.add(main_agent)
        await session.commit()

        # 执行 Supervisor 编排
        print("\n[Step 3] 执行 Supervisor 编排...")
        try:
            mock_gateway = MockModelGateway()
            mock_registry = MockSkillRegistry()

            orchestrator = MultiAgentOrchestrator(
                db=session,
                model_gateway=mock_gateway,
                skill_registry=mock_registry,
            )

            result = await session.execute(
                select(AgentConfig).where(AgentConfig.id == main_agent_id)
            )
            main_agent_config = result.scalar_one_or_none()

            response = await orchestrator.orchestrate(
                agent_config=main_agent_config,
                user_id=user_id,
                query="请审查这段代码并编写文档",
            )

            print(f"✓ Supervisor 编排完成")
            print(f"  mode: {response.get('mode', 'N/A')}")
            print(f"  迭代次数：{response.get('iterations', 0)}")

        except Exception as e:
            print(f"✗ 编排失败：{e}")

        # 清理
        print("\n[清理] 删除测试数据...")
        try:
            await session.execute(
                delete(AgentConfig).where(AgentConfig.id == main_agent_id)
            )
            for wid in worker_ids:
                await session.execute(
                    delete(AgentConfig).where(AgentConfig.id == wid)
                )
            await session.commit()
            print(f"✓ 测试数据已清理")
        except Exception as e:
            await session.rollback()
            print(f"✗ 清理失败：{e}")

    print("\n" + "=" * 70)
    print("Supervisor 模式测试完成")
    print("=" * 70)


async def main():
    """运行所有测试"""
    await test_round_robin_orchestrator()
    await test_voting_orchestrator()
    await test_supervisor_orchestrator()


if __name__ == "__main__":
    asyncio.run(main())
