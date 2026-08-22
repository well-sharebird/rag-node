"""
测试 /execute/stream 接口返回数据的完整性
"""
import asyncio
import json
import aiohttp
from datetime import datetime

API_BASE_URL = "http://localhost:8000"  # 根据实际情况修改

async def test_execute_stream():
    """测试执行流接口"""
    query = "你可以帮我生成一个 doc 文件吗"
    
    # 准备请求数据
    payload = {
        "query": query,
        "agent_id": 1,  # 根据实际情况修改
        "session_id": None,
    }
    
    print(f"🚀 开始测试接口：{API_BASE_URL}/execute/stream")
    print(f"📝 查询内容：{query}")
    print(f"⏰ 测试时间：{datetime.now().isoformat()}")
    print("=" * 80)
    
    # 保存所有事件的列表
    all_events = []
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{API_BASE_URL}/execute/stream",
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                print(f"📡 响应状态码：{response.status}")
                print(f"📡 响应头：{dict(response.headers)}")
                print("=" * 80)
                
                # 逐行读取 SSE 流
                line_num = 0
                reasoning_count = 0
                token_count = 0
                reasoning_content = ""
                token_content = ""
                
                async for line in response.content:
                    line = line.decode('utf-8').strip()
                    line_num += 1
                    
                    # 跳过空行和注释
                    if not line or line.startswith(':'):
                        continue
                    
                    # 解析 SSE 数据
                    if line.startswith('data: '):
                        data_str = line[6:]  # 去掉 'data: ' 前缀
                        
                        try:
                            event = json.loads(data_str)
                            all_events.append(event)
                            
                            # 打印事件详情
                            event_type = event.get('type', 'unknown')
                            
                            if event_type == 'reasoning':
                                reasoning_count += 1
                                content = event.get('content', '')
                                reasoning_content += content
                                print(f"📦 事件 {line_num}: [reasoning] 长度={len(content)}, 累计={len(reasoning_content)}")
                                print(f"   内容：{content[:100]}{'...' if len(content) > 100 else ''}")
                                
                            elif event_type == 'token':
                                token_count += 1
                                content = event.get('content', '')
                                token_content += content
                                print(f"📦 事件 {line_num}: [token] 长度={len(content)}, 累计={len(token_content)}")
                                print(f"   内容：{content[:100]}{'...' if len(content) > 100 else ''}")
                                
                            elif event_type == 'done':
                                data = event.get('data', {})
                                print(f"📦 事件 {line_num}: [done]")
                                print(f"   reason={data.get('reason')}, rounds={data.get('rounds')}")
                                print(f"   tools_used={data.get('tools_used')}, files={data.get('files')}")
                                
                            elif event_type == 'tool_event':
                                data = event.get('data', {})
                                print(f"📦 事件 {line_num}: [tool_event] phase={data.get('phase')}, tool={data.get('tool')}")
                                
                            else:
                                print(f"📦 事件 {line_num}: [{event_type}]")
                                
                        except json.JSONDecodeError as e:
                            print(f"❌ 事件 {line_num}: JSON 解析失败 - {e}")
                            print(f"   原始数据：{data_str[:200]}")
                    
                print("=" * 80)
                print(f"✅ 总共接收 {line_num} 行，{len(all_events)} 个事件")
                print(f"✅ reasoning 事件：{reasoning_count} 个，总长度：{len(reasoning_content)}")
                print(f"✅ token 事件：{token_count} 个，总长度：{len(token_content)}")
                
    except Exception as e:
        print(f"❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
    
    # 保存到文件
    output_file = f"api_response_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "metadata": {
                "query": query,
                "test_time": datetime.now().isoformat(),
                "api_url": f"{API_BASE_URL}/execute/stream",
                "total_events": len(all_events),
                "reasoning_count": reasoning_count,
                "token_count": token_count,
                "reasoning_total_length": len(reasoning_content),
                "token_total_length": len(token_content),
            },
            "events": all_events,
            "summary": {
                "complete_reasoning": reasoning_content,
                "complete_token": token_content,
            }
        }, f, ensure_ascii=False, indent=2)
    
    print(f"💾 完整响应已保存到：{output_file}")
    print(f"📊 文件大小：{len(json.dumps(all_events, ensure_ascii=False))} 字节")
    
    return all_events

if __name__ == "__main__":
    asyncio.run(test_execute_stream())
