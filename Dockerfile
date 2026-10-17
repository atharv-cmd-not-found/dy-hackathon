# =====================================================================
# Stage 1: Build React / Three.js Frontend Production Bundle
# =====================================================================
FROM node:22-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# =====================================================================
# Stage 2: Python / PyTorch / MONAI Backend Runtime
# =====================================================================
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    PORT=8000 \
    DATA_DIR=/app/data

WORKDIR /app

# Install system libraries for medical imaging, OpenGL, and git
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    libgl1 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (with CUDA 12.1 PyTorch wheels)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cu121 -r requirements.txt

# Copy backend application and models
COPY app/ ./app/
COPY ml/ ./ml/
COPY models/ ./models/
COPY eval/ ./eval/
COPY tests/ ./tests/

# Copy built frontend assets from Stage 1 into frontend/dist
# (FastAPI automatically mounts and serves frontend/dist at /)
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Create persistent storage directory for cases & SQLite DB
RUN mkdir -p /app/data

EXPOSE 8000

# Health check to ensure model and backend are operational
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
