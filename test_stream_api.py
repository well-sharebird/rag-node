import requests
import json
import os

# 调用后端接口
api_url = "http://1.181.141.96:8000/api/v1/agents/execute/stream"

# 获取 token（从环境变量或硬编码）
token = os.getenv("TEST_TOKEN", "your_token_here")

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}

payload = {
    "query": "1+1 等于多少？请思考后回答",
    "model_name": "qwen3.5-397b-a17b"
}

print(f"=== 测试后端流式接口 ===")
print(f"URL: {api_url}")
print(f"Query: {payload['query']}")
print()

reasoning_events = []
token_events = []
all_events = []

try:
    response = requests.post(api_url, headers=headers, json=payload, stream=True, timeout=60)
    print(f"HTTP 状态码：{response.status_code}")
    print()
    
    for line in response.iter_lines():
        if line:
            line_str = line.decode('utf-8')
            if line_str.startswith('data: '):
                data_str = line_str[6:]
                if data_str.strip() == '[DONE]':
                    print("\n=== [DONE] ===")
                    break
                try:
                    data = json.loads(data_str)
                    all_events.append(data)
                    
                    event_type = data.get('type')
                    if event_type == 'reasoning':
                        content = data.get('content', '')
                        reasoning_events.append(content)
                        print(f"[reasoning] {repr(content[:60])}")
                    elif event_type == 'token':
                        content = data.get('content', '')
                        token_events.append(content)
                        print(f"[token] {repr(content[:60])}")
                    elif event_type:
                        print(f"[{event_type}]")
                    
                except json.JSONDecodeError as e:
                    print(f"JSON 解析错误：{e}, 原始数据：{data_str[:100]}")
    
    print(f"\n=== 统计 ===")
    print(f"总事件数：{len(all_events)}")
    print(f"Reasoning 事件：{len(reasoning_events)} ({sum(len(c) for c in reasoning_events)} 字符)")
    print(f"Token 事件：{len(token_events)} ({sum(len(c) for c in token_events)} 字符)")
    
    # 检查 switching 点
    if reasoning_events and token_events:
        print(f"\n=== Switching 分析 ===")
        print(f"最后一个 reasoning: {repr(reasoning_events[-1][-30:])}")
        print(f"第一个 token: {repr(token_events[0][:30])}")
        
        # 检查是否有截断
        full_reasoning = ''.join(reasoning_events)
        full_content = ''.join(token_events)
        print(f"\n完整 reasoning 长度：{len(full_reasoning)}")
        print(f"完整 content 长度：{len(full_content)}")
        print(f"\n完整 reasoning 结尾：{repr(full_reasoning[-50:])}")
        print(f"\n完整 content 开头：{repr(full_content[:50])}")
    
    # 保存到文件
    with open('stream_output.json', 'w', encoding='utf-8') as f:
        json.dump({
            'all_events': all_events,
            'reasoning_events': reasoning_events,
            'token_events': token_events,
            'full_reasoning': ''.join(reasoning_events),
            'full_content': ''.join(token_events)
        }, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 数据已保存到 stream_output.json")
    
except Exception as e:
    print(f"请求失败：{e}")
    import traceback
    traceback.print_exc()
