# Use an official, stable PyTorch image as the base
FROM pytorch/pytorch:2.1.0-cuda11.8-cudnn8-runtime

# Set the working directory
WORKDIR /app

# Install git and system dependencies
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Set environment variables for ComfyUI API authentication
# These will be provided by RunPod environment variables
ENV AUTH_TOKEN_COMFY_ORG=""
ENV API_KEY_COMFY_ORG=""

# Clone the correct repository for this endpoint
# Force fresh clone every time - no cache
RUN git clone --depth 1 https://github.com/zeeshan8126/flux_kontext_pro.git . && \
    echo "Build timestamp: $(date)" > /app/build_info.txt

# Install Python dependencies with proper numpy handling
# Install numpy first with compatible version, then other requirements
RUN pip install --upgrade pip && \
    pip install "numpy>=1.25.0,<2.0" && \
    pip install opencv-python-headless && \
    pip install -r requirements.txt

# Verify numpy installation
RUN python -c "import numpy; print(f'NumPy version: {numpy.__version__}')"

# Set the entrypoint to run the handler script.
CMD ["python", "-u", "handler.py"]