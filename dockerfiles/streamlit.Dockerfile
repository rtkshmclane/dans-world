# Dockerfile template for Streamlit apps
# Copy this to your app's root directory as "Dockerfile"
# Adjust the port, base URL path, and app file name.

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

# Change --server.baseUrlPath to match your nginx location
# Change streamlit_app.py to your app's main file
CMD ["streamlit", "run", "streamlit_app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.baseUrlPath=/apps/your-app", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
