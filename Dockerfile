FROM python:3.11-slim

WORKDIR /app

# mock 模式仅需 Web 依赖；Agent / 编排 / services 不依赖第三方库
RUN pip install --no-cache-dir fastapi uvicorn

COPY app ./app

ENV PYTHONUNBUFFERED=1 \
    MOCK_MODE=true

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
