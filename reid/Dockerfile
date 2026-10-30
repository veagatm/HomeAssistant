FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender-dev \
    ffmpeg \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .

# Install CPU-only torch first — prevents EasyOCR from pulling 2GB of CUDA libs
# (Colima/Apple Silicon has no NVIDIA GPU; CPU inference is all we use)
RUN pip install --no-cache-dir torch torchvision \
    --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir -r requirements.txt

# InsightFace model download (buffalo_l = ArcFace, cached in image layer)
RUN python3 -c "from insightface.app import FaceAnalysis; FaceAnalysis(name='buffalo_l').prepare(ctx_id=-1)"

COPY service.py ocr.py clusters.py ./

CMD ["python3", "-u", "service.py"]
