FROM pytorch/pytorch:2.1.2-cuda11.8-cudnn8-runtime

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables for CUDA
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility
ENV CUDA_HOME=/usr/local/cuda
ENV PATH=${CUDA_HOME}/bin:${PATH}
ENV LD_LIBRARY_PATH=${CUDA_HOME}/lib64:${LD_LIBRARY_PATH}

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8002

# Note: Pass HF_TOKEN as environment variable at runtime for gated models.
# For Podman: docker run --device nvidia.com/gpu=all -p 8002:8002 --env-file .env ai4bharat-tts-server
# For Docker: docker run --gpus all -p 8002:8002 --env-file .env ai4bharat-tts-server

# Run the application
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8002"]
