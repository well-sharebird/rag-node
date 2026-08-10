# Runtime 实现方案详解

> 文档版本：1.0  
> 创建日期：2026-08-05

---

## 1. 概述

### 两种实现模式对比

| 维度 | 独立 Runtime | 共享 Runtime |
|------|-------------|-------------|
| **隔离级别** | 进程/容器级隔离 | 逻辑隔离 |
| **资源开销** | 高 | 低 |
| **启动时间** | 秒级 (5-30s) | 毫秒级 (<1s) |
| **适用场景** | VIP/企业/高安全 | 普通用户/大规模 |
| **成本** | $2-5/用户/天 | $0.5-1/用户/天 |

---

## 2. 独立 Runtime 实现方案

### 2.1 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Runtime Pod (用户 A 专属)                  │   │
│  │  ┌────────────────────────────────────────────────┐  │   │
│  │  │  Container: Agent Runtime                       │  │   │
│  │  │  ┌─────────────┐  ┌─────────────┐              │  │   │
│  │  │  │ Session α   │  │ Session β   │              │  │   │
│  │  │  │ (用户 A)    │  │ (用户 A)    │              │  │   │
│  │  │  └─────────────┘  └─────────────┘              │  │   │
│  │  │                                                 │  │   │
│  │  │  +───────────────────────────────────+          │  │   │
│  │  │  │ 文件系统：/workspace/user_a/       │          │  │   │
│  │  │  │ 网络命名空间：ns_user_a            │          │  │   │
│  │  │  │ 资源配额：CPU=2, Mem=2GB           │          │  │   │
│  │  │  +───────────────────────────────────+          │  │   │
│  │  └────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Runtime Pod (用户 B 专属)                  │   │
│  │  (结构同上，完全隔离)                                  │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 技术栈

```yaml
容器编排：Kubernetes
运行时：containerd / Docker
网络：CNI (Calico/Flannel)
存储：CSI (云厂商块存储/NFS)
服务网格：Istio (可选，用于流量管理)
```

### 2.3 实现细节

#### A. Pod 定义示例

```yaml
# runtime-pod.yaml
apiVersion: v1
kind: Pod
metadata:
  name: runtime-user-a-abc123
  labels:
    user-id: "user_a"
    runtime-type: dedicated
    agent-id: "agent_xyz"
spec:
  # 资源配额
  containers:
  - name: agent-runtime
    image: agent-runtime:latest
    resources:
      requests:
        cpu: "500m"
        memory: "512Mi"
      limits:
        cpu: "2000m"
        memory: "2Gi"
    
    # 环境变量
    env:
    - name: USER_ID
      value: "user_a"
    - name: RUNTIME_ID
      value: "runtime-abc123"
    - name: AGENT_MANIFEST
      valueFrom:
        configMapKeyRef:
          name: agent-manifest-xyz
          key: manifest.json
    
    # 持久化存储
    volumeMounts:
    - name: workspace
      mountPath: /workspace
    - name: cache
      mountPath: /cache
  
  # 存储卷
  volumes:
  - name: workspace
    persistentVolumeClaim:
      claimName: pvc-user-a-workspace
  - name: cache
    emptyDir: {}
  
  # 网络策略 (可选)
  networkPolicy:
    ingress:
    - from:
      - podSelector:
          matchLabels:
            role: api-gateway
```

#### B. 生命周期管理

```python
# runtime_lifecycle.py
class RuntimeLifecycleManager:
    """独立 Runtime 生命周期管理器"""
    
    async def create_runtime(
        self,
        user_id: str,
        agent_id: str,
        resources: ResourceQuota,
    ) -> Runtime:
        """创建 Runtime"""
        # 1. 创建 PVC (持久化存储)
        pvc = await self.k8s.create_pvc(
            name=f"pvc-{user_id}-workspace",
            size="10Gi",
            storage_class="fast-ssd",
        )
        
        # 2. 创建 ConfigMap (Agent Manifest)
        manifest = await self.agent_service.get_manifest(agent_id)
        await self.k8s.create_configmap(
            name=f"agent-manifest-{agent_id}",
            data={"manifest.json": manifest.json()},
        )
        
        # 3. 创建 Pod
        pod = await self.k8s.create_pod(
            name=f"runtime-{user_id}-{uuid4()[:8]}",
            template=self._build_pod_template(
                user_id=user_id,
                agent_id=agent_id,
                pvc=pvc,
                resources=resources,
            ),
        )
        
        # 4. 等待 Pod 就绪
        await self.k8s.wait_pod_ready(pod.name, timeout=60)
        
        # 5. 创建 Runtime 记录
        runtime = Runtime(
            id=pod.name,
            user_id=user_id,
            agent_id=agent_id,
            pod_name=pod.name,
            status=RuntimeStatus.RUNNING,
        )
        await self.db.add(runtime)
        
        return runtime
    
    async def hibernate_runtime(self, runtime_id: str):
        """休眠 Runtime (缩容到 0)"""
        runtime = await self.db.get(runtime_id)
        
        # 1. Checkpoint 保存状态
        await self.checkpoint_service.save(runtime)
        
        # 2. 缩容 Deployment 到 0
        await self.k8s.scale_deployment(runtime.pod_name, replicas=0)
        
        # 3. 更新状态
        runtime.status = RuntimeStatus.SLEEPING
        await self.db.update(runtime)
    
    async def wake_runtime(self, runtime_id: str):
        """唤醒 Runtime"""
        runtime = await self.db.get(runtime_id)
        
        # 1. 扩容 Deployment 到 1
        await self.k8s.scale_deployment(runtime.pod_name, replicas=1)
        
        # 2. 等待 Pod 就绪
        await self.k8s.wait_pod_ready(runtime.pod_name, timeout=30)
        
        # 3. 恢复状态
        await self.checkpoint_service.restore(runtime)
        
        # 4. 更新状态
        runtime.status = RuntimeStatus.RUNNING
        await self.db.update(runtime)
    
    async def delete_runtime(self, runtime_id: str):
        """删除 Runtime"""
        runtime = await self.db.get(runtime_id)
        
        # 1. 删除 Pod
        await self.k8s.delete_pod(runtime.pod_name)
        
        # 2. 删除 PVC (可选保留)
        await self.k8s.delete_pvc(f"pvc-{runtime.user_id}-workspace")
        
        # 3. 删除 ConfigMap
        await self.k8s.delete_configmap(f"agent-manifest-{runtime.agent_id}")
        
        # 4. 删除数据库记录
        await self.db.delete(runtime)
```

#### C. 网络隔离

```python
# network_policy.py
class RuntimeNetworkPolicy:
    """Runtime 网络策略"""
    
    async def create_isolated_network(
        self,
        runtime_id: str,
        user_id: str,
    ):
        """创建隔离网络"""
        # 1. 创建 NetworkPolicy
        policy = {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "NetworkPolicy",
            "metadata": {"name": f"netpol-{runtime_id}"},
            "spec": {
                "podSelector": {
                    "matchLabels": {"runtime-id": runtime_id}
                },
                "policyTypes": ["Ingress", "Egress"],
                "ingress": [
                    # 只允许 API Gateway 访问
                    {
                        "from": [{
                            "podSelector": {
                                "matchLabels": {"role": "api-gateway"}
                            }
                        }],
                        "ports": [{"port": 8080, "protocol": "TCP"}]
                    }
                ],
                "egress": [
                    # 只允许访问白名单外部服务
                    {
                        "to": [{
                            "ipBlock": {
                                "cidr": "0.0.0.0/0",
                                "except": ["10.0.0.0/8"]  # 禁止访问内网
                            }
                        }],
                        "ports": [
                            {"port": 443, "protocol": "TCP"},  # HTTPS
                            {"port": 53, "protocol": "UDP"},   # DNS
                        ]
                    }
                ]
            }
        }
        await self.k8s.create_network_policy(policy)
```

### 2.4 优缺点

| 优点 | 缺点 |
|------|------|
| ✅ 完全隔离，安全性最高 | ❌ 资源开销大 |
| ✅ 可定制专属环境 | ❌ 启动时间长 (5-30 秒) |
| ✅ 易于合规审计 | ❌ 运维复杂度高 |
| ✅ 性能可预测 | ❌ 成本高 ($2-5/用户/天) |

---

## 3. 共享 Runtime 实现方案

### 3.1 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│              Kubernetes Cluster                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │           Runtime Pool (共享资源池)                    │   │
│  │  ┌────────────────────────────────────────────────┐  │   │
│  │  │  Deployment: agent-runtime-pool (replicas=10)  │  │   │
│  │  │                                                 │  │   │
│  │  │  Pod 1: ┌─────────────────────────────────┐    │  │   │
│  │  │         │ Session Manager                  │    │  │   │
│  │  │         │ ├─ Session α (用户 A) [隔离]      │    │  │   │
│  │  │         │ ├─ Session δ (用户 B) [隔离]      │    │  │   │
│  │  │         │ ├─ Session ε (用户 C) [隔离]      │    │  │   │
│  │  │         │                                  │    │  │   │
│  │  │         │ 共享：LLM 连接池、向量索引缓存       │    │  │   │
│  │  │         └─────────────────────────────────┘    │  │   │
│  │  │                                                 │  │   │
│  │  │  Pod 2: ┌─────────────────────────────────┐    │  │   │
│  │  │         │ (同上结构)                       │    │  │   │
│  │  │         └─────────────────────────────────┘    │  │   │
│  │  │                                                 │  │   │
│  │  │  ... (共 10 个 Pod)                             │  │   │
│  │  └────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 技术栈

```yaml
容器编排：Kubernetes
运行时：containerd / Docker
会话管理：自定义 Session Manager
隔离机制：命名空间 + 逻辑隔离
缓存：Redis (共享)
存储：多租户数据库 (Row-Level Security)
```

### 3.3 实现细节

#### A. Session 隔离管理器

```python
# session_isolation_manager.py
class SessionIsolationManager:
    """Session 隔离管理器 - 共享 Runtime 的核心"""
    
    def __init__(self, redis: Redis, db: AsyncSession):
        self.redis = redis
        self.db = db
    
    def create_session_context(
        self,
        user_id: str,
        session_id: str,
        runtime_id: str,
    ) -> SessionContext:
        """创建隔离的会话上下文"""
        return SessionContext(
            user_id=user_id,
            session_id=session_id,
            runtime_id=runtime_id,
            # 隔离键 (用于所有存储操作)
            isolation_key=f"user:{user_id}:session:{session_id}",
            # 命名空间 (用于 Redis/缓存)
            namespace=f"ns_{user_id}_{session_id}",
            # 权限边界
            permissions=self._build_permissions(user_id),
        )
    
    async def get_isolated_data(
        self,
        context: SessionContext,
        key: str,
    ) -> Any:
        """获取隔离数据 - 自动附加隔离键"""
        full_key = f"{context.isolation_key}:{key}"
        
        # 验证访问权限
        await self._verify_access(context, full_key)
        
        # 从 Redis 获取
        data = await self.redis.get(full_key)
        return json.loads(data) if data else None
    
    async def set_isolated_data(
        self,
        context: SessionContext,
        key: str,
        value: Any,
        ttl: int = 3600,
    ):
        """设置隔离数据 - 自动附加隔离键"""
        full_key = f"{context.isolation_key}:{key}"
        await self.redis.setex(full_key, ttl, json.dumps(value))
    
    async def _verify_access(
        self,
        context: SessionContext,
        key: str,
    ):
        """验证数据访问权限"""
        # 提取键中的用户 ID
        parts = key.split(":")
        if len(parts) >= 2:
            key_user_id = parts[1]  # user:{user_id}:...
            if key_user_id != context.user_id:
                raise PermissionDeniedError(
                    f"User {context.user_id} cannot access {key}"
                )
    
    def _build_permissions(self, user_id: str) -> dict:
        """构建用户权限"""
        return {
            "user_id": user_id,
            "allowed_prefixes": [
                f"user:{user_id}:",
            ],
            "denied_prefixes": [
                "admin:",
                "system:",
            ],
        }
```

#### B. 多租户数据库隔离

```python
# multi_tenant_db.py
class MultiTenantDatabase:
    """多租户数据库 - Row-Level Security"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def query_sessions(
        self,
        user_id: str,
        runtime_id: str,
    ) -> List[Session]:
        """查询会话 - 自动附加用户过滤"""
        # 使用 RLS (Row-Level Security) 策略
        stmt = (
            select(Session)
            .where(Session.user_id == user_id)
            .where(Session.runtime_id == runtime_id)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
    
    async def store_message(
        self,
        user_id: str,
        session_id: str,
        message: Message,
    ):
        """存储消息 - 自动附加用户 ID"""
        db_message = Message(
            id=uuid4(),
            user_id=user_id,  # 强制设置
            session_id=session_id,
            content=message.content,
            role=message.role,
            created_at=datetime.utcnow(),
        )
        self.db.add(db_message)
        await self.db.commit()
    
    async def get_vector_index(
        self,
        user_id: str,
        session_id: str,
    ) -> VectorIndex:
        """获取向量索引 - 严格隔离"""
        stmt = (
            select(VectorIndex)
            .where(VectorIndex.user_id == user_id)
            .where(VectorIndex.session_id == session_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
```

#### C. 共享资源管理

```python
# shared_resource_pool.py
class SharedResourcePool:
    """共享资源池管理"""
    
    def __init__(self, redis: Redis):
        self.redis = redis
        self.llm_pool = LLMConnectionPool()
        self.vector_cache = VectorCache(redis)
    
    async def get_llm_connection(
        self,
        context: SessionContext,
    ) -> LLMClient:
        """获取 LLM 连接 - 共享但隔离上下文"""
        client = await self.llm_pool.borrow()
        
        # 包装客户端，确保上下文隔离
        return IsolatedLLMClient(
            client=client,
            isolation_key=context.isolation_key,
        )
    
    async def get_vector_index(
        self,
        context: SessionContext,
    ) -> VectorIndex:
        """获取向量索引 - 缓存共享，数据隔离"""
        cache_key = f"vector:{context.isolation_key}"
        
        # 尝试从缓存获取
        cached = await self.redis.get(cache_key)
        if cached:
            return VectorIndex.from_cache(cached)
        
        # 从数据库加载
        index = await self.db.get_vector_index(
            user_id=context.user_id,
            session_id=context.session_id,
        )
        
        # 缓存 (带 TTL)
        await self.redis.setex(
            cache_key,
            3600,
            index.to_cache(),
        )
        
        return index
    
    async def release_resources(
        self,
        context: SessionContext,
    ):
        """释放资源"""
        # 清理临时缓存
        await self.redis.delete(f"temp:{context.isolation_key}:*")
        
        # 归还 LLM 连接
        await self.llm_pool.return_client(context.isolation_key)
```

#### D. 会话路由

```python
# session_router.py
class SessionRouter:
    """Session 路由器 - 将请求路由到正确的 Pod"""
    
    def __init__(self, k8s_client, redis: Redis):
        self.k8s = k8s_client
        self.redis = redis
    
    async def get_target_pod(
        self,
        user_id: str,
        session_id: str,
    ) -> str:
        """获取目标 Pod"""
        # 1. 检查是否有现有会话
        existing = await self.redis.get(
            f"session_location:{user_id}:{session_id}"
        )
        if existing:
            return existing
        
        # 2. 选择负载最低的 Pod
        pods = await self._get_available_pods()
        target = min(pods, key=lambda p: p.load)
        
        # 3. 记录位置
        await self.redis.set(
            f"session_location:{user_id}:{session_id}",
            target.name,
            ex=3600,  # 1 小时过期
        )
        
        return target.name
    
    async def _get_available_pods(self) -> List[Pod]:
        """获取可用 Pod 列表"""
        # 从 Kubernetes 获取
        pod_list = await self.k8s.list_pods(
            label_selector="app=agent-runtime-pool"
        )
        
        # 过滤就绪的 Pod
        ready_pods = [
            p for p in pod_list
            if self._is_pod_ready(p)
        ]
        
        # 获取负载信息
        pods_with_load = []
        for pod in ready_pods:
            load = await self._get_pod_load(pod)
            pods_with_load.append(PodWithLoad(pod=pod, load=load))
        
        return pods_with_load
```

### 3.4 隔离保证

| 隔离层 | 实现方式 | 安全性 |
|-------|---------|--------|
| **用户 ID 验证** | 每个请求强制验证 | 🔴 高 |
| **Session 上下文** | 独立内存对象 | 🟡 中 |
| **数据库查询** | Row-Level Security | 🔴 高 |
| **Redis 键命名** | 前缀隔离 | 🟡 中 |
| **向量索引** | 用户 ID + Session ID 复合键 | 🔴 高 |
| **文件系统** | 命名空间隔离 | 🟡 中 |

### 3.5 优缺点

| 优点 | 缺点 |
|------|------|
| ✅ 资源利用率高 | ❌ 隔离依赖代码正确性 |
| ✅ 启动快 (<1 秒) | ❌ 存在隔离失效风险 |
| ✅ 成本低 ($0.5-1/用户/天) | ❌ 调试复杂 |
| ✅ 易于水平扩展 | ❌ 多租户数据泄露风险 |

---

## 4. 混合模式实现方案

### 4.1 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────────┐  ┌─────────────────────────────┐   │
│  │  Dedicated Pool     │  │     Shared Pool             │   │
│  │  (VIP/企业用户)     │  │   (普通用户)                │   │
│  │                     │  │                             │   │
│  │  ┌───────┐ ┌───────┐│  │  ┌───────────────────────┐ │   │
│  │  │User A │ │User B ││  │  │  Runtime Pool (10x)   │ │   │
│  │  │ Pod   │ │ Pod   ││  │  │  ├─ Session A (用户 C) │ │   │
│  │  └───────┘ └───────┘│  │  │  ├─ Session B (用户 D) │ │   │
│  │                     │  │  │  ├─ Session C (用户 E) │ │   │
│  │  (独立资源)          │  │  │  └─────────────────────┘ │   │
│  └─────────────────────┘  │  └─────────────────────────────┘   │
│                           │                                     │
│  ┌────────────────────────┴─────────────────────────────┐     │
│  │              Unified API Gateway                      │     │
│  │  (自动路由：VIP → Dedicated, 普通 → Shared)            │     │
│  └──────────────────────────────────────────────────────┘     │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 路由逻辑

```python
# runtime_router.py
class RuntimeRouter:
    """Runtime 路由器 - 根据用户类型选择池"""
    
    def __init__(
        self,
        dedicated_pool: DedicatedPool,
        shared_pool: SharedPool,
        user_service: UserService,
    ):
        self.dedicated = dedicated_pool
        self.shared = shared_pool
        self.user_service = user_service
    
    async def get_or_create_runtime(
        self,
        user_id: str,
        agent_id: str,
    ) -> Runtime:
        """获取或创建 Runtime"""
        # 1. 获取用户类型
        user = await self.user_service.get_user(user_id)
        
        # 2. 根据用户类型选择池
        if user.tier in ["vip", "enterprise"]:
            # VIP/企业用户 → 独立 Runtime
            return await self._get_dedicated_runtime(user, agent_id)
        else:
            # 普通用户 → 共享 Runtime
            return await self._get_shared_runtime(user, agent_id)
    
    async def _get_dedicated_runtime(
        self,
        user: User,
        agent_id: str,
    ) -> Runtime:
        """获取独立 Runtime"""
        # 检查是否已存在
        existing = await self.dedicated.find_by_user(user.id)
        if existing:
            return existing
        
        # 创建新的独立 Runtime
        return await self.dedicated.create(
            user_id=user.id,
            agent_id=agent_id,
            resources=ResourceQuota(
                cpu="2000m",
                memory="2Gi",
                disk="10Gi",
            ),
        )
    
    async def _get_shared_runtime(
        self,
        user: User,
        agent_id: str,
    ) -> Runtime:
        """获取共享 Runtime"""
        # 从共享池分配
        return await self.shared.allocate(
            user_id=user.id,
            agent_id=agent_id,
        )
```

### 4.3 成本对比

| 模式 | 100 用户 | 1000 用户 | 10000 用户 |
|------|---------|----------|-----------|
| **全独立** | $15,000/月 | $150,000/月 | $1,500,000/月 |
| **全共享** | $1,500/月 | $15,000/月 | $150,000/月 |
| **混合 (20% VIP)** | $4,500/月 | $45,000/月 | $450,000/月 |

---

## 5. 方案选择建议

### 5.1 决策矩阵

```
                        安全性要求
                           │
              高 ─────────┼────────── 低
                │         │
                │  独立    │  混合
          成    │  Runtime │  Mode
          本    │         │
          高    ├─────────┼──────────
                │  独立    │  共享
                │  Mode    │  Pool
                │         │
              多 ─────────┼────────── 少
                        用户规模
```

### 5.2 推荐配置

| 场景 | 推荐方案 | 配置 |
|------|---------|------|
| **企业内网部署** | 独立 Runtime | 每用户/每部门独立 Pod |
| **SaaS 服务 (高端)** | 混合模式 | 20% Dedicated + 80% Shared |
| **SaaS 服务 (大众)** | 共享 Runtime | 严格 Session 隔离 |
| **POC/测试环境** | 共享 Runtime | 最小化配置 |

---

## 6. 总结

### 关键技术点

| 方案 | 核心技术 | 关键挑战 |
|------|---------|---------|
| **独立** | K8s Pod 隔离、PVC、NetworkPolicy | 启动时间、资源利用率 |
| **共享** | Session 隔离管理器、RLS、命名空间 | 隔离正确性、代码复杂度 |
| **混合** | 智能路由、双池管理 | 运维复杂性 |

### 实施建议

1. **从共享开始**：初期用户少，共享模式成本低、开发快
2. **逐步演进**：用户增长后，为 VIP 添加独立池
3. **隔离优先**：无论哪种方案，用户间数据隔离是底线
