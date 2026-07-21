# 架构偏差修复方案

## 现状分析

| 组件 | 设计要求 | 实际实现 | 偏差等级 |
|------|----------|----------|----------|
| Elasticsearch | BM25 全文检索 | 未引入 | 🔴 严重 |
| Neo4j | 知识图谱 | 未引入 | 🔴 严重 |
| Kafka | 消息队列解耦 | arq 直连 | 🔴 严重 |
| Prometheus | 标准指标端点 | Redis 自研 | 🟡 部分 |

## 修复策略

### 方案 A：轻量级替代（推荐 - 快速落地）

考虑到系统复杂度和运维成本，采用以下替代方案：

| 原设计 | 替代方案 | 理由 |
|--------|----------|------|
| Elasticsearch | **Milvus 全文索引 + SQLite FTS** | Milvus 2.4+ 支持全文检索，避免引入新组件 |
| Neo4j | **Milvus 图索引 + 关系表** | 用关系表存储实体关系，Milvus 做向量关联 |
| Kafka | **Redis Streams + arq** | Redis Streams 提供队列功能，arq 处理消费 |
| Prometheus | **OpenTelemetry + /metrics** | 添加标准 Prometheus 端点，兼容现有 Redis 存储 |

### 方案 B：完整实现（生产级）

如需完整实现原设计，需要：
1. 添加 Elasticsearch 服务 - 用于 BM25 检索
2. 添加 Neo4j 服务 - 用于知识图谱
3. 添加 Kafka 服务 - 用于消息队列
4. 添加 Prometheus + Grafana - 用于监控

## 实施计划

### 阶段 1：Prometheus 指标端点（1 天）
- [ ] 添加 `/metrics` 端点（Prometheus 格式）
- [ ] 集成 OpenTelemetry
- [ ] 添加 docker-compose 配置

### 阶段 2：全文检索增强（2 天）
- [ ] 方案 A：实现 SQLite FTS 全文检索
- [ ] 方案 B：集成 Elasticsearch
- [ ] 混合检索（向量 + 全文）

### 阶段 3：知识图谱支持（3 天）
- [ ] 方案 A：实体关系表 + 图查询 API
- [ ] 方案 B：集成 Neo4j
- [ ] 实体链接和关系推理

### 阶段 4：消息队列解耦（2 天）
- [ ] Redis Streams 实现
- [ ] 文档处理流水线改造
- [ ] 重试机制和死信队列
