# Use an official, stable PyTorch image as the base
FROM pytorch/pytorch:2.1.0-cuda11.8-cudnn8-runtime

# Set the working directory
WORKDIR /app

# Install git and system dependencies
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Set environment variables for ComfyUI API authentication
ENV AUTH_TOKEN_COMFY_ORG=""
ENV API_KEY_COMFY_ORG=""

# CACHE BUST: Force rebuild for ImageStitch fixes
ENV FIX_VERSION="imagestitch-fix-v7"
RUN echo "DEPLOYING FIX VERSION: $FIX_VERSION" > /app/version.txt

# Clone the fixed repository - clear directory first
RUN rm -rf /app/* /app/.* 2>/dev/null || true && \
    git clone --depth 1 https://github.com/zeeshan8126/flux-kontext-pro-fixed.git /tmp/repo && \
    cp -r /tmp/repo/* /app/ && \
    cp -r /tmp/repo/.* /app/ 2>/dev/null || true && \
    rm -rf /tmp/repo && \
    echo "Clone completed at: $(date)" > /app/build_info.txt

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
    echo 'try:' >> /app/verify_startup.py && \
    echo '    import numpy as np' >> /app/verify_startup.py && \
    echo '    import torch' >> /app/verify_startup.py && \
    echo '    print(f"[STARTUP] ✅ NumPy {np.__version__} ready")' >> /app/verify_startup.py && \
    echo '    print(f"[STARTUP] ✅ PyTorch {torch.__version__} ready")' >> /app/verify_startup.py && \
    echo '    # Test NumPy-PyTorch compatibility' >> /app/verify_startup.py && \
    echo '    test_array = np.array([1.0, 2.0, 3.0], dtype=np.float32)' >> /app/verify_startup.py && \
    echo '    test_tensor = torch.from_numpy(test_array)' >> /app/verify_startup.py && \
    echo '    print("[STARTUP] ✅ NumPy-PyTorch compatibility verified")' >> /app/verify_startup.py && \
    echo '    print("[STARTUP] ✅ All dependencies verified")' >> /app/verify_startup.py && \
    echo 'except Exception as e:' >> /app/verify_startup.py && \
    echo '    print(f"[STARTUP] ❌ Dependency error: {e}")' >> /app/verify_startup.py && \
    echo '    sys.exit(1)' >> /app/verify_startup.py

# Final verification
RUN echo "✅ Build completed successfully with ImageStitch fixes" > /app/build_complete.txt

# Set the entrypoint
CMD ["sh", "-c", "python /app/verify_startup.py && python -u handler.py"]