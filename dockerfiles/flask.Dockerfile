# Dockerfile template for Flask apps
# Copy this to your app's root directory as "Dockerfile"
# Adjust the port, entrypoint module, and any extra dependencies.

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Change 5000 to your app's port
EXPOSE 5000

# Change "app:app" to match your Flask entrypoint (e.g., "ticket_viewer_enhanced:app")
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "app:app"]
