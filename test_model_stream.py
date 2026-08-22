import asyncio
import json
import httpx

async def test_model_stream():
    """直接测试模型流式输出"""
    url = "http://127.0.0.1:8000/api/v1/models/qwen3.5-397b-a17b/chat/completions"
    
    payload = {
        "messages": [
            {"role": "user", "content": "1+1 等于多少？请思考后回答"}
        ],
        "stream": True
    }
    
    print("=== 测试模型流式输出 ===\n")
    
    reasoning_chunks = []
    content_chunks = []
    all_deltas = []
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream("POST", url, json=payload) as response:
            async for line in response.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data = line[6:].strip()
                if data == "[DONE]":
                    print("\n[DONE]")
                    break
                
                try:
                    obj = json.loads(data)
                    choices = obj.get("choices") or []
                    if not choices:
                        continue
                    
                    delta = choices[0].get("delta") or {}
                    all_deltas.append(delta)
                    
                    reason_text = delta.get("reasoning_content") or delta.get("reasoning")
                    answer_text = delta.get("content")
                    
                    if reason_text:
                        reasoning_chunks.append(reason_text)
                        print(f"[reasoning] {repr(reason_text[:50])}")
                    if answer_text:
                        content_chunks.append(answer_text)
                        print(f"[content] {repr(answer_text[:50])}")
                        
                except json.JSONDecodeError as e:
                    print(f"JSON 错误：{e}")
    
    print(f"\n=== 统计 ===")
    print(f"Total deltas: {len(all_deltas)}")
    print(f"Reasoning chunks: {len(reasoning_chunks)}, total={sum(len(c) for c in reasoning_chunks)} chars")
    print(f"Content chunks: {len(content_chunks)}, total={sum(len(c) for c in content_chunks)} chars")
    
    if reasoning_chunks:
        print(f"\nReasoning 结尾：{repr(''.join(reasoning_chunks)[-50:])}")
    if content_chunks:
        print(f"Content 开头：{repr(''.join(content_chunks)[:50])}")

if __name__ == "__main__":
    asyncio.run(test_model_stream())
