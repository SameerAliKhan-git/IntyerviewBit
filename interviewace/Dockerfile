FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire app
COPY . .

# Expose the port Cloud Run uses
ENV PORT=8080
ENV K_SERVICE=interviewace
EXPOSE 8080

# Run uvicorn directly — this ensures proper WebSocket support
# and avoids reload/watchfiles issues in containers
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8080", \
     "--log-level", "info", \
     "--ws-max-size", "16777216", \
     "--timeout-keep-alive", "300"]
