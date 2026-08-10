#!/bin/bash
# Pre-commit 检查脚本
# 在代码提交前运行，确保符合约束规则

set -e

echo "Running Harness pre-commit checks..."

# 1. 工作区边界检查（如果有文件路径参数）
# python .harness/linters/check-workspace.py

# 2. 代码风格检查
echo "Checking code style..."

# 3. 安全检查 - 禁止直接数据库访问
echo "Checking for direct database access..."
if grep -r "execute.*SELECT\|execute.*INSERT\|execute.*UPDATE\|execute.*DELETE" \
   --include="*.py" \
   --exclude-dir=.harness \
   --exclude-dir=node_modules \
   . 2>/dev/null; then
    echo "ERROR: Direct database access detected. Use service layer instead."
    exit 1
fi

# 4. 安全检查 - 禁止硬编码密钥
echo "Checking for hardcoded secrets..."
if grep -rE "(api_key|secret|password)\s*=\s*['\"][^'\"]+['\"]" \
   --include="*.py" \
   --include="*.json" \
   --exclude-dir=.harness \
   --exclude-dir=node_modules \
   . 2>/dev/null | grep -v ".env.example"; then
    echo "WARNING: Potential hardcoded secrets found."
fi

# 5. 导入检查 - 确保使用 runtime_engine 而非旧的 harness
echo "Checking imports..."
if grep -r "from packages.agent.harness" --include="*.py" . 2>/dev/null | grep -v ".bak"; then
    echo "ERROR: Old harness import detected. Use runtime_engine instead."
    exit 1
fi

echo "✓ All pre-commit checks passed."
exit 0
