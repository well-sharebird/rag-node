import requests
import json

# 直接调用模型 API
api_url = "http://1.181.141.96:6018/qwen3.5-397b-a17b/v1/chat/completions"
model_name = "qwen3.5-397b-a17b"

print(f"=== 直接调用模型 API ===")
print(f"URL: {api_url}")
print(f"Model: {model_name}")
print(f"问题：1+1 等于多少？请思考后回答\n")

headers = {"Content-Type": "application/json"}

payload = {
    "model": model_name,
    "messages": [{"role": "user", "content": "1+1 等于多少？请思考后回答"}],
    "stream": True,
    "stream_options": {"include_usage": True}
}

reasoning_chunks = []
content_chunks = []

try:
    response = requests.post(api_url, headers=headers, json=payload, stream=True, timeout=60)
    print(f"HTTP 状态码：{response.status_code}\n")
    
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
                    choices = data.get('choices', [])
                    if choices:
                        delta = choices[0].get('delta', {})
                        
                        # 检查 reasoning 字段
                        if 'reasoning' in delta and delta['reasoning']:
                            reasoning_chunks.append(delta['reasoning'])
                            print(f"[reasoning] {repr(delta['reasoning'][:80])}")
                        
                        # 检查 content 字段
                        if 'content' in delta and delta['content']:
                            content_chunks.append(delta['content'])
                            print(f"[content] {repr(delta['content'][:80])}")
                    
                except json.JSONDecodeError as e:
                    print(f"JSON 解析错误：{e}")
    
    print(f"\n=== 统计 ===")
    print(f"Reasoning chunks: {len(reasoning_chunks)} ({sum(len(c) for c in reasoning_chunks)} 字符)")
    print(f"Content chunks: {len(content_chunks)} ({sum(len(c) for c in content_chunks)} 字符)")
    
    full_reasoning = ''.join(reasoning_chunks)
    full_content = ''.join(content_chunks)
    
    print(f"\n=== 完整性检查 ===")
    print(f"完整 reasoning 结尾：{repr(full_reasoning[-100:])}")
    print(f"\n完整 content 开头：{repr(full_content[:100])}")
    print(f"完整 content 结尾：{repr(full_content[-100:])}")
    
    # 检查 reasoning 是否有结束标点
    has_end_punct = full_reasoning.rstrip().endswith(('。', '！', '？', '.', '!', '?', '…'))
    print(f"\nReasoning 有结束标点：{has_end_punct}")
    
except Exception as e:
    print(f"请求失败：{e}")
    import traceback
    traceback.print_exc()
