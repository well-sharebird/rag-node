# Rag-nsjail 一次性沙箱执行镜像（仅本地开发用）。
#
# macOS 无法原生运行 nsjail（依赖 Linux namespace/seccomp-bpf），故封装成
# python:3.10-slim 的镜像：Python 版本与后端宿主 venv（py3.10）对齐，使宿主装好的
# 依赖（venv site-packages）可在容器内复用。nsjail 从源码编译（各发行版 apt 无预编译包）。
#
# 用法：SandboxRuntime 探测到本机无 nsjail 且安装过本镜像时，用
#   docker run --rm -v <sandbox_root>:/sb -w /sb/work rag-nsjail:py310 <script> <sitepackages>
# 容器内 runner.sh 用 nsjail 包住 python 执行挂载进来的脚本。

FROM python:3.10-slim

# nsjail 源码编译所需构建依赖
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      git g++ make autoconf bison flex pkg-config protobuf-compiler \
      libprotobuf-dev libnl-route-3-dev libcap-dev \
 && git clone --depth 1 https://github.com/google/nsjail.git /tmp/nsjail \
 && make -C /tmp/nsjail -j"$(nproc)" \
 && cp /tmp/nsjail/nsjail /usr/local/bin/nsjail \
 && rm -rf /tmp/nsjail \
 && apt-get purge -y git g++ make autoconf bison flex protobuf-compiler \
 && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

COPY runner.sh /usr/local/bin/rag-runner
RUN chmod +x /usr/local/bin/rag-runner

ENTRYPOINT ["/usr/local/bin/rag-runner"]
