"""
提示词工程 CLI 工具

使用方法:
    uv run python -m app.cli.prompt commit <template_name> --file ./prompt.md --version 1.0.0
    uv run python -m app.cli.prompt eval <template_name> --candidate 1.0.0 --baseline stable
    uv run python -m app.cli.prompt tag <template_name> --version 1.0.0 --tag stable
    uv run python -m app.cli.prompt rollback <template_name> --to 1.0.0 --tag stable
"""
import asyncio
import sys
import json
import argparse
from pathlib import Path
from typing import Optional

# 添加父目录到路径以便导入
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import get_db_session
from app.models.prompt_template import PromptTemplate, PromptVersion, PromptTag
from app.schemas.prompt import (
    PromptTemplateCreate,
    PromptVersionCreate,
    TagCreate,
    RollbackRequest,
)
from app.services.prompt import (
    PromptRegistryService,
    PromptPublisher,
    PromptEvaluator,
    AuditService,
)


def get_db() -> AsyncSession:
    """获取数据库会话"""
    from app.config import settings

    engine = create_async_engine(
        settings.database_url,
        echo=False,
    )
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)()


# ==================== Commit Command ====================


async def cmd_commit(
    name: str,
    file_path: str,
    version: str,
    changelog: Optional[str] = None,
    category: str = "system",
    description: Optional[str] = None,
    owner: Optional[str] = None,
):
    """提交新版本（草稿）"""
    db = get_db()
    registry = PromptRegistryService(db)
    audit = AuditService(db)

    try:
        # 读取文件内容
        content = Path(file_path).read_text(encoding="utf-8")

        # 检查模板是否存在
        template = await registry.get_template(name)

        if not template:
            # 创建新模板
            template_data = PromptTemplateCreate(
                name=name,
                description=description or f"提示词模板：{name}",
                category=category,
                owner=owner,
            )
            template = await registry.create_template(template_data, actor="cli")
            print(f"✓ 创建新模板：{name}")
        else:
            print(f"✓ 使用现有模板：{name}")

        # 创建新版本
        version_data = PromptVersionCreate(
            version=version,
            content=content,
            changelog=changelog,
        )
        new_version = await registry.create_version(name, version_data, actor="cli")
        print(f"✓ 创建新版本：{version}")

        # 审计日志
        await audit.log(
            actor="cli",
            action=AuditService.ACTION_CREATE,
            resource_type=AuditService.RESOURCE_VERSION,
            resource_id=new_version.id,
            new_value={"version": version, "changelog": changelog},
        )

        print(f"\n版本已创建（状态：draft）")
        print(f"  运行评估：uv run python -m app.cli.prompt eval {name} --candidate {version}")
        print(f"  发布为 stable: uv run python -m app.cli.prompt tag {name} --version {version} --tag stable")

    finally:
        await db.close()


# ==================== Eval Command ====================


async def cmd_eval(
    name: str,
    candidate: str,
    baseline: Optional[str] = None,
    sample: Optional[int] = None,
    judge_model: str = "gpt-4o",
):
    """运行离线评估"""
    db = get_db()
    registry = PromptRegistryService(db)

    try:
        # 获取候选版本
        candidate_version = await registry.get_version(name, candidate)
        if not candidate_version:
            print(f"✗ 版本不存在：{candidate}")
            return

        # 获取基线版本
        baseline_version_id = None
        if baseline:
            baseline_version = await registry.get_version(name, baseline)
            if not baseline_version:
                print(f"✗ 基线版本不存在：{baseline}")
                return
            baseline_version_id = baseline_version.id

        # 获取测试用例
        test_cases = await registry.list_test_cases(name, is_active=True)
        if not test_cases:
            print(f"⚠ 模板 '{name}' 没有测试用例")
            print(f"  先创建测试用例再运行评估")
            return

        if sample:
            test_cases = test_cases[:sample]

        print(f"开始评估...")
        print(f"  候选版本：{candidate}")
        print(f"  基线版本：{baseline or 'stable'}")
        print(f"  测试用例：{len(test_cases)} 条")
        print(f"  裁判模型：{judge_model}")

        # 运行评估
        evaluator = PromptEvaluator(db)
        report = await evaluator.evaluate(
            candidate_version_id=candidate_version.id,
            baseline_version_id=baseline_version_id,
            test_case_ids=[c.id for c in test_cases],
            judge_model=judge_model,
            triggered_by="cli",
        )

        # 输出结果
        print(f"\n{'='*50}")
        print(f"评估结果")
        print(f"{'='*50}")
        print(f"  平均分数：{report.avg_score:.1f}")
        print(f"  相对提升：{report.delta:+.1f}")
        print(f"  是否通过：{'✓' if report.passed else '✗'}")
        print(f"  耗时：{report.run_duration_ms}ms")

        if not report.passed:
            print(f"\n⚠ 评估未通过（提升 < 3 分）")
            print(f"  建议：修改提示词后重新评估")

    finally:
        await db.close()


# ==================== Tag Command ====================


async def cmd_tag(
    name: str,
    version: str,
    tag: str,
    gray_percent: Optional[int] = None,
):
    """设置标签"""
    db = get_db()
    registry = PromptRegistryService(db)
    audit = AuditService(db)

    try:
        # 获取版本
        version_obj = await registry.get_version(name, version)
        if not version_obj:
            print(f"✗ 版本不存在：{version}")
            return

        # 构建元配置
        meta_config = {}
        if gray_percent:
            meta_config["gray_percent"] = gray_percent

        # 设置标签
        tag_data = TagCreate(
            tag_name=tag,
            version_id=version_obj.id,
            meta_config=meta_config,
        )
        result = await registry.set_tag(name, tag_data, actor="cli")

        if not result:
            print(f"✗ 设置标签失败")
            return

        print(f"✓ 标签已设置")
        print(f"  模板：{name}")
        print(f"  标签：{tag}")
        print(f"  版本：{version}")
        if gray_percent:
            print(f"  灰度：{gray_percent}%")

        # 审计日志
        await audit.log(
            actor="cli",
            action=AuditService.ACTION_TAG,
            resource_type=AuditService.RESOURCE_TAG,
            resource_id=result.id,
            new_value={"tag_name": tag, "version_id": version_obj.id},
        )

    finally:
        await db.close()


# ==================== Rollback Command ====================


async def cmd_rollback(
    name: str,
    to: str,
    tag: str = "stable",
    force: bool = False,
):
    """回滚"""
    db = get_db()
    publisher = PromptPublisher(db)
    registry = PromptRegistryService(db)
    audit = AuditService(db)

    try:
        # 获取目标版本
        version_obj = await registry.get_version(name, to)
        if not version_obj:
            print(f"✗ 版本不存在：{to}")
            return

        # 执行回滚
        success = await publisher.rollback(
            name,
            target_version_id=version_obj.id,
            tag_name=tag,
            actor="cli",
        )

        if not success:
            print(f"✗ 回滚失败")
            return

        print(f"✓ 回滚成功")
        print(f"  模板：{name}")
        print(f"  标签：{tag}")
        print(f"  回滚至：{to}")

        # 审计日志
        await audit.log(
            actor="cli",
            action=AuditService.ACTION_ROLLBACK,
            resource_type=AuditService.RESOURCE_TAG,
            resource_id=0,
            new_value={"tag_name": tag, "target_version": to},
        )

    finally:
        await db.close()


# ==================== List Command ====================


async def cmd_list(name: Optional[str] = None):
    """列出模板或版本"""
    db = get_db()
    registry = PromptRegistryService(db)

    try:
        if name:
            # 列出某模板的所有版本
            template = await registry.get_template(name)
            if not template:
                print(f"✗ 模板不存在：{name}")
                return

            versions, _ = await registry.list_versions(name, limit=50)
            tags = await registry.list_tags(name)
            tag_map = {t.tag_name: t.version.version for t in tags if t.version}

            print(f"模板：{name}")
            print(f"  描述：{template.description or '-'}")
            print(f"  分类：{template.category}")
            print(f"  标签:")
            for tag_name, version in tag_map.items():
                print(f"    {tag_name}: {version}")
            print(f"  版本列表:")
            for v in versions:
                status_icon = "✓" if v.status == "released" else "○" if v.status == "draft" else "✗"
                score = f" (score: {v.latest_eval_score:.1f})" if v.latest_eval_score else ""
                print(f"    {status_icon} {v.version} [{v.status}]{score}")
        else:
            # 列出所有模板
            templates, total = await registry.list_templates(limit=50)

            print(f"提示词模板列表 (共 {total} 个)")
            print("-" * 60)
            for t in templates:
                tags = await registry.list_tags(t.name)
                tag_str = ", ".join([f"{tag.tag_name}={tag.version.version}" for tag in tags if tag.version])
                print(f"  {t.name}")
                print(f"    分类：{t.category}, 状态：{t.status}")
                print(f"    标签：{tag_str or '-'}")

    finally:
        await db.close()


# ==================== Main ====================


def main():
    parser = argparse.ArgumentParser(
        description="提示词工程 CLI 工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="命令")

    # commit 命令
    commit_parser = subparsers.add_parser("commit", help="提交新版本")
    commit_parser.add_argument("name", help="模板名称")
    commit_parser.add_argument("--file", "-f", required=True, help="提示词文件路径")
    commit_parser.add_argument("--version", "-v", required=True, help="语义化版本号")
    commit_parser.add_argument("--changelog", "-c", help="变更说明")
    commit_parser.add_argument("--category", default="system", help="分类")
    commit_parser.add_argument("--description", "-d", help="描述")
    commit_parser.add_argument("--owner", "-o", help="负责人")

    # eval 命令
    eval_parser = subparsers.add_parser("eval", help="运行评估")
    eval_parser.add_argument("name", help="模板名称")
    eval_parser.add_argument("--candidate", required=True, help="候选版本")
    eval_parser.add_argument("--baseline", "-b", help="基线版本（默认 stable）")
    eval_parser.add_argument("--sample", "-n", type=int, help="抽样数量")
    eval_parser.add_argument("--judge-model", "-m", default="gpt-4o", help="裁判模型")

    # tag 命令
    tag_parser = subparsers.add_parser("tag", help="设置标签")
    tag_parser.add_argument("name", help="模板名称")
    tag_parser.add_argument("--version", "-v", required=True, help="版本号")
    tag_parser.add_argument("--tag", "-t", required=True, help="标签名")
    tag_parser.add_argument("--gray-percent", type=int, help="灰度百分比")

    # rollback 命令
    rollback_parser = subparsers.add_parser("rollback", help="回滚")
    rollback_parser.add_argument("name", help="模板名称")
    rollback_parser.add_argument("--to", required=True, help="回滚目标版本")
    rollback_parser.add_argument("--tag", "-t", default="stable", help="要回滚的标签")
    rollback_parser.add_argument("--force", "-f", action="store_true", help="强制回滚")

    # list 命令
    list_parser = subparsers.add_parser("list", help="列出模板或版本")
    list_parser.add_argument("name", nargs="?", help="模板名称（可选）")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # 执行命令
    if args.command == "commit":
        asyncio.run(cmd_commit(
            name=args.name,
            file_path=args.file,
            version=args.version,
            changelog=args.changelog,
            category=args.category,
            description=args.description,
            owner=args.owner,
        ))
    elif args.command == "eval":
        asyncio.run(cmd_eval(
            name=args.name,
            candidate=args.candidate,
            baseline=args.baseline,
            sample=args.sample,
            judge_model=args.judge_model,
        ))
    elif args.command == "tag":
        asyncio.run(cmd_tag(
            name=args.name,
            version=args.version,
            tag=args.tag,
            gray_percent=args.gray_percent,
        ))
    elif args.command == "rollback":
        asyncio.run(cmd_rollback(
            name=args.name,
            to=args.to,
            tag=args.tag,
            force=args.force,
        ))
    elif args.command == "list":
        asyncio.run(cmd_list(name=args.name))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
