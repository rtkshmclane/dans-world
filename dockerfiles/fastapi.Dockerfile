# Dockerfile template for FastAPI apps
# Copy this to your app's root directory as "Dockerfile"
# Adjust the port and module path.

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Change 8000 to your app's port
EXPOSE 8000

# Change "main:app" to match your FastAPI entrypoint
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
