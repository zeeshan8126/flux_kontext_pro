# ComfyUI as a Flexible, Serverless API

This repository contains a full ComfyUI setup configured to run as a scalable, on-demand API endpoint using RunPod Serverless. It has been customized to include the `Flux.1 Kontext Pro Image` node and dynamically builds its workflow to handle a variable number of input images (from 2 to 5).

## Overview

Instead of sending a complex workflow object with every request, this API is designed for simplicity. You send only the data that changes with each job—the prompt, the images, and key parameters—and the server intelligently constructs the correct ComfyUI workflow on the fly.

## How to Deploy

1.  **Commit & Push:** Ensure all your latest changes, including the final `handler.py` and this `README.md`, are committed and pushed to this GitHub repository.
2.  **Navigate to RunPod:** Go to the **Serverless -> Endpoints** section in your RunPod dashboard.
3.  **Create New Endpoint:**
    *   Click "**New Endpoint**".
    *   Give your endpoint a memorable name.
    *   In the template selection area, click the button to **"Deploy from a repository"**.
    *   Paste the URL of this GitHub repository: `https://github.com/zeeshan8126/flux_kontext_pro.git`.
4.  **Build and Deploy:** RunPod will automatically use the `Dockerfile` in this repository to build your serverless worker. This build process can take 15-20 minutes.
5.  **Wait for Activation:** Once the build is complete, your endpoint will become active and ready to receive API calls.

## API Usage

To use the deployed endpoint, you need to send a `POST` request to its `/runsync` URL with a simplified JSON payload.

### API Request Structure

*   **URL:** `https://api.runpod.ai/v2/YOUR_ENDPOINT_ID/runsync`
*   **Method:** `POST`
*   **Headers:**
    *   `Content-Type: application/json`
    *   `Authorization: Bearer YOUR_RUNPOD_API_KEY`
*   **Body:** A JSON object with the following structure:
    *   `prompt` (string, required): Your detailed editing instruction.
    *   `images` (array, required): An array containing 1 to 5 image objects.
        *   `name` (string): A unique filename for the image.
        *   `image` (string): The Base64 encoded data for the image.
    *   `aspect_ratio` (string, optional): The desired output aspect ratio (e.g., "1:1", "16:9"). Defaults to "1:1".
    *   `guidance` (number, optional): A value to control prompt upsampling. Values > 7.5 will enable it. Defaults to a value that keeps it disabled.
    *   `steps` (integer, optional): The number of sampling steps. Defaults to 50.
    *   `seed` (integer, optional): The random seed for generation. Defaults to 1234.

### API Response Structure

The API will return a JSON object containing the results. The `data` field will contain the full Base64 encoded PNG data for each generated image.

```json
{
  "images": [
    {
      "filename": "Final_Output_00001_.png",
      "data": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgA..."
    }
  ]
}
```


### Example: 2-Image Payload with Optional Parameters

```json
{
  "input": {
    "prompt": "Place the person into the new background scene",
    "aspect_ratio": "16:9",
    "guidance": 8.0,
    "images": [
      {
        "name": "person_photo.png",
        "image": "data:image/png;base64,iVBORw0KGgoAAA..."
      },
      {
        "name": "new_background.png",
        "image": "data:image/png;base64,R0lGODlhAQABAIAAAP..."
      }
    ]
  }
}
```

### Example: 5-Image Payload

```json
{
  "input": {
    "prompt": "Combine all five elements into a single cohesive scene",
    "aspect_ratio": "1:1",
    "guidance": 7.0,
    "images": [
      { "name": "image1.png", "image": "data:image/png;base64,..." },
      { "name": "image2.png", "image": "data:image/png;base64,..." },
      { "name": "image3.png", "image": "data:image/png;base64,..." },
      { "name": "image4.png", "image": "data:image/png;base64,..." },
      { "name": "image5.png", "image": "data:image/png;base64,..." }
    ]
  }
}
```

### Important Notes

*   **Models:** This worker assumes the necessary models for the ComfyUI nodes are already present in the environment. For a production setup, you would typically modify the `Dockerfile` to download your required models (e.g., from Hugging Face) into the `/app/models/checkpoints/` directory during the build process.
*   **`class_type` Names:** The `handler.py` script uses the verified `class_type` names `FluxKontextProImageNode` and `ImageStitch`. If you change the nodes, these names must be updated in the script.
