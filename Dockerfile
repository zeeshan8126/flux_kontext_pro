# Use a standard RunPod PyTorch image as the base
FROM runpod/pytorch:2.3.1-py3.12-cuda12.1.1-devel-ubuntu22.04

# Set the working directory inside the container
WORKDIR /app

# Install git so we can clone your repository
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Clone the correct repository for this endpoint
RUN git clone https://github.com/zeeshan8126/flux_kontext_pro.git .

# Install the Python dependencies from your requirements.txt file
RUN pip install --upgrade pip && pip install -r requirements.txt

# Set the entrypoint to run the handler script.
CMD ["python", "-u", "handler.py"]