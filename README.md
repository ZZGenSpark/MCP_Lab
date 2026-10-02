# MCP_Lab

Lightweight rebuild of the `fde-dev` toolchain on `python:3.12-slim-bookworm`. The image includes the same CLI tools and the Ollama models `llama3.2:3b` and `mistral`.

```bash
docker compose build
docker compose up -d
docker exec -it mcp-lab bash
```

Start Ollama inside the container when you need the models:

```bash
ollama serve
ollama list
```