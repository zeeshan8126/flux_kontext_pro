    # Start from an official NVIDIA base image that includes CUDA drivers
    FROM runpod/pytorch:2.2.0-py3.10-cuda12.1.1-devel-ubuntu22.04

    # Set the working directory inside the container
    WORKDIR /workspace/ComfyUI

    # Copy the requirements file first to leverage Docker cache
    COPY ./requirements.txt .

    # Install all Python dependencies
    RUN pip install --no-cache-dir -r requirements.txt

    # Copy the rest of your application code
    COPY . .

    # Expose the port ComfyUI runs on
    EXPOSE 8188

    # The command to run when the container starts
    # We add --listen to make it accessible from outside the container
    CMD ["python", "main.py", "--listen"]