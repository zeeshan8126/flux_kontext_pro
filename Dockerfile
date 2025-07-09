# Use a standard RunPod image with PyTorch and CUDA
FROM runpod/pytorch:2.2.0-py3.11-cuda12.1.1-devel-ubuntu22.04

# Set the working directory
WORKDIR /

# Install git and other essentials
RUN apt-get update && apt-get install -y git wget && rm -rf /var/lib/apt/lists/*

# Copy your entire ComfyUI project into the container
COPY . /app
WORKDIR /app

# Install all Python dependencies from your requirements file
RUN pip install --upgrade pip && pip install -r requirements.txt

# This is where you would add commands to install custom nodes.
# For example, to install the node from your repo (if it were separate):
# RUN git clone https://github.com/zeeshan8126/flux_kontext_pro.git ./custom_nodes/flux_kontext_pro
# Since your nodes are already inside the 'custom_nodes' directory, this step is covered by the main COPY command.

# Set the entrypoint for the RunPod worker
CMD ["python", "-u", "-m", "runpod.serverless"]