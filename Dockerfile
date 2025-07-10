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

# CACHE BUST: ImageStitch fix deployment - VERSION 3
ENV IMAGESTITCH_FIX_VERSION="2024-12-19-v3"
RUN echo "DEPLOYING IMAGESTITCH FIX VERSION: $IMAGESTITCH_FIX_VERSION" > /app/version.txt

# Clone the NEW FIXED repository for this endpoint
# Force fresh clone every time - no cache
RUN git clone --depth 1 https://github.com/zeeshan8126/flux-kontext-pro-fixed.git . && \
    echo "Build timestamp: $(date)" > /app/build_info.txt

# Verify we have the latest code with ImageStitch parameters
RUN grep -n "spacing_width\|direction\|match_image_size\|spacing_color" handler.py || (echo "ERROR: ImageStitch parameters not found!" && exit 1)

# Install Python dependencies with proper numpy handling
# Install numpy first with compatible version, then other requirements
RUN pip install --upgrade pip && \
    pip install "numpy>=1.25.0,<2.0" && \
    pip install opencv-python-headless && \
    pip install -r requirements.txt

# Verify numpy installation
RUN python -c "import numpy; print(f'NumPy version: {numpy.__version__}')"

# Final verification: Check that handler.py contains ImageStitch fix
RUN echo "VERIFICATION: Checking ImageStitch parameters in handler.py..." && \
    grep -c "spacing_width.*0" handler.py && \
    grep -c "direction.*right" handler.py && \
    grep -c "match_image_size.*True" handler.py && \
    grep -c "spacing_color.*white" handler.py && \
    echo "✅ All ImageStitch parameters verified!"

# Set the entrypoint to run the handler script.
CMD ["python", "-u", "handler.py"]