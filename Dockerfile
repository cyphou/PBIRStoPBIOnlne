FROM python:3.12-slim

WORKDIR /app

COPY pbirs_export/ pbirs_export/
COPY pbi_import/ pbi_import/
COPY migrate.py .
COPY pyproject.toml .

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt 2>/dev/null || true

EXPOSE 8000

CMD ["python", "migrate.py", "--help"]
