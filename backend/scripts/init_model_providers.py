"""
初始化模型供应商数据脚本
主流 LLM 云厂商的 API 接口地址内置配置

Usage:
    cd backend
    uv run python scripts/init_model_providers.py
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.core.database import async_session_factory, engine
from app.models.model_gateway import ModelProvider


# 主流 LLM 云厂商配置
MODEL_PROVIDERS_DATA = [
    # ========== 国际云服务 ==========
    {
        "name": "OpenAI",
        "code": "openai",
        "description": "OpenAI GPT 系列模型（GPT-4, GPT-4o, GPT-4o-mini, o1 等）",
        "provider_type": "cloud",
        "region": "international",
        "base_url": "https://api.openai.com/v1",
        "api_version": None,
        "auth_type": "api_key",
        "api_key_name": "Authorization",
        "is_enabled": True,
        "is_default": False,
        "status": "active",
        "cost_input": 0.005,  # $5/1M tokens (GPT-4o mini 参考)
        "cost_output": 0.015,
        "metadata_json": {
            "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4", "o1-preview", "o1-mini"],
            "website": "https://platform.openai.com",
            "docs": "https://platform.openai.com/docs"
        }
    },
    {
        "name": "Anthropic",
        "code": "anthropic",
        "description": "Anthropic Claude 系列模型（Claude 3.5 Sonnet, Claude 3 Opus 等）",
        "provider_type": "cloud",
        "region": "international",
        "base_url": "https://api.anthropic.com",
        "api_version": "2023-06-01",
        "auth_type": "api_key",
        "api_key_name": "x-api-key",
        "is_enabled": True,
        "is_default": False,
        "status": "active",
        "cost_input": 0.003,  # $3/1M tokens (Claude 3.5 Sonnet 参考)
        "cost_output": 0.015,
        "metadata_json": {
            "models": ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229", "claude-3-haiku-20240307"],
            "website": "https://anthropic.com",
            "docs": "https://docs.anthropic.com"
        }
    },
    {
        "name": "Google AI",
        "code": "google",
        "description": "Google Gemini 系列模型",
        "provider_type": "cloud",
        "region": "international",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "api_version": None,
        "auth_type": "api_key",
        "api_key_name": "Authorization",
        "is_enabled": True,
        "is_default": False,
        "status": "active",
        "cost_input": 0.000125,  # $0.125/1M tokens (Gemini 1.5 Flash 参考)
        "cost_output": 0.0005,
        "metadata_json": {
            "models": ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash"],
            "website": "https://ai.google",
            "docs": "https://ai.google.dev"
        }
    },
    {
        "name": "Azure OpenAI",
        "code": "azure",
        "description": "Microsoft Azure OpenAI Service（中国区由世纪互联运营）",
        "provider_type": "cloud",
        "region": "international",
        "base_url": "https://{resource}.openai.azure.com",
        "api_version": "2024-08-01-preview",
        "auth_type": "azure_ad",
        "api_key_name": "api-key",
        "is_enabled": True,
        "is_default": False,
        "status": "active",
        "cost_input": 0.003,
        "cost_output": 0.015,
        "metadata_json": {
            "models": ["gpt-4o", "gpt-4", "gpt-35-turbo"],
            "website": "https://azure.microsoft.com/products/ai-services/openai-service",
            "docs": "https://learn.microsoft.com/azure/ai-services/openai",
            "note": "需要将 {resource} 替换为你的 Azure 资源名称"
        }
    },
    {
        "name": "AWS Bedrock",
        "code": "aws",
        "description": "Amazon Bedrock - 托管的 foundation models 服务",
        "provider_type": "cloud",
        "region": "international",
        "base_url": "https://bedrock-runtime.{region}.amazonaws.com",
        "api_version": None,
        "auth_type": "aws_sigv4",
        "api_key_name": None,
        "is_enabled": True,
        "is_default": False,
        "status": "active",
        "cost_input": 0.003,
        "cost_output": 0.015,
        "metadata_json": {
            "models": ["anthropic.claude-3-5-sonnet", "meta.llama3-70b", "ai21.j2-mid"],
            "website": "https://aws.amazon.com/bedrock",
            "docs": "https://docs.aws.amazon.com/bedrock",
            "note": "需要将 {region} 替换为你的 AWS 区域"
        }
    },
    {
        "name": "Cohere",
        "code": "cohere",
        "description": "Cohere - 企业级 NLP 模型（Command, Embed 等）",
        "provider_type": "cloud",
        "region": "international",
        "base_url": "https://api.cohere.ai/v1",
        "api_version": None,
        "auth_type": "api_key",
        "api_key_name": "Authorization",
        "is_enabled": True,
        "is_default": False,
        "status": "active",
        "cost_input": 0.0005,
        "cost_output": 0.001,
        "metadata_json": {
            "models": ["command-r-plus", "command-r", "embed-english-v3.0"],
            "website": "https://cohere.com",
            "docs": "https://docs.cohere.com"
        }
    },

    # ========== 国内云服务 ==========
    {
        "name": "智谱 AI",
        "code": "zhipu",
        "description": "智谱 AI - GLM 系列模型（GLM-4, GLM-3-Turbo 等）",
        "provider_type": "domestic",
        "region": "china",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "api_version": None,
        "auth_type": "api_key",
        "api_key_name": "Authorization",
        "is_enabled": True,
        "is_default": False,
        "status": "active",
        "cost_input": 0.001,  # ￥0.01/1K tokens (GLM-4 参考)
        "cost_output": 0.001,
        "metadata_json": {
            "models": ["glm-4", "glm-4-air", "glm-4-flash", "glm-3-turbo"],
            "website": "https://www.zhipuai.cn",
            "docs": "https://open.bigmodel.cn/dev/api"
        }
    },
    {
        "name": "月之暗面 (Kimi)",
        "code": "moonshot",
        "description": "月之暗面 Kimi - 超长上下文模型",
        "provider_type": "domestic",
        "region": "china",
        "base_url": "https://api.moonshot.cn/v1",
        "api_version": None,
        "auth_type": "api_key",
        "api_key_name": "Authorization",
        "is_enabled": True,
        "is_default": False,
        "status": "active",
        "cost_input": 0.012,  # ￥0.012/1K tokens (Kimi Plus 参考)
        "cost_output": 0.012,
        "metadata_json": {
            "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
            "website": "https://www.moonshot.cn",
            "docs": "https://platform.moonshot.cn/docs"
        }
    },
    {
        "name": "阿里云百炼",
        "code": "aliyun",
        "description": "阿里云百炼 - 通义千问系列模型",
        "provider_type": "domestic",
        "region": "china",
        "base_url": "https://dashscope.aliyuncs.com/api/v1",
        "api_version": None,
        "auth_type": "api_key",
        "api_key_name": "Authorization",
        "is_enabled": True,
        "is_default": False,
        "status": "active",
        "cost_input": 0.002,  # ￥0.002/1K tokens (Qwen-Turbo 参考)
        "cost_output": 0.006,
        "metadata_json": {
            "models": ["qwen-turbo", "qwen-plus", "qwen-max", "qwen-vl-max"],
            "website": "https://www.aliyun.com/product/bailian",
            "docs": "https://help.aliyun.com/product/42154"
        }
    },
    {
        "name": "百川智能",
        "code": "baichuan",
        "description": "百川智能 - Baichuan 系列模型",
        "provider_type": "domestic",
        "region": "china",
        "base_url": "https://api.baichuan-ai.com/v1",
        "api_version": None,
        "auth_type": "api_key",
        "api_key_name": "Authorization",
        "is_enabled": True,
        "is_default": False,
        "status": "active",
        "cost_input": 0.012,
        "cost_output": 0.012,
        "metadata_json": {
            "models": ["Baichuan4", "Baichuan3-Turbo", "Baichuan2-53B"],
            "website": "https://www.baichuan-ai.com",
            "docs": "https://platform.baichuan-ai.com"
        }
    },
    {
        "name": "MiniMax",
        "code": "minimax",
        "description": "MiniMax - ABAB 系列模型",
        "provider_type": "domestic",
        "region": "china",
        "base_url": "https://api.minimax.chat/v1",
        "api_version": None,
        "auth_type": "api_key",
        "api_key_name": "Authorization",
        "is_enabled": True,
        "is_default": False,
        "status": "active",
        "cost_input": 0.01,
        "cost_output": 0.01,
        "metadata_json": {
            "models": ["abab6.5-chat", "abab6-chat", "abab5.5-chat"],
            "website": "https://www.minimaxi.com",
            "docs": "https://platform.minimaxi.com"
        }
    },
    {
        "name": "零一万物",
        "code": "01ai",
        "description": "零一万物 - Yi 系列模型",
        "provider_type": "domestic",
        "region": "china",
        "base_url": "https://api.lingyiwanwu.com/v1",
        "api_version": None,
        "auth_type": "api_key",
        "api_key_name": "Authorization",
        "is_enabled": True,
        "is_default": False,
        "status": "active",
        "cost_input": 0.005,
        "cost_output": 0.005,
        "metadata_json": {
            "models": ["yi-large", "yi-medium", "yi-spark"],
            "website": "https://www.lingyiwanwu.com",
            "docs": "https://platform.lingyiwanwu.com"
        }
    },
    {
        "name": "DeepSeek (深度求索)",
        "code": "deepseek",
        "description": "DeepSeek - 深度求索大模型",
        "provider_type": "domestic",
        "region": "china",
        "base_url": "https://api.deepseek.com/v1",
        "api_version": None,
        "auth_type": "api_key",
        "api_key_name": "Authorization",
        "is_enabled": True,
        "is_default": False,
        "status": "active",
        "cost_input": 0.001,
        "cost_output": 0.002,
        "metadata_json": {
            "models": ["deepseek-chat", "deepseek-coder"],
            "website": "https://www.deepseek.com",
            "docs": "https://platform.deepseek.com"
        }
    },
    {
        "name": "步惊云 (StepFun)",
        "code": "stepfun",
        "description": "步惊云 - 阶梯系列模型",
        "provider_type": "domestic",
        "region": "china",
        "base_url": "https://api.stepfun.com/v1",
        "api_version": None,
        "auth_type": "api_key",
        "api_key_name": "Authorization",
        "is_enabled": True,
        "is_default": False,
        "status": "active",
        "cost_input": 0.005,
        "cost_output": 0.005,
        "metadata_json": {
            "models": ["step-1-8k", "step-1-32k", "step-1-128k"],
            "website": "https://www.stepfun.com",
            "docs": "https://platform.stepfun.com"
        }
    },

    # ========== 自托管服务 ==========
    {
        "name": "Ollama",
        "code": "ollama",
        "description": "Ollama - 本地运行开源 LLM（Llama 3, Qwen2, Mistral 等）",
        "provider_type": "self_hosted",
        "region": None,
        "base_url": "http://localhost:11434",
        "api_version": None,
        "auth_type": "api_key",
        "api_key_name": None,
        "is_enabled": True,
        "is_default": False,
        "status": "active",
        "cost_input": 0,
        "cost_output": 0,
        "metadata_json": {
            "models": ["llama3.1", "qwen2.5", "mistral", "mixtral", "gemma2"],
            "website": "https://ollama.com",
            "docs": "https://github.com/ollama/ollama",
            "note": "本地部署，成本为 0"
        }
    },
    {
        "name": "vLLM",
        "code": "vllm",
        "description": "vLLM - 高性能开源 LLM 推理服务",
        "provider_type": "self_hosted",
        "region": None,
        "base_url": "http://localhost:8000/v1",
        "api_version": None,
        "auth_type": "api_key",
        "api_key_name": None,
        "is_enabled": True,
        "is_default": False,
        "status": "active",
        "cost_input": 0,
        "cost_output": 0,
        "metadata_json": {
            "models": ["*"],  # 支持任意 HuggingFace 模型
            "website": "https://vllm.ai",
            "docs": "https://docs.vllm.ai",
            "note": "兼容 OpenAI API 格式"
        }
    },
    {
        "name": "NVIDIA Triton",
        "code": "triton",
        "description": "NVIDIA Triton Inference Server",
        "provider_type": "self_hosted",
        "region": None,
        "base_url": "http://localhost:8001",
        "api_version": None,
        "auth_type": "api_key",
        "api_key_name": None,
        "is_enabled": True,
        "is_default": False,
        "status": "active",
        "cost_input": 0,
        "cost_output": 0,
        "metadata_json": {
            "models": ["*"],
            "website": "https://developer.nvidia.com/nvidia-triton-inference-server",
            "docs": "https://docs.nvidia.com/deeplearning/triton-inference-server"
        }
    },
    {
        "name": "LocalAI",
        "code": "localai",
        "description": "LocalAI - 本地自建的 OpenAI 兼容 API",
        "provider_type": "self_hosted",
        "region": None,
        "base_url": "http://localhost:8080/v1",
        "api_version": None,
        "auth_type": "api_key",
        "api_key_name": None,
        "is_enabled": True,
        "is_default": False,
        "status": "active",
        "cost_input": 0,
        "cost_output": 0,
        "metadata_json": {
            "models": ["*"],
            "website": "https://localai.io",
            "docs": "https://localai.io/basics/getting_started"
        }
    },
]


async def init_model_providers():
    """初始化模型供应商数据"""
    print("=" * 60)
    print("开始初始化模型供应商数据...")
    print("=" * 60)

    created_count = 0
    updated_count = 0
    skipped_count = 0

    async with async_session_factory() as session:
        for provider_data in MODEL_PROVIDERS_DATA:
            # 检查是否已存在
            result = await session.execute(
                select(ModelProvider).where(ModelProvider.code == provider_data["code"])
            )
            existing = result.scalar_one_or_none()

            if existing:
                # 更新现有供应商（只更新非空字段）
                for key, value in provider_data.items():
                    if hasattr(existing, key) and key not in ["code"]:  # 不更新 code
                        setattr(existing, key, value)
                updated_count += 1
                print(f"  [更新] {provider_data['name']} ({provider_data['code']})")
            else:
                # 创建新供应商
                provider = ModelProvider(**provider_data)
                session.add(provider)
                created_count += 1
                print(f"  [创建] {provider_data['name']} ({provider_data['code']})")

        await session.commit()

    print("=" * 60)
    print(f"初始化完成!")
    print(f"  - 新建：{created_count} 个")
    print(f"  - 更新：{updated_count} 个")
    print(f"  - 总计：{len(MODEL_PROVIDERS_DATA)} 个供应商配置")
    print("=" * 60)

    # 打印供应商分类统计
    by_type = {}
    for p in MODEL_PROVIDERS_DATA:
        t = p["provider_type"]
        by_type[t] = by_type.get(t, 0) + 1

    print("\n供应商分类统计:")
    type_names = {
        "cloud": "国际云服务",
        "domestic": "国内云服务",
        "self_hosted": "自托管服务"
    }
    for t, count in by_type.items():
        print(f"  - {type_names.get(t, t)}: {count} 个")


async def main():
    try:
        await init_model_providers()
        print("\n✓ 模型供应商初始化成功!")
        print("\n提示：")
        print("  1. 访问 /api/v1/model-gateway/providers 查看供应商列表")
        print("  2. 在前端 Model Gateway 页面配置 API Key")
        print("  3. 设置默认供应商后即可使用")
    except Exception as e:
        print(f"\n✗ 初始化失败：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
