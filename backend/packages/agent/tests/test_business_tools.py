"""业务/沙箱工具核心单测"""
import pytest

from packages.agent.orchestrator.business_tools import _check_code_safety


class TestCodeSafety:
    def test_dangerous_calls_blocked(self):
        dangerous = [
            "import os; os.system('rm -rf /')",
            "import subprocess; subprocess.run(['ls'])",
            "eval('1+1')",
            "exec('x=1')",
            "__import__('os').system('x')",
            "shutil.rmtree('/tmp/x')",
            "open('/etc/passwd')",
        ]
        for code in dangerous:
            assert _check_code_safety(code) is not None, f"应拦截: {code}"

    def test_safe_code_allowed(self):
        safe = [
            "print('hello world')",
            "x = 1 + 2",
            "with open('hello.txt','w') as f: f.write('hi')",
            "for i in range(5): print(i)",
        ]
        for code in safe:
            assert _check_code_safety(code) is None, f"应放行: {code}"
