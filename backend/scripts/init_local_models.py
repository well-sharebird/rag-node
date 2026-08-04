"""
初始化本地 Xinference 模型配置脚本
配置 embedding 和 rerank 模型
"""
from sqlalchemy import select
from app.core.database import get_sync_db
from app.models.model_gateway import ModelProvider
from app.models.model_config import ModelConfig

def init_local_models():
    """初始化本地 Xinference 模型配置"""

    db = next(get_sync_db())

    try:
        # =============================================================================
        # 1. 创建 ModelProvider - Xinference 本地服务
        # =============================================================================
        provider = db.execute(
            select(ModelProvider).where(ModelProvider.code == "xinference")
        ).scalar_one_or_none()

        if not provider:
            provider = ModelProvider(
                name="Xinference 本地服务",
                code="xinference",
                description="本地部署的 Xinference 模型推理服务",
                provider_type="self_hosted",
                region="local",
                base_url="http://1.181.141.96:6018/xinference220/v1",
                api_version=None,
                auth_type="api_key",
                api_key="not_required",  # Xinference 本地服务通常不需要 API Key
                api_key_name="X-API-Key",
                config={
                    "supports_embedding": True,
                    "supports_rerank": True,
                    "supports_llm": True,
                },
                is_enabled=True,
                is_default=True,
                status="active",
            )
            db.add(provider)
            db.commit()
            db.refresh(provider)
            print(f"✓ 创建 ModelProvider: {provider.name} ({provider.code})")
        else:
            # 更新现有配置
            provider.base_url = "http://1.181.141.96:6018/xinference220/v1"
            provider.is_enabled = True
            provider.is_default = True
            db.commit()
            print(f"✓ 更新 ModelProvider: {provider.name}")

        # =============================================================================
        # 2. 创建 Embedding Model Config - bge-large-zh-v1.5
        # =============================================================================
        embedding_model = db.execute(
            select(ModelConfig).where(
                ModelConfig.model_type == "embedding",
                ModelConfig.model_id == "bge-large-zh-v1.5"
            )
        ).scalar_one_or_none()

        if not embedding_model:
            embedding_model = ModelConfig(
                name="BGE Large Chinese v1.5",
                model_id="bge-large-zh-v1.5",
                model_type="embedding",
                adapter_type="api",  # Xinference 使用 OpenAI 兼容 API
                provider="xinference",
                description="智源研究院的中文向量模型，适用于中文文本嵌入",
                embedding_dim=1024,
                normalization=True,
                batch_size=32,
                timeout_ms=30000,
                status="active",
                is_default=True,
                is_enabled=True,
                tags='["chinese", "embedding", "bge", "xinference"]',
                metadata_json={
                    "vendor": "BAAI",
                    "language": "zh",
                    "max_seq_length": 512,
                    "similarity_metric": "cosine",
                },
            )
            db.add(embedding_model)
            print(f"✓ 创建 Embedding Model: {embedding_model.name}")
        else:
            embedding_model.is_enabled = True
            embedding_model.is_default = True
            embedding_model.status = "active"
            print(f"✓ 更新 Embedding Model: {embedding_model.name}")

        # =============================================================================
        # 3. 创建 Rerank Model Config - bge-reranker-large
        # =============================================================================
        rerank_model = db.execute(
            select(ModelConfig).where(
                ModelConfig.model_type == "rerank",
                ModelConfig.model_id == "bge-reranker-large"
            )
        ).scalar_one_or_none()

        if not rerank_model:
            rerank_model = ModelConfig(
                name="BGE Reranker Large",
                model_id="bge-reranker-large",
                model_type="rerank",
                adapter_type="api",  # Xinference 使用 OpenAI 兼容 API
                provider="xinference",
                description="智源研究院的重排序模型，用于检索结果重排序",
                embedding_dim=None,
                normalization=True,
                batch_size=32,
                timeout_ms=30000,
                status="active",
                is_default=True,
                is_enabled=True,
                tags='["chinese", "rerank", "bge", "xinference"]',
                metadata_json={
                    "vendor": "BAAI",
                    "language": "zh",
                    "max_seq_length": 512,
                    "similarity_metric": "score",
                },
            )
            db.add(rerank_model)
            print(f"✓ 创建 Rerank Model: {rerank_model.name}")
        else:
            rerank_model.is_enabled = True
            rerank_model.is_default = True
            rerank_model.status = "active"
            print(f"✓ 更新 Rerank Model: {rerank_model.name}")

        db.commit()

        # =============================================================================
        # 打印配置摘要
        # =============================================================================
        print("\n" + "=" * 60)
        print("模型配置完成!")
        print("=" * 60)

        providers = db.execute(select(ModelProvider)).scalars().all()
        print(f"\nModel Providers ({len(providers)}):")
        for p in providers:
            print(f"  - {p.name}: {p.base_url}")

        models = db.execute(
            select(ModelConfig).order_by(ModelConfig.model_type, ModelConfig.name)
        ).scalars().all()
        print(f"\nModel Configs ({len(models)}):")
        for m in models:
            print(f"  [{m.model_type:10s}] {m.name:25s} model_id={m.model_id}")

    except Exception as e:
        db.rollback()
        print(f"✗ 错误：{e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    init_local_models()
