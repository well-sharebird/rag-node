"""
Subagent Service
子智能体服务 - 负责动态唤起和执行子智能体

架构设计：
- Lead Agent 通过 task 工具委托任务
- Subagent Service 接收委托，动态创建/选择子智能体
- 子智能体执行完成后返回结果给 Lead Agent
"""
import logging
from typing import Optional, Any, AsyncGenerator
from datetime import datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from packages.agent.models.agent import AgentConfig

logger = logging.getLogger("app.services.subagent_service")


# ============================================================
# Subagent Types
# ============================================================

class SubagentType:
    """子智能体类型定义"""

    CODE_ANALYZER = "code_analyzer"
    DOC_WRITER = "doc_writer"
    RESEARCHER = "researcher"
    DATA_ANALYST = "data_analyst"
    TESTER = "tester"
    REVIEWER = "reviewer"
    CUSTOM = "custom"


# ============================================================
# Subagent Configurations
# ============================================================

SUBAGENT_CONFIGS = {
    SubagentType.CODE_ANALYZER: {
        "name": "代码分析专家",
        "system_prompt": """你是一位资深代码分析专家。你的职责：
1. 分析代码结构、质量和潜在问题
2. 识别代码异味、安全漏洞和性能瓶颈
3. 提供具体的改进建议
4. 解释复杂代码逻辑

请以结构化方式输出分析结果。""",
        "default_skills": ["code_interpreter"],
        "default_model": {"provider": "anthropic", "model": "claude-3-5-sonnet"},
    },
    SubagentType.DOC_WRITER: {
        "name": "技术文档专家",
        "system_prompt": """你是一位专业技术文档工程师。你的职责：
1. 编写清晰的 API 文档、用户手册
2. 将技术概念转化为易懂的文档
3. 生成 Markdown、OpenAPI 规范等格式

请输出专业、结构化的文档内容。""",
        "default_skills": ["file_processor"],
        "default_model": {"provider": "anthropic", "model": "claude-3-5-sonnet"},
    },
    SubagentType.RESEARCHER: {
        "name": "研究分析专家",
        "system_prompt": """你是一位专业研究分析师。你的职责：
1. 搜集和整理特定主题的信息
2. 分析趋势、对比不同方案
3. 提供有数据支持的结论

请输出详细、有引用来源的研究报告。""",
        "default_skills": ["web_search"],
        "default_model": {"provider": "anthropic", "model": "claude-3-opus"},
    },
    SubagentType.DATA_ANALYST: {
        "name": "数据分析专家",
        "system_prompt": """你是一位资深数据分析师。你的职责：
1. 分析数据集，发现模式和趋势
2. 生成统计报告和可视化建议
3. 解释数据背后的业务含义

请输出结构化的数据分析报告。""",
        "default_skills": ["data_analysis"],
        "default_model": {"provider": "anthropic", "model": "claude-3-5-sonnet"},
    },
    SubagentType.TESTER: {
        "name": "测试专家",
        "system_prompt": """你是一位 QA 测试专家。你的职责：
1. 设计测试用例和测试计划
2. 编写单元测试、集成测试代码
3. 分析测试覆盖率和质量

请输出完整的测试方案和代码。""",
        "default_skills": ["code_interpreter"],
        "default_model": {"provider": "anthropic", "model": "claude-3-5-sonnet"},
    },
    SubagentType.REVIEWER: {
        "name": "代码审查专家",
        "system_prompt": """你是一位资深代码审查专家。你的职责：
1. 审查代码质量和规范遵循
2. 识别 bug、安全漏洞和性能问题
3. 提供具体的改进建议

请以建设性、详细的方式输出审查意见。""",
        "default_skills": ["code_interpreter"],
        "default_model": {"provider": "anthropic", "model": "claude-3-opus"},
    },
}


# ============================================================
# Subagent Execution Result
# ============================================================

class SubagentResult:
    """子智能体执行结果"""

    def __init__(
        self,
        success: bool,
        output: str,
        subagent_type: str,
        execution_time_ms: int,
        tokens_used: int = 0,
        metadata: dict = None,
    ):
        self.success = success
        self.output = output
        self.subagent_type = subagent_type
        self.execution_time_ms = execution_time_ms
        self.tokens_used = tokens_used
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output": self.output,
            "subagent_type": self.subagent_type,
            "execution_time_ms": self.execution_time_ms,
            "tokens_used": self.tokens_used,
            "metadata": self.metadata,
        }


# ============================================================
# Subagent Service
# ============================================================

class SubagentService:
    """
    子智能体服务

    负责动态唤起和执行子智能体
    """

    def __init__(
        self,
        db: AsyncSession,
        model_gateway: Any,
        skill_registry: Any,
        lead_agent_factory: Any,
    ):
        self.db = db
        self.model_gateway = model_gateway
        self.skill_registry = skill_registry
        self.lead_agent_factory = lead_agent_factory

        # 子智能体实例缓存（可选，用于复用）
        self._agent_cache: dict[str, Any] = {}

    async def execute(
        self,
        subagent_type: str,
        task: str,
        expected_output: str,
        parent_context: dict,
        priority: str = "normal",
    ) -> str:
        """
        执行子智能体任务

        Args:
            subagent_type: 子智能体类型
            task: 任务描述
            expected_output: 期望输出
            parent_context: 父 Agent 上下文
            priority: 优先级

        Returns:
            执行结果
        """
        import time
        start_time = time.time()

        logger.info(
            "[Subagent] Executing | type=%s task=%s priority=%s",
            subagent_type, task[:50] if len(task) > 50 else task, priority
        )

        try:
            # 1. 获取子智能体配置
            config = self._get_subagent_config(subagent_type)

            # 2. 创建或获取子智能体
            agent_config = await self._get_or_create_subagent_config(
                subagent_type, config, parent_context
            )

            # 3. 执行子智能体
            result = await self._execute_subagent(
                agent_config, task, expected_output, parent_context
            )

            execution_time = int((time.time() - start_time) * 1000)

            subagent_result = SubagentResult(
                success=True,
                output=result,
                subagent_type=subagent_type,
                execution_time_ms=execution_time,
                metadata={"task": task[:100] if len(task) > 100 else task},
            )

            # 记录执行日志
            await self._log_execution(subagent_result, parent_context)

            return result

        except Exception as e:
            logger.error("[Subagent] Execution failed: %s", e)
            execution_time = int((time.time() - start_time) * 1000)

            subagent_result = SubagentResult(
                success=False,
                output=f"[ERROR] {str(e)}",
                subagent_type=subagent_type,
                execution_time_ms=execution_time,
                metadata={"error": str(e)},
            )

            await self._log_execution(subagent_result, parent_context)
            return f"[ERROR] Subagent execution failed: {str(e)}"

    def _get_subagent_config(self, subagent_type: str) -> dict:
        """获取子智能体配置"""
        if subagent_type in SUBAGENT_CONFIGS:
            return SUBAGENT_CONFIGS[subagent_type]

        # 自定义子智能体
        return {
            "name": f"Custom Agent: {subagent_type}",
            "system_prompt": f"你是一个{subagent_type}专家。",
            "default_skills": [],
            "default_model": {"provider": "anthropic", "model": "claude-3-5-sonnet"},
        }

    async def _get_or_create_subagent_config(
        self,
        subagent_type: str,
        config: dict,
        parent_context: dict,
    ) -> AgentConfig:
        """
        获取或创建子智能体配置

        优先使用数据库中已存在的配置，不存在则临时创建
        """
        # 尝试从数据库获取已注册的子智能体
        result = await self.db.execute(
            select(AgentConfig).where(
                AgentConfig.name == config["name"],
                AgentConfig.user_id == parent_context.get("user_id"),
            )
        )
        agent_config = result.scalar_one_or_none()

        if agent_config:
            return agent_config

        # 临时创建内存中的配置（不持久化）
        agent_config = AgentConfig(
            id=f"subagent_{subagent_type}_{uuid4().hex[:8]}",
            user_id=parent_context.get("user_id"),
            name=config["name"],
            description=f"子智能体：{subagent_type}",
            agent_type="single",
            system_prompt=config["system_prompt"],
            default_model_config=config["default_model"],
            enabled_skills=config.get("default_skills", []),
            extensions_config={},
        )

        return agent_config

    async def _execute_subagent(
        self,
        agent_config: AgentConfig,
        task: str,
        expected_output: str,
        parent_context: dict,
    ) -> str:
        """
        执行子智能体

        复用 LeadAgentFactory 的图构建能力
        """
        # 使用 LeadAgentFactory 构建子智能体图
        # 子智能体本质上是简化版的 Lead Agent

        runtime_config = {
            "model_name": parent_context.get("requested_model"),
            "skills": agent_config.enabled_skills,
            "mcp_servers": [],
        }

        # 构建提示词
        enhanced_prompt = f"""{agent_config.system_prompt}

当前任务：
{task}

期望输出格式：
{expected_output}

请专注完成任务并提供清晰的输出。"""

        # 使用工厂创建并执行
        async with self.lead_agent_factory.create_lead_agent(
            agent_config=agent_config,
            runtime_config=runtime_config,
            run_id=str(uuid4()),
            user_id=parent_context.get("user_id", 0),
        ) as graph:
            from langchain_core.messages import HumanMessage
            from packages.core.database import engine
            from sqlalchemy.orm import sessionmaker
            from packages.agent.services.agent_checkpoint_service import DatabaseCheckpointSaver

            sync_session_factory = sessionmaker(bind=engine.sync_engine)
            sync_db = sync_session_factory()

            try:
                checkpoint_saver = DatabaseCheckpointSaver(sync_db)
                config = {
                    "configurable": {
                        "thread_id": f"{parent_context.get('user_id')}:{agent_config.id}:subagent",
                        "checkpoint_saver": checkpoint_saver,
                        "parent_run_id": parent_context.get("run_id"),
                    }
                }

                initial_state = {
                    "messages": [HumanMessage(content=enhanced_prompt)],
                    "context": {
                        "parent_context": parent_context,
                        "task": task,
                        "expected_output": expected_output,
                    },
                    "current_step": "start",
                    "metadata": {
                        "user_id": parent_context.get("user_id"),
                        "agent_id": agent_config.id,
                        "is_subagent": True,
                    },
                }

                result = await graph.ainvoke(initial_state, config=config)
                messages = result.get("messages", [])

                return messages[-1].content if messages else ""

            finally:
                sync_db.close()

    async def _log_execution(
        self,
        result: SubagentResult,
        parent_context: dict,
    ):
        """记录执行日志"""
        from packages.agent.models.agent import AgentCallLog

        log = AgentCallLog(
            id=str(uuid4()),
            agent_id=f"subagent_{result.subagent_type}",
            user_id=parent_context.get("user_id"),
            thread_id=f"{parent_context.get('user_id')}:subagent:{result.subagent_type}",
            run_id=str(uuid4()),
            model_provider="system",
            model_name=result.subagent_type,
            input_tokens=0,
            output_tokens=result.tokens_used,
            total_tokens=result.tokens_used,
            latency_ms=result.execution_time_ms,
            status="success" if result.success else "error",
            error_message=None if result.success else result.output,
            input_summary={"task": parent_context.get("task", "")[:200]},
            output_summary={"output": result.output[:200]},
        )

        self.db.add(log)
        try:
            await self.db.commit()
        except Exception as e:
            logger.error("Failed to log subagent execution: %s", e)
            await self.db.rollback()

    async def get_available_subagents(self) -> list[dict]:
        """获取可用的子智能体列表"""
        return [
            {
                "type": key,
                "name": config["name"],
                "description": config["system_prompt"][:100],
                "default_skills": config.get("default_skills", []),
            }
            for key, config in SUBAGENT_CONFIGS.items()
        ]

    async def register_custom_subagent(
        self,
        name: str,
        system_prompt: str,
        skills: list[str],
        model_config: dict,
        user_id: int,
    ) -> AgentConfig:
        """
        注册自定义子智能体

        将自定义子智能体持久化到数据库
        """
        agent_config = AgentConfig(
            id=f"custom_subagent_{name}_{uuid4().hex[:8]}",
            user_id=user_id,
            name=name,
            description=f"自定义子智能体：{name}",
            agent_type="single",
            system_prompt=system_prompt,
            default_model_config=model_config,
            enabled_skills=skills,
            extensions_config={"is_custom_subagent": True},
            status="active",
        )

        self.db.add(agent_config)
        await self.db.commit()
        await self.db.refresh(agent_config)

        logger.info("Registered custom subagent: %s", name)
        return agent_config
