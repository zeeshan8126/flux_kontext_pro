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

# CACHE BUST: Force rebuild for ImageStitch + NumPy fixes
ENV FIX_VERSION="imagestitch-numpy-fix-v6"
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

# Install Python dependencies with NumPy fix
RUN pip install --upgrade pip && \
    pip uninstall -y numpy || true && \
    pip install --no-cache-dir "numpy>=1.25.0,<2.0" && \
    pip install opencv-python-headless && \
    pip install -r requirements.txt

# Verify NumPy installation works correctly
RUN python -c "import numpy as np; print(f'✅ NumPy {np.__version__} installed')" && \
    python -c "import torch, numpy as np; test = torch.from_numpy(np.array([1,2,3])); print('✅ torch.from_numpy() works')"

# Create startup verification script
RUN echo '#!/usr/bin/env python' > /app/verify_startup.py && \
    echo 'import sys' >> /app/verify_startup.py && \
    echo 'try:' >> /app/verify_startup.py && \
    echo '    import numpy as np' >> /app/verify_startup.py && \
    echo '    import torch' >> /app/verify_startup.py && \
    echo '    print(f"[STARTUP] ✅ NumPy {np.__version__} ready")' >> /app/verify_startup.py && \
    echo '    print("[STARTUP] ✅ All dependencies verified")' >> /app/verify_startup.py && \
    echo 'except Exception as e:' >> /app/verify_startup.py && \
    echo '    print(f"[STARTUP] ❌ Dependency error: {e}")' >> /app/verify_startup.py && \
    echo '    sys.exit(1)' >> /app/verify_startup.py

# Final verification
RUN echo "✅ Build completed successfully with ImageStitch + NumPy fixes" > /app/build_complete.txt

# Set the entrypoint
CMD ["sh", "-c", "python /app/verify_startup.py && python -u handler.py"]