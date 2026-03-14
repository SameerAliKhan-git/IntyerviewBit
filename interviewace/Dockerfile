FROM python:3.11-slim

# Install system dependencies
WORKDIR /interviewace
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

# Set working directory to where main.py lives
# This ensures "from interview_coach_agent.agent import root_agent" works
WORKDIR /interviewace/app

# Expose the port Cloud Run uses
ENV PORT=8080
EXPOSE 8080

# Run uvicorn directly from the app/ directory
# "main:app" means main.py's FastAPI `app` object
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8080", \
     "--log-level", "info", \
     "--ws-max-size", "16777216", \
     "--timeout-keep-alive", "300"]
