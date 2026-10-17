FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir falkordb pyyaml fastapi "uvicorn[standard]" "mcp<2" httpx
COPY ownergraph ./ownergraph
COPY data/snapshot ./data/snapshot
ENV OWNERGRAPH_DATA=/app/data/snapshot OWNERGRAPH_HOST=0.0.0.0 FALKORDB_HOST=falkordb
EXPOSE 8000
CMD ["python", "-m", "ownergraph", "serve", "--load-if-empty", "--port", "8000"]
