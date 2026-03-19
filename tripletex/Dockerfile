FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen

COPY . .

EXPOSE 8080
CMD ["uv", "run", "uvicorn", "nmai.tasks.tripletex.solve:app", "--host", "0.0.0.0", "--port", "8080"]
