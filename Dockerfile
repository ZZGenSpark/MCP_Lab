FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:/root/.local/bin:/usr/local/bin:${PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        gnupg \
        xz-utils \
        zstd \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/0.12.5/install.sh | sh \
    && uv --version

RUN set -eux; \
    NODE_VERSION=v24.19.0; \
    case "$(uname -m)" in \
      aarch64|arm64) NODE_ARCH=arm64 ;; \
      x86_64|amd64) NODE_ARCH=x64 ;; \
      *) echo "Unsupported architecture"; exit 1 ;; \
    esac; \
    curl -fsSLO "https://nodejs.org/dist/${NODE_VERSION}/node-${NODE_VERSION}-linux-${NODE_ARCH}.tar.xz"; \
    tar -xJf "node-${NODE_VERSION}-linux-${NODE_ARCH}.tar.xz" -C /usr/local --strip-components=1; \
    rm "node-${NODE_VERSION}-linux-${NODE_ARCH}.tar.xz"; \
    node --version; \
    npm --version

RUN set -eux; \
    install -d -m 0755 /etc/apt/keyrings; \
    curl -fsSL https://downloads.claude.ai/keys/claude-code.asc -o /etc/apt/keyrings/claude-code.asc; \
    echo "deb [signed-by=/etc/apt/keyrings/claude-code.asc] https://downloads.claude.ai/claude-code/apt/stable stable main" \
      > /etc/apt/sources.list.d/claude-code.list; \
    apt-get update; \
    apt-get install -y claude-code; \
    rm -rf /var/lib/apt/lists/*; \
    claude --version

RUN npm install -g promptfoo@0.122.0 \
    && promptfoo --version \
    && npm cache clean --force \
    && rm -rf /root/.npm

RUN curl -sL https://aka.ms/InstallAzureCLIDeb | bash \
    && az version

RUN set -eux; \
    case "$(uname -m)" in \
      aarch64|arm64) KUBE_ARCH=arm64 ;; \
      x86_64|amd64) KUBE_ARCH=amd64 ;; \
      *) echo "Unsupported architecture"; exit 1 ;; \
    esac; \
    KUBE_VERSION=v1.36.3; \
    curl -fsSLO "https://dl.k8s.io/release/${KUBE_VERSION}/bin/linux/${KUBE_ARCH}/kubectl"; \
    install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl; \
    rm kubectl; \
    kubectl version --client

RUN set -eux; \
    case "$(uname -m)" in \
      aarch64|arm64) OLLAMA_ARCH=arm64 ;; \
      x86_64|amd64) OLLAMA_ARCH=amd64 ;; \
      *) echo "Unsupported architecture"; exit 1 ;; \
    esac; \
    curl -fsSL "https://ollama.com/download/ollama-linux-${OLLAMA_ARCH}.tar.zst" -o /tmp/ollama.tar.zst; \
    tar --zstd -xf /tmp/ollama.tar.zst -C /usr; \
    rm /tmp/ollama.tar.zst; \
    ollama -v

RUN uv venv /opt/venv \
    && uv pip install --python /opt/venv/bin/python \
        "pydantic>=2" \
        fastapi \
        langchain \
        langgraph \
        "mcp[cli]" \
        opentelemetry-api \
        opentelemetry-sdk \
        tenacity \
        pybreaker \
        pytest \
        ruff \
        mypy \
        pip-audit \
        deepeval \
        inspect-ai \
    && python -c "import pydantic, fastapi, langchain, langgraph, mcp; print('Python stack OK')" \
    && rm -rf /root/.cache

RUN set -eux; \
    ollama serve > /tmp/ollama-build.log 2>&1 & \
    pid=$!; \
    ready=0; \
    for _ in $(seq 1 60); do \
      if curl -sf http://127.0.0.1:11434/api/version; then \
        ready=1; \
        break; \
      fi; \
      sleep 1; \
    done; \
    if [ "$ready" -ne 1 ]; then \
      cat /tmp/ollama-build.log; \
      exit 1; \
    fi; \
    ollama pull llama3.2:3b; \
    ollama pull mistral; \
    kill "$pid"; \
    wait "$pid" || true; \
    rm -f /tmp/ollama-build.log

WORKDIR /workspace

CMD ["sleep", "infinity"]
