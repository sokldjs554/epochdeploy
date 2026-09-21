FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml /app/pyproject.toml
COPY orchestrator /app/orchestrator
RUN pip install --no-cache-dir .[postgres]
ENV PYTHONPATH=/app/orchestrator
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
