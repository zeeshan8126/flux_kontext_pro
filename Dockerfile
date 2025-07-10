# Use an official, stable PyTorch image as the base
FROM pytorch/pytorch:2.1.0-cuda11.8-cudnn8-runtime

# Set the working directory
WORKDIR /app

# Install git.
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Clone the correct repository for this endpoint
# Cache bust: 2024-12-29-fix-validation-error
RUN git clone https://github.com/zeeshan8126/flux_kontext_pro.git .

# Install Python dependencies.
# This now includes pinning NumPy to a version less than 2.0 to solve the conflict.
RUN pip install --upgrade pip && \
    pip install "numpy<2.0" && \
    pip install -r requirements.txt && \
    pip install opencv-python-headless

# Set the entrypoint to run the handler script.
CMD ["python", "-u", "handler.py"]