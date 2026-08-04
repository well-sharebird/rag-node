#!/usr/bin/env python3
"""Backend package migration script.

Moves all files from app/ to packages/{core,rag,model_gateway,prompt,agent}/
and updates all import paths from app.xxx to packages.xxx.

Usage: cd backend && python migrate_packages.py
"""

import os
import shutil
import re

BASE = os.path.dirname(os.path.abspath(__file__))

# ============================================================
# 1. FILE MAPPING: (old_relative_path, new_relative_path)
# ============================================================

FILE_MAPPING = {
    # --- Core package ---
    "app/config.py": "packages/core/config.py",
    "app/core/database.py": "packages/core/database.py",
    "app/core/auth.py": "packages/core/auth.py",
    "app/core/deps.py": "packages/core/deps.py",
    "app/core/logging_config.py": "packages/core/logging_config.py",
    "app/core/observability.py": "packages/core/observability.py",
    "app/core/security.py": "packages/core/security.py",
    "app/core/init_data.py": "packages/core/init_data.py",
    "app/core/init_db.py": "packages/core/init_db.py",
    "app/core/tracing.py": "packages/core/tracing.py",
    # Core infra
    "app/core/redis_client.py": "packages/core/infra/redis_client.py",
    "app/core/milvus_client.py": "packages/core/infra/milvus_client.py",
    "app/core/elasticsearch_client.py": "packages/core/infra/elasticsearch_client.py",
    "app/core/es_client.py": "packages/core/infra/es_client.py",
    "app/core/minio_client.py": "packages/core/infra/minio_client.py",
    "app/core/kafka_client.py": "packages/core/infra/kafka_client.py",
    "app/core/message_queue.py": "packages/core/infra/message_queue.py",
    "app/core/neo4j_client.py": "packages/core/infra/neo4j_client.py",
    "app/core/knowledge_graph.py": "packages/core/infra/knowledge_graph.py",
    "app/core/prometheus_client.py": "packages/core/infra/prometheus_client.py",
    # Core utils
    "app/utils/error_handlers.py": "packages/core/error_handlers.py",
    "app/utils/exceptions.py": "packages/core/exceptions.py",
    "app/utils/file_utils.py": "packages/core/file_utils.py",
    # Core models
    "app/models/base.py": "packages/core/base_model.py",
    "app/models/menu.py": "packages/core/system/models/menu.py",
    "app/models/department.py": "packages/core/system/models/department.py",
    "app/models/system_setting.py": "packages/core/system/models/system_setting.py",
    "app/models/user.py": "packages/core/system/models/user.py",
    # Core schemas
    "app/schemas/auth.py": "packages/core/system/schemas/auth.py",
    "app/schemas/dashboard.py": "packages/core/system/schemas/dashboard.py",
    "app/schemas/department.py": "packages/core/system/schemas/department.py",
    "app/schemas/menu.py": "packages/core/system/schemas/menu.py",
    "app/schemas/settings.py": "packages/core/system/schemas/settings.py",
    "app/schemas/user.py": "packages/core/system/schemas/user.py",
    # Core services
    "app/services/menu_service.py": "packages/core/system/services/menu_service.py",
    "app/services/department_service.py": "packages/core/system/services/department_service.py",
    "app/services/settings_service.py": "packages/core/system/services/settings_service.py",
    # Core API
    "app/api/v1/auth.py": "packages/core/system/api/auth.py",
    "app/api/v1/admin.py": "packages/core/system/api/admin.py",
    "app/api/v1/users.py": "packages/core/system/api/users.py",
    "app/api/v1/dashboard.py": "packages/core/system/api/dashboard.py",
    "app/api/v1/health.py": "packages/core/system/api/health.py",
    "app/api/v1/metrics.py": "packages/core/system/api/metrics.py",
    "app/api/v1/prometheus.py": "packages/core/system/api/prometheus.py",
    "app/api/v1/settings.py": "packages/core/system/api/settings.py",

    # --- RAG package ---
    "app/core/rag_config.py": "packages/rag/config.py",
    "app/core/fts_engine.py": "packages/rag/fts_engine.py",
    # RAG API
    "app/api/v1/knowledge_bases.py": "packages/rag/api/knowledge_bases.py",
    "app/api/v1/documents.py": "packages/rag/api/documents.py",
    "app/api/v1/retrieval.py": "packages/rag/api/retrieval.py",
    "app/api/v1/data_sources.py": "packages/rag/api/data_sources.py",
    "app/api/v1/evaluation.py": "packages/rag/api/evaluation.py",
    "app/api/v1/synonyms.py": "packages/rag/api/synonyms.py",
    "app/api/v1/desensitization.py": "packages/rag/api/desensitization.py",
    # RAG services
    "app/services/kb_service.py": "packages/rag/services/kb_service.py",
    "app/services/document_service.py": "packages/rag/services/document_service.py",
    "app/services/retrieval_service.py": "packages/rag/services/retrieval_service.py",
    "app/services/chunking_service.py": "packages/rag/services/chunking_service.py",
    "app/services/embedding_service.py": "packages/rag/services/embedding_service.py",
    "app/services/vector_store_service.py": "packages/rag/services/vector_store_service.py",
    "app/services/parsing_service.py": "packages/rag/services/parsing_service.py",
    "app/services/multi_index_service.py": "packages/rag/services/multi_index_service.py",
    "app/services/mmr_service.py": "packages/rag/services/mmr_service.py",
    "app/services/rrf_fusion.py": "packages/rag/services/rrf_fusion.py",
    "app/services/query_expansion.py": "packages/rag/services/query_expansion.py",
    "app/services/keyword_extraction_service.py": "packages/rag/services/keyword_extraction_service.py",
    "app/services/multi_modal_retrieval.py": "packages/rag/services/multi_modal_retrieval.py",
    "app/services/synonym_service.py": "packages/rag/services/synonym_service.py",
    "app/services/evaluation_service.py": "packages/rag/services/evaluation_service.py",
    "app/services/data_source_service.py": "packages/rag/services/data_source_service.py",
    "app/services/document_enrichment.py": "packages/rag/services/document_enrichment.py",
    "app/services/ingestion_validator.py": "packages/rag/services/ingestion_validator.py",
    "app/services/file_type_router.py": "packages/rag/services/file_type_router.py",
    "app/services/desensitization_service.py": "packages/rag/services/desensitization_service.py",
    # RAG models
    "app/models/knowledge_base.py": "packages/rag/models/knowledge_base.py",
    "app/models/document.py": "packages/rag/models/document.py",
    "app/models/data_source.py": "packages/rag/models/data_source.py",
    "app/models/synonym.py": "packages/rag/models/synonym.py",
    "app/models/evaluation.py": "packages/rag/models/evaluation.py",
    "app/models/desensitization_config.py": "packages/rag/models/desensitization_config.py",
    # RAG schemas
    "app/schemas/knowledge_base.py": "packages/rag/schemas/knowledge_base.py",
    "app/schemas/document.py": "packages/rag/schemas/document.py",
    "app/schemas/retrieval.py": "packages/rag/schemas/retrieval.py",
    "app/schemas/data_source.py": "packages/rag/schemas/data_source.py",
    "app/schemas/evaluation.py": "packages/rag/schemas/evaluation.py",
    "app/schemas/parsing.py": "packages/rag/schemas/parsing.py",
    # RAG connectors (entire directory)
    "app/connectors/__init__.py": "packages/rag/connectors/__init__.py",
    "app/connectors/base.py": "packages/rag/connectors/base.py",
    "app/connectors/factory.py": "packages/rag/connectors/factory.py",
    "app/connectors/api_connector.py": "packages/rag/connectors/api_connector.py",
    "app/connectors/web_connector.py": "packages/rag/connectors/web_connector.py",
    "app/connectors/database_connector.py": "packages/rag/connectors/database_connector.py",
    "app/connectors/confluence_connector.py": "packages/rag/connectors/confluence_connector.py",
    "app/connectors/git_connector.py": "packages/rag/connectors/git_connector.py",
    "app/connectors/notion_connector.py": "packages/rag/connectors/notion_connector.py",
    # RAG workers
    "app/workers/document_pipeline.py": "packages/rag/workers/document_pipeline.py",
    "app/workers/sync_engine.py": "packages/rag/workers/sync_engine.py",
    # RAG preprocessing
    "app/preprocessing/text_cleaner.py": "packages/rag/preprocessing/text_cleaner.py",

    # --- Model Gateway package ---
    "app/api/v1/models.py": "packages/model_gateway/api/models.py",
    "app/api/v1/model_gateway.py": "packages/model_gateway/api/model_gateway.py",
    "app/api/v1/token_usage.py": "packages/model_gateway/api/token_usage.py",
    # MG services
    "app/services/model_service.py": "packages/model_gateway/services/model_service.py",
    "app/services/model_config_service.py": "packages/model_gateway/services/model_config_service.py",
    "app/services/model_gateway_service.py": "packages/model_gateway/services/model_gateway_service.py",
    "app/services/model_health_monitor.py": "packages/model_gateway/services/model_health_monitor.py",
    "app/services/llm_service.py": "packages/model_gateway/services/llm_service.py",
    "app/services/llm_fallback_chain.py": "packages/model_gateway/services/llm_fallback_chain.py",
    "app/services/token_usage_service.py": "packages/model_gateway/services/token_usage_service.py",
    # MG models
    "app/models/model_config.py": "packages/model_gateway/models/model_config.py",
    "app/models/model_gateway.py": "packages/model_gateway/models/model_gateway.py",
    "app/models/token_usage.py": "packages/model_gateway/models/token_usage.py",
    # MG schemas
    "app/schemas/model.py": "packages/model_gateway/schemas/model.py",
    "app/schemas/model_gateway.py": "packages/model_gateway/schemas/model_gateway.py",
    "app/schemas/token_usage.py": "packages/model_gateway/schemas/token_usage.py",

    # --- Prompt package ---
    "app/api/v1/prompts.py": "packages/prompt/api/prompts.py",
    # Prompt services (prompt_template_service + prompt/ subdirectory)
    "app/services/prompt_template_service.py": "packages/prompt/services/prompt_template_service.py",
    "app/services/prompt/__init__.py": "packages/prompt/services/__init__.py",
    "app/services/prompt/registry.py": "packages/prompt/services/registry.py",
    "app/services/prompt/renderer.py": "packages/prompt/services/renderer.py",
    "app/services/prompt/evaluator.py": "packages/prompt/services/evaluator.py",
    "app/services/prompt/publisher.py": "packages/prompt/services/publisher.py",
    "app/services/prompt/audit.py": "packages/prompt/services/audit.py",
    # Prompt CLI
    "app/cli/prompt.py": "packages/prompt/cli/prompt.py",
    # Prompt models/schemas
    "app/models/prompt_template.py": "packages/prompt/models/prompt_template.py",
    "app/schemas/prompt.py": "packages/prompt/schemas/prompt.py",

    # --- Agent package ---
    "app/api/v1/agents.py": "packages/agent/api/agents.py",
    "app/api/v1/agent_runtime.py": "packages/agent/api/agent_runtime.py",
    "app/api/v1/conversations.py": "packages/agent/api/conversations.py",
    "app/api/v1/conversation_history.py": "packages/agent/api/conversation_history.py",
    "app/api/v1/feedback.py": "packages/agent/api/feedback.py",
    "app/api/v1/tracing.py": "packages/agent/api/tracing.py",
    "app/api/v1/chat.py": "packages/agent/api/chat.py",
    "app/api/v1/skills.py": "packages/agent/api/skills.py",
    # Agent services
    "app/services/agent_bootstrap.py": "packages/agent/services/agent_bootstrap.py",
    "app/services/agent_builder_service.py": "packages/agent/services/agent_builder_service.py",
    "app/services/agent_checkpoint_service.py": "packages/agent/services/agent_checkpoint_service.py",
    "app/services/agent_config_service.py": "packages/agent/services/agent_config_service.py",
    "app/services/agent_graph_factory.py": "packages/agent/services/agent_graph_factory.py",
    "app/services/agent_memory_service.py": "packages/agent/services/agent_memory_service.py",
    "app/services/agent_monitoring_service.py": "packages/agent/services/agent_monitoring_service.py",
    "app/services/agent_runtime_service.py": "packages/agent/services/agent_runtime_service.py",
    "app/services/agent_service.py": "packages/agent/services/agent_service.py",
    "app/services/conversation_archive_service.py": "packages/agent/services/conversation_archive_service.py",
    "app/services/conversation_memory.py": "packages/agent/services/conversation_memory.py",
    "app/services/conversation_service.py": "packages/agent/services/conversation_service.py",
    "app/services/feedback_service.py": "packages/agent/services/feedback_service.py",
    "app/services/trace_service.py": "packages/agent/services/trace_service.py",
    "app/services/skill_registry.py": "packages/agent/services/skill_registry.py",
    "app/services/skill_storage.py": "packages/agent/services/skill_storage.py",
    "app/services/version_manager.py": "packages/agent/services/version_manager.py",
    "app/services/stats_service.py": "packages/agent/services/stats_service.py",
    "app/services/subagent_service.py": "packages/agent/services/subagent_service.py",
    "app/services/lead_agent_factory.py": "packages/agent/services/lead_agent_factory.py",
    "app/services/meta_agent_service.py": "packages/agent/services/meta_agent_service.py",
    "app/services/intent_classifier.py": "packages/agent/services/intent_classifier.py",
    # Agent models
    "app/models/agent.py": "packages/agent/models/agent.py",
    "app/models/conversation.py": "packages/agent/models/conversation.py",
    "app/models/conversation_archive.py": "packages/agent/models/conversation_archive.py",
    "app/models/feedback.py": "packages/agent/models/feedback.py",
    "app/models/skill.py": "packages/agent/models/skill.py",
    # Agent schemas
    "app/schemas/chat.py": "packages/agent/schemas/chat.py",
    "app/schemas/conversation.py": "packages/agent/schemas/conversation.py",
    "app/schemas/skill.py": "packages/agent/schemas/skill.py",
    "app/schemas/feedback.py": "packages/agent/schemas/feedback.py",
    # Agent middlewares
    "app/agents/plan_middleware.py": "packages/agent/middlewares/plan_middleware.py",
    # Agent skills (entire directory)
    "app/skills/__init__.py": "packages/agent/skills/__init__.py",
    "app/skills/agent_tools.py": "packages/agent/skills/agent_tools.py",
    "app/skills/create_agent_skill.py": "packages/agent/skills/create_agent_skill.py",
    "app/skills/knowledge_base_tools.py": "packages/agent/skills/knowledge_base_tools.py",
    "app/skills/model_tools.py": "packages/agent/skills/model_tools.py",
    "app/skills/prompt_tools.py": "packages/agent/skills/prompt_tools.py",
    # Agent tools (entire directory)
    "app/tools/builtins.py": "packages/agent/tools/builtins.py",
    "app/tools/meta_agent_tools.py": "packages/agent/tools/meta_agent_tools.py",
    # Agent mcp (entire directory)
    "app/mcp_integration/__init__.py": "packages/agent/mcp/__init__.py",
    "app/mcp_integration/client.py": "packages/agent/mcp/client.py",
    "app/mcp_integration/config.py": "packages/agent/mcp/config.py",
    "app/mcp_integration/server.py": "packages/agent/mcp/server.py",
    "app/mcp_integration/tools/__init__.py": "packages/agent/mcp/tools/__init__.py",
    "app/mcp_integration/tools/agent_tools.py": "packages/agent/mcp/tools/agent_tools.py",
    "app/mcp_integration/tools/kb_tools.py": "packages/agent/mcp/tools/kb_tools.py",
    "app/mcp_integration/tools/model_tools.py": "packages/agent/mcp/tools/model_tools.py",
    "app/mcp_integration/tools/prompt_tools.py": "packages/agent/mcp/tools/prompt_tools.py",
    # Agent workers
    "app/workers/archive_scheduler.py": "packages/agent/workers/archive_scheduler.py",
    "app/workers/arq_worker.py": "packages/agent/workers/arq_worker.py",
}

# Files that stay in app/ (shell)
SHELL_FILES = {
    "app/__init__.py",
    "app/main.py",
    "app/api/__init__.py",
    "app/api/v1/__init__.py",
    "app/api/v1/router.py",
    "app/models/__init__.py",
}


def create_dirs():
    """Create all target directories with __init__.py."""
    dirs = set()
    for new_path in FILE_MAPPING.values():
        d = os.path.join(BASE, os.path.dirname(new_path))
        dirs.add(d)

    for d in sorted(dirs):
        os.makedirs(d, exist_ok=True)
        init_file = os.path.join(d, "__init__.py")
        if not os.path.exists(init_file):
            with open(init_file, "w") as f:
                f.write("")

    print(f"Created {len(dirs)} directories with __init__.py")


def move_files():
    """Move files from old to new locations."""
    moved = 0
    skipped = 0
    for old_rel, new_rel in FILE_MAPPING.items():
        old_path = os.path.join(BASE, old_rel)
        new_path = os.path.join(BASE, new_rel)

        if not os.path.exists(old_path):
            print(f"  SKIP (not found): {old_rel}")
            skipped += 1
            continue

        if os.path.exists(new_path):
            # Already moved, skip
            skipped += 1
            continue

        shutil.move(old_path, new_path)
        moved += 1

    print(f"Moved {moved} files, skipped {skipped}")


def build_module_mapping():
    """Build module path mapping from file mapping.

    Returns dict: old_module_path -> new_module_path
    e.g. "app.services.kb_service" -> "packages.rag.services.kb_service"
    """
    mapping = {}

    for old_rel, new_rel in FILE_MAPPING.items():
        # Skip __init__.py for now, handle separately
        if old_rel.endswith("__init__.py"):
            # Map the package path
            old_module = old_rel.replace("/", ".").replace("/__init__.py", "")
            new_module = new_rel.replace("/", ".").replace("/__init__.py", "")
            # But only if the __init__.py is not at the top level
            if old_module != "app":
                mapping[old_module] = new_module
            continue

        # Convert file path to module path
        old_module = old_rel.replace("/", ".").replace(".py", "")
        new_module = new_rel.replace("/", ".").replace(".py", "")
        mapping[old_module] = new_module

    # Special: app.config -> packages.core.config
    mapping["app.config"] = "packages.core.config"

    # Sort by key length descending (longest first to avoid partial matches)
    sorted_mapping = sorted(mapping.items(), key=lambda x: len(x[0]), reverse=True)

    return sorted_mapping


def update_imports():
    """Update all import paths in Python files."""
    module_mapping = build_module_mapping()

    # Collect all .py files to update (in packages/ and app/ and tests/ and alembic/)
    files_to_update = set()

    # All .py files in packages/
    for root, dirs, files in os.walk(os.path.join(BASE, "packages")):
        if "__pycache__" in root:
            continue
        for f in files:
            if f.endswith(".py"):
                files_to_update.add(os.path.join(root, f))

    # Shell files in app/
    for sf in SHELL_FILES:
        full = os.path.join(BASE, sf)
        if os.path.exists(full):
            files_to_update.add(full)

    # Test files
    tests_dir = os.path.join(BASE, "tests")
    if os.path.exists(tests_dir):
        for root, dirs, files in os.walk(tests_dir):
            if "__pycache__" in root:
                continue
            for f in files:
                if f.endswith(".py"):
                    files_to_update.add(os.path.join(root, f))

    # Alembic env.py
    alembic_env = os.path.join(BASE, "alembic", "env.py")
    if os.path.exists(alembic_env):
        files_to_update.add(alembic_env)

    # Conftest
    conftest = os.path.join(BASE, "tests", "conftest.py")
    if os.path.exists(conftest):
        files_to_update.add(conftest)

    updated_count = 0
    for filepath in sorted(files_to_update):
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        original = content

        for old_module, new_module in module_mapping:
            # Replace "from app.xxx import" -> "from packages.xxx import"
            content = content.replace(
                f"from {old_module} ",
                f"from {new_module} "
            )
            content = content.replace(
                f"from {old_module}.",
                f"from {new_module}."
            )
            # Replace "import app.xxx" -> "import packages.xxx"
            content = content.replace(
                f"import {old_module} ",
                f"import {new_module} "
            )
            content = content.replace(
                f"import {old_module}.",
                f"import {new_module}."
            )
            # Handle "from app.xxx import" at end of line
            content = content.replace(
                f"from {old_module}\n",
                f"from {new_module}\n"
            )

        if content != original:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            updated_count += 1

    print(f"Updated imports in {updated_count} files")


def cleanup_empty_dirs():
    """Remove empty directories in app/ (except shell dirs)."""
    removed = 0
    # Walk app/ bottom-up to remove empty dirs
    app_dir = os.path.join(BASE, "app")
    for root, dirs, files in os.walk(app_dir, topdown=False):
        if root == app_dir:
            continue
        # Check if directory is empty (only __pycache__ or nothing)
        real_files = [f for f in files if f != ".gitkeep"]
        real_dirs = [d for d in dirs if d != "__pycache__"]
        if not real_files and not real_dirs:
            # Remove __pycache__ if exists
            pycache = os.path.join(root, "__pycache__")
            if os.path.exists(pycache):
                shutil.rmtree(pycache)
            os.rmdir(root)
            removed += 1
    print(f"Removed {removed} empty directories")


def main():
    print("=" * 60)
    print("Backend Package Migration")
    print("=" * 60)

    print("\n1. Creating directory structure...")
    create_dirs()

    print("\n2. Moving files...")
    move_files()

    print("\n3. Updating imports...")
    update_imports()

    print("\n4. Cleaning up empty directories...")
    cleanup_empty_dirs()

    print("\n" + "=" * 60)
    print("Migration complete!")
    print("Next steps:")
    print("  1. Update app/main.py imports")
    print("  2. Update app/api/v1/router.py imports")
    print("  3. Update app/models/__init__.py re-exports")
    print("  4. Test: cd backend && uv run python app/main.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
