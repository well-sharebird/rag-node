#!/bin/bash
# Elasticsearch 一键部署 (清华镜像源)
# 使用路径: /opt/rag
set -e

echo "=== Elasticsearch 部署 (清华镜像源) ==="

# 1. 配置 Docker 使用清华镜像加速
echo "[1/5] 配置 Docker 镜像加速..."
sudo tee /etc/docker/daemon.json << 'EOF'
{
  "registry-mirrors": [
    "https://mirrors.tuna.tsinghua.edu.cn/docker-ce"
  ]
}
EOF
sudo systemctl daemon-reload
sudo systemctl restart docker
echo "Docker 镜像加速配置完成"

# 2. 设置内核参数 (ES 必须)
echo "[2/5] 设置内核参数..."
sudo sysctl -w vm.max_map_count=262144
echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf

# 3. 创建数据目录
echo "[3/5] 创建数据目录..."
sudo mkdir -p /opt/rag/volumes/elasticsearch
sudo chmod -R 777 /opt/rag/volumes/elasticsearch

# 4. 拉取镜像并启动
echo "[4/5] 拉取镜像并启动..."
cd /opt/rag
sudo docker compose -f docker-compose.es.yml up -d

# 5. 验证
echo "[5/5] 等待启动并验证..."
sleep 20
curl -s http://localhost:9200 | python3 -m json.tool 2>/dev/null || echo "服务启动中，请稍后访问 http://localhost:9200"

echo ""
echo "=== 部署完成 ==="
echo "地址: http://localhost:9200"
echo "日志: sudo docker logs -f rag-elasticsearch"
