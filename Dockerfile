# Use an official, stable PyTorch image as the base
FROM pytorch/pytorch:2.1.0-cuda11.8-cudnn8-runtime

# Set the working directory
WORKDIR /app

# AGGRESSIVE CACHE BUST - FORCE REBUILD
ENV BUILD_ID="numpy-fix-2024-12-19-$(date +%s)"
ENV CACHE_BUST_NUMPY="FORCE_NUMPY_REBUILD_v4"
ENV CACHE_BUST_IMAGESTITCH="FORCE_IMAGESTITCH_REBUILD_v4"
RUN echo "CACHE BUST: $(date) - BUILD_ID: $BUILD_ID" > /app/force_rebuild.txt

# Install git and system dependencies
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Set environment variables for ComfyUI API authentication
# These will be provided by RunPod environment variables
ENV AUTH_TOKEN_COMFY_ORG=""
ENV API_KEY_COMFY_ORG=""

# CACHE BUST: ImageStitch fix deployment - VERSION 4
ENV IMAGESTITCH_FIX_VERSION="2024-12-19-v4-NUMPY-FIX"
RUN echo "DEPLOYING IMAGESTITCH + NUMPY FIX VERSION: $IMAGESTITCH_FIX_VERSION at $(date)" > /app/version.txt

# Clone the NEW FIXED repository for this endpoint
# Force fresh clone every time - no cache
ARG CACHE_BUST_CLONE=$(date +%s)
RUN echo "Clone cache bust: $CACHE_BUST_CLONE" && \
    git clone --depth 1 https://github.com/zeeshan8126/flux-kontext-pro-fixed.git . && \
    echo "Build timestamp: $(date)" > /app/build_info.txt && \
    echo "Cache bust timestamp: $CACHE_BUST_CLONE" >> /app/build_info.txt

# Verify we have the latest code with ImageStitch parameters
RUN grep -n "spacing_width\|direction\|match_image_size\|spacing_color" handler.py || (echo "ERROR: ImageStitch parameters not found!" && exit 1)

# CRITICAL: Install NumPy with proper error handling and verification
# CACHE BUST for pip installs
ARG PIP_CACHE_BUST=$(date +%s)
RUN echo "Pip cache bust: $PIP_CACHE_BUST" && \
    pip install --upgrade pip --no-cache-dir && \
    pip uninstall -y numpy || true && \
    pip install --no-cache-dir --force-reinstall "numpy>=1.25.0,<2.0" && \
    python -c "import numpy as np; print(f'✅ NumPy {np.__version__} installed successfully')" && \
    pip install --no-cache-dir opencv-python-headless && \
    pip install --no-cache-dir --force-reinstall -r requirements.txt

# TRIPLE CHECK: Verify numpy is available in the exact way ComfyUI uses it
RUN python -c "import sys; print('Python path:', sys.path)" && \
    python -c "import numpy as np; print(f'✅ NumPy version: {np.__version__}'); print(f'✅ NumPy location: {np.__file__}')" && \
    python -c "import torch, numpy as np; test_array = np.array([[1, 2, 3], [4, 5, 6]]); test_tensor = torch.from_numpy(test_array); print(f'✅ torch.from_numpy() test passed: {test_tensor.shape}'); print('✅ ALL NUMPY TESTS PASSED')"

# Final verification: Check that handler.py contains ImageStitch fix
RUN echo "VERIFICATION: Checking ImageStitch parameters in handler.py..." && \
    grep -c "spacing_width.*0" handler.py && \
    grep -c "direction.*right" handler.py && \
    grep -c "match_image_size.*True" handler.py && \
    grep -c "spacing_color.*white" handler.py && \
    echo "✅ All ImageStitch parameters verified!"

# Add runtime numpy verification to handler.py startup
RUN echo "# Verify NumPy at startup - $(date)" >> /app/startup_check.py && \
    echo "try:" >> /app/startup_check.py && \
    echo "    import numpy as np" >> /app/startup_check.py && \
    echo "    print(f'[STARTUP] NumPy {np.__version__} available')" >> /app/startup_check.py && \
    echo "except ImportError as e:" >> /app/startup_check.py && \
    echo "    print(f'[STARTUP] CRITICAL: NumPy not available: {e}')" >> /app/startup_check.py && \
    echo "    exit(1)" >> /app/startup_check.py

# FINAL CACHE BUST: Unique identifier for this build
RUN echo "FINAL_BUILD_VERIFICATION: $(date) - NUMPY+IMAGESTITCH FIX v4" > /app/build_complete.txt

# Set the entrypoint to run startup check then handler
CMD ["sh", "-c", "python /app/startup_check.py && python -u handler.py"]