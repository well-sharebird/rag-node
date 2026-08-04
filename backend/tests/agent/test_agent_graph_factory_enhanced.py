"""
Agent Graph Factory 增强测试
测试 Phase 4 新增的工厂模式功能：
1. 并行执行
2. 条件分支
3. 循环和重试
4. 子图嵌套
5. 预定义节点函数
"""
import asyncio
import sys
import uuid
from datetime import datetime

sys.path.insert(0, '.')

from typing import Any, Dict, List
from langchain_core.messages import HumanMessage, AIMessage

from app.services.agent_graph_factory import (
    StateGraphBuilder,
    WorkflowState,
    create_llm_node,
    create_tool_node,
    create_router_node,
)


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


class MockDB:
    """模拟数据库"""

    async def execute(self, query):
        class Result:
            def scalar_one_or_none(self):
                return None
        return Result()


async def test_parallel_workflow():
    """测试并行执行工作流"""
    print("=" * 70)
    print("工厂模式增强测试 - 并行执行")
    print("=" * 70)

    # 创建模拟的并行节点（使用不同的输出键避免并发冲突）
    async def expert_a(state: WorkflowState):
        """专家 A 节点"""
        return {
            "context": {**state.get("context", {}), "expert_a_result": "回答 A"},
        }

    async def expert_b(state: WorkflowState):
        """专家 B 节点"""
        return {
            "context": {**state.get("context", {}), "expert_b_result": "回答 B"},
        }

    async def expert_c(state: WorkflowState):
        """专家 C 节点"""
        return {
            "context": {**state.get("context", {}), "expert_c_result": "回答 C"},
        }

    def aggregator(state: WorkflowState):
        """聚合函数"""
        ctx = state.get("context", {})
        results = [ctx.get(k, "") for k in ["expert_a_result", "expert_b_result", "expert_c_result"]]
        combined = "\n\n".join([r for r in results if r])
        return {
            "messages": state.get("messages", []) + [AIMessage(content=combined)],
            "current_step": "aggregated",
        }

    try:
        builder = StateGraphBuilder(
            model_gateway=MockModelGateway(),
            skill_registry=MockSkillRegistry(),
            db=MockDB(),
        )

        graph = await builder.build_parallel_workflow(
            name="parallel_experts",
            parallel_nodes={
                "expert_a": expert_a,
                "expert_b": expert_b,
                "expert_c": expert_c,
            },
            aggregator=aggregator,
            model_config=await MockModelGateway().get_model_by_name("qwen3.5-397b-a17b"),
            system_prompt="你是专家助手。",
        )

        # 执行测试
        result = await graph.ainvoke({
            "messages": [HumanMessage(content="请分析这个问题")],
            "context": {},
        })

        print(f"✓ 并行执行工作流创建成功")
        print(f"  图已编译：{graph is not None}")
        print(f"  执行结果：{result.get('current_step', 'N/A')}")
        print(f"  聚合结果：{len(result.get('messages', []))} 条消息")

    except Exception as e:
        print(f"✗ 测试失败：{e}")
        import traceback
        traceback.print_exc()


async def test_conditional_workflow():
    """测试条件分支工作流"""
    print("\n" + "=" * 70)
    print("工厂模式增强测试 - 条件分支")
    print("=" * 70)

    # 定义条件判断函数
    def condition_func(state: WorkflowState):
        """根据问题类型选择分支"""
        messages = state.get("messages", [])
        if messages:
            content = str(messages[-1].content).lower()
            if "code" in content or "编程" in content:
                return {"branch": "code_review"}
            elif "write" in content or "文档" in content:
                return {"branch": "doc_write"}
        return {"branch": "default"}

    # 定义各分支的节点（使用不同的输出键避免并发冲突）
    async def code_review_node(state: WorkflowState):
        return {"context": {**state.get("context", {}), "branch_result": "code_review"}}

    async def doc_write_node(state: WorkflowState):
        return {"context": {**state.get("context", {}), "branch_result": "doc_write"}}

    async def default_node(state: WorkflowState):
        return {"context": {**state.get("context", {}), "branch_result": "default"}}

    try:
        builder = StateGraphBuilder(
            model_gateway=MockModelGateway(),
            skill_registry=MockSkillRegistry(),
            db=MockDB(),
        )

        graph = await builder.build_conditional_workflow(
            name="conditional_router",
            branches={
                "code_review": {
                    "nodes": {"review": code_review_node},
                    "start_nodes": ["review"],
                    "end_nodes": ["review"],
                },
                "doc_write": {
                    "nodes": {"write": doc_write_node},
                    "start_nodes": ["write"],
                    "end_nodes": ["write"],
                },
                "default": {
                    "nodes": {"handle": default_node},
                    "start_nodes": ["handle"],
                    "end_nodes": ["handle"],
                },
            },
            condition_func=condition_func,
            model_config=await MockModelGateway().get_model_by_name("qwen3.5-397b-a17b"),
            system_prompt="你是路由助手。",
        )

        # 测试代码相关问题
        result_code = await graph.ainvoke({
            "messages": [HumanMessage(content="请审查这段代码")],
            "context": {},
        })
        print(f"✓ 条件分支工作流创建成功")
        print(f"  代码问题路由：{result_code.get('context', {}).get('branch_result', 'N/A')}")

        # 测试文档相关问题
        result_doc = await graph.ainvoke({
            "messages": [HumanMessage(content="请帮我写文档")],
            "context": {},
        })
        print(f"  文档问题路由：{result_doc.get('context', {}).get('branch_result', 'N/A')}")

    except Exception as e:
        print(f"✗ 测试失败：{e}")
        import traceback
        traceback.print_exc()


async def test_loop_workflow():
    """测试循环工作流"""
    print("\n" + "=" * 70)
    print("工厂模式增强测试 - 循环和重试")
    print("=" * 70)

    iteration_count = 0
    max_test_iterations = 3

    async def loop_body(state: WorkflowState):
        """循环体：模拟代码生成和审查"""
        nonlocal iteration_count
        iteration_count += 1

        current_code = state.get("context", {}).get("current_code", "")
        return {
            "context": {
                **state.get("context", {}),
                "current_code": f"代码版本 v{iteration_count}",
                "should_continue": iteration_count < max_test_iterations,
            },
            "loop_count": iteration_count,
        }

    def condition_func(state: WorkflowState):
        """继续条件"""
        return state.get("context", {}).get("should_continue", False)

    try:
        builder = StateGraphBuilder(
            model_gateway=MockModelGateway(),
            skill_registry=MockSkillRegistry(),
            db=MockDB(),
        )

        graph = await builder.build_loop_workflow(
            name="code_review_loop",
            loop_body=loop_body,
            condition_func=condition_func,
            max_iterations=5,
        )

        # 执行测试
        result = await graph.ainvoke({
            "messages": [HumanMessage(content="生成代码")],
            "context": {"current_code": ""},
        })

        print(f"✓ 循环工作流创建成功")
        print(f"  最终循环次数：{result.get('loop_count', 'N/A')}")
        print(f"  最终状态：{result.get('current_step', 'N/A')}")
        print(f"  代码版本：{result.get('context', {}).get('current_code', 'N/A')}")

    except Exception as e:
        print(f"✗ 测试失败：{e}")
        import traceback
        traceback.print_exc()


async def test_nested_workflow():
    """测试嵌套子图工作流"""
    print("\n" + "=" * 70)
    print("工厂模式增强测试 - 子图嵌套")
    print("=" * 70)

    try:
        builder = StateGraphBuilder(
            model_gateway=MockModelGateway(),
            skill_registry=MockSkillRegistry(),
            db=MockDB(),
        )

        # 创建子图 1：分析阶段
        subgraph1 = await builder.build_custom_workflow(
            name="analysis_phase",
            nodes={
                "analyze": lambda s: {"context": {**s.get("context", {}), "analyzed": True}},
            },
            edges=[("analyze", "END")],
            model_config=await MockModelGateway().get_model_by_name("qwen3.5-397b-a17b"),
            system_prompt="分析助手",
        )

        # 创建子图 2：执行阶段
        subgraph2 = await builder.build_custom_workflow(
            name="execution_phase",
            nodes={
                "execute": lambda s: {"context": {**s.get("context", {}), "executed": True}},
            },
            edges=[("execute", "END")],
            model_config=await MockModelGateway().get_model_by_name("qwen3.5-397b-a17b"),
            system_prompt="执行助手",
        )

        # 注册子图
        builder.register_subgraph("analysis", subgraph1)
        builder.register_subgraph("execution", subgraph2)

        # 创建嵌套工作流
        graph = await builder.build_nested_workflow(
            name="nested_pipeline",
            subgraphs={
                "analyze_step": "analysis",
                "execute_step": "execution",
            },
            entry_points={},
        )

        # 执行测试
        result = await graph.ainvoke({
            "messages": [HumanMessage(content="执行任务")],
            "context": {},
        })

        print(f"✓ 嵌套子图工作流创建成功")
        print(f"  子图注册数：{len(builder._subgraph_cache)}")
        print(f"  执行结果：analyzed={result.get('context', {}).get('analyzed', False)}, executed={result.get('context', {}).get('executed', False)}")

    except Exception as e:
        print(f"✗ 测试失败：{e}")
        import traceback
        traceback.print_exc()


async def test_predefined_nodes():
    """测试预定义节点函数"""
    print("\n" + "=" * 70)
    print("工厂模式增强测试 - 预定义节点函数")
    print("=" * 70)

    try:
        # 测试 create_llm_node
        from langchain_core.language_models.fake import FakeListLLM

        fake_llm = FakeListLLM(responses=["LLM 响应"])
        llm_node = create_llm_node(fake_llm, "系统提示", "test_llm")

        result = await llm_node({
            "messages": [HumanMessage(content="你好")],
            "context": {},
        })

        print(f"✓ create_llm_node 测试通过")
        print(f"  节点返回消息数：{len(result.get('messages', []))}")

        # 测试 create_tool_node
        async def mock_tool(messages, context):
            return "工具执行结果"

        tool_node = create_tool_node(mock_tool, "test_tool")
        result = await tool_node({
            "messages": [HumanMessage(content="使用工具")],
            "context": {},
        })

        print(f"✓ create_tool_node 测试通过")
        print(f"  工具返回：{result.get('messages', [])[-1].content if result.get('messages') else 'N/A'}")

        # 测试 create_router_node
        async def route_func(state):
            return "route_a"

        router_node = create_router_node(route_func, {"route_a": "node_a", "route_b": "node_b"})
        result = await router_node({
            "messages": [],
            "context": {},
        })

        print(f"✓ create_router_node 测试通过")
        print(f"  路由结果：{result.get('current_step', 'N/A')}")

    except Exception as e:
        print(f"✗ 测试失败：{e}")
        import traceback
        traceback.print_exc()


async def main():
    """运行所有测试"""
    await test_parallel_workflow()
    await test_conditional_workflow()
    await test_loop_workflow()
    await test_nested_workflow()
    await test_predefined_nodes()

    print("\n" + "=" * 70)
    print("工厂模式增强测试完成")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
