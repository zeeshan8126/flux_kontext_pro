# Use an official, stable PyTorch image as the base
FROM pytorch/pytorch:2.1.0-cuda11.8-cudnn8-runtime

# Set the working directory
WORKDIR /app

# The official PyTorch image may not have git, so we install it.
# We also need to set an environment variable to allow apt to work without asking questions.
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Clone the correct repository for this endpoint
RUN git clone https://github.com/zeeshan8126/flux_kontext_pro.git .

# Install the Python dependencies from your requirements.txt file
# AND install the missing 'opencv-python' dependency for the ComfyI2I custom node.
RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install opencv-python-headless

# Set the entrypoint to run the handler script.
CMD ["python", "-u", "handler.py"]