FROM python:3.13-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY tripletex/ tripletex/

EXPOSE 8080
CMD ["uv", "run", "uvicorn", "tripletex.solve:app", "--host", "0.0.0.0", "--port", "8080"]
