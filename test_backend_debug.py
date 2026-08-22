import asyncio
import logging
import sys

# 设置日志级别为 DEBUG
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

logger = logging.getLogger(__name__)

async def test_direct_answer():
    """直接测试 _direct_answer_stream 方法"""
    from packages.agent.orchestrator.graph import Orchestrator
    from packages.agent.models.agent import AgentConfig
    from packages.agent.schemas.chat import ModelConfig
    
    # 创建 Orchestrator 实例
    orchestrator = Orchestrator(
        user_id=1,
        db=None,
        config=type('Config', (), {'timeout_seconds': 120})()
    )
    
    # 测试查询
    query = "1+1 等于多少？请详细思考后回答"
    main_prompt = "你是通用助手。"
    
    print(f"\n=== 开始测试 _direct_answer_stream ===")
    print(f"Query: {query}\n")
    
    reasoning_chunks = []
    content_chunks = []
    
    try:
        async for kind, content in orchestrator._direct_answer_stream(
            query=query,
            main_prompt=main_prompt,
            main_agent_cfg=None,
            session_id="debug-test"
        ):
            if kind == "reasoning":
                reasoning_chunks.append(content)
                print(f"[reasoning] len={len(content)}, preview={repr(content[:50])}")
            elif kind == "content":
                content_chunks.append(content)
                print(f"[content] len={len(content)}, preview={repr(content[:50])}")
        
        print(f"\n=== 统计 ===")
        print(f"Reasoning chunks: {len(reasoning_chunks)}, total={sum(len(c) for c in reasoning_chunks)} chars")
        print(f"Content chunks: {len(content_chunks)}, total={sum(len(c) for c in content_chunks)} chars")
        
        if reasoning_chunks:
            print(f"\n完整 reasoning 结尾：{repr(''.join(reasoning_chunks)[-100:])}")
        if content_chunks:
            print(f"\n完整 content 开头：{repr(''.join(content_chunks)[:100])}")
            
    except Exception as e:
        logger.error(f"测试失败：{e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(test_direct_answer())
