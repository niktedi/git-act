FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# сначала только манифесты зависимостей — для кеширования слоёв
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# теперь сам код
COPY . .

CMD ["uv", "run", "main.py"]