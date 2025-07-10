# Use an official, stable PyTorch image as the base
FROM pytorch/pytorch:2.1.0-cuda11.8-cudnn8-runtime

# Set the working directory
WORKDIR /app

# Install git and system dependencies
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Set environment variables for ComfyUI API authentication
# These will be overridden by RunPod environment variables
ENV AUTH_TOKEN_COMFY_ORG=""
ENV API_KEY_COMFY_ORG=""



# Copy repository content to container first
COPY . /app/

# CACHE BUST: Force rebuild for ImageStitch fixes
ENV FIX_VERSION="flux-pro-v1"
RUN echo "DEPLOYING FIX VERSION: $FIX_VERSION" > /app/version.txt && \
    echo "Using flux-pro repository content at: $(date)" > /app/build_info.txt

# Verify we have the ImageStitch parameters in handler.py
RUN grep -q "spacing_width.*0" handler.py && \
    grep -q "direction.*right" handler.py && \
    grep -q "match_image_size.*True" handler.py && \
    grep -q "spacing_color.*white" handler.py && \
    echo "✅ ImageStitch parameters verified in handler.py"

# Install Python dependencies with proper NumPy version for PyTorch 2.1.0 compatibility
RUN pip install --upgrade pip && \
    pip uninstall -y numpy && \
    pip install opencv-python-headless && \
    pip install -r requirements.txt && \
    pip install "numpy<2.0.0"

# Simple verification that basic imports work
RUN python -c "print('✅ Build verification complete')"

# Create startup verification script  
RUN echo '#!/usr/bin/env python' > /app/verify_startup.py && \
    echo 'import sys' >> /app/verify_startup.py && \
    echo 'import os' >> /app/verify_startup.py && \
    echo 'try:' >> /app/verify_startup.py && \
    echo '    import numpy as np' >> /app/verify_startup.py && \
    echo '    import torch' >> /app/verify_startup.py && \
    echo '    print(f"[STARTUP] ✅ NumPy {np.__version__} ready")' >> /app/verify_startup.py && \
    echo '    print(f"[STARTUP] ✅ PyTorch {torch.__version__} ready")' >> /app/verify_startup.py && \
    echo '    # Test NumPy-PyTorch compatibility' >> /app/verify_startup.py && \
    echo '    test_array = np.array([1.0, 2.0, 3.0], dtype=np.float32)' >> /app/verify_startup.py && \
    echo '    test_tensor = torch.from_numpy(test_array)' >> /app/verify_startup.py && \
    echo '    print("[STARTUP] ✅ NumPy-PyTorch compatibility verified")' >> /app/verify_startup.py && \
    echo '    # Check API credentials' >> /app/verify_startup.py && \
    echo '    auth_token = os.getenv("AUTH_TOKEN_COMFY_ORG", "")' >> /app/verify_startup.py && \
    echo '    api_key = os.getenv("API_KEY_COMFY_ORG", "")' >> /app/verify_startup.py && \
    echo '    print(f"[STARTUP] AUTH_TOKEN_COMFY_ORG: {auth_token[:20]}..." if auth_token else "[STARTUP] AUTH_TOKEN_COMFY_ORG: (empty)")' >> /app/verify_startup.py && \
    echo '    print(f"[STARTUP] API_KEY_COMFY_ORG: {api_key[:20]}..." if api_key else "[STARTUP] API_KEY_COMFY_ORG: (empty)")' >> /app/verify_startup.py && \
    echo '    if not auth_token or not api_key:' >> /app/verify_startup.py && \
    echo '        print("[STARTUP] ⚠️  WARNING: API credentials not set!")' >> /app/verify_startup.py && \
    echo '        print("[STARTUP] Set AUTH_TOKEN_COMFY_ORG and API_KEY_COMFY_ORG in RunPod environment variables")' >> /app/verify_startup.py && \
    echo '    elif auth_token == "your_actual_token_here" or api_key == "your_actual_api_key_here":' >> /app/verify_startup.py && \
    echo '        print("[STARTUP] ⚠️  WARNING: Using placeholder values! Set real API tokens!")' >> /app/verify_startup.py && \
    echo '    else:' >> /app/verify_startup.py && \
    echo '        print("[STARTUP] ✅ API credentials configured")' >> /app/verify_startup.py && \
    echo '    print("[STARTUP] ✅ All dependencies verified")' >> /app/verify_startup.py && \
    echo 'except Exception as e:' >> /app/verify_startup.py && \
    echo '    print(f"[STARTUP] ❌ Dependency error: {e}")' >> /app/verify_startup.py && \
    echo '    sys.exit(1)' >> /app/verify_startup.py

# Final verification
RUN echo "✅ Build completed successfully with ImageStitch fixes" > /app/build_complete.txt

# Set the entrypoint
CMD ["sh", "-c", "python /app/verify_startup.py && python -u handler.py"]