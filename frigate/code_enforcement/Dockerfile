FROM python:3.11-slim
WORKDIR /app
# libgl1 + libglib2.0-0 required by OpenCV (pulled in by easyocr)
# libgomp1 required by PyTorch CPU ops
RUN apt-get update && apt-get install -y \
    libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY service.py .
CMD ["python", "service.py"]
