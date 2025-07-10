import runpod
import subprocess
import threading
import time
import requests
import json
import uuid
import os
import base64
import copy

# ---------------------------------- Globals --------------------------------- #
server_process = None
SERVER_ADDRESS = "127.0.0.1:8188"
comfyui_started = False

# -------------------------- Dynamic Workflow Builder -------------------------- #
def build_workflow(num_images):
    """Dynamically builds a workflow to chain-stitch a variable number of images."""
    workflow = {}
    load_node_ids = []
    for i in range(num_images):
        node_id = str(10 + i)
        load_node_ids.append(node_id)
        workflow[node_id] = {"class_type": "LoadImage", "inputs": {"image": f"image_{i+1}.png"}}

    last_stitch_node_id = ""
    if num_images >= 2:
        stitch_node_id = "20"
        last_stitch_node_id = stitch_node_id
        workflow[stitch_node_id] = {
            "class_type": "ImageStitch",
            "inputs": {"image1": [load_node_ids[0], 0], "image2": [load_node_ids[1], 0]}
        }
        for i in range(2, num_images):
            prev_stitch_node_id = last_stitch_node_id
            stitch_node_id = str(20 + i - 1)
            last_stitch_node_id = stitch_node_id
            workflow[stitch_node_id] = {
                "class_type": "ImageStitch",
                "inputs": {"image1": [prev_stitch_node_id, 0], "image2": [load_node_ids[i], 0]}
            }
    
    bfl_input_node_id = load_node_ids[0] if num_images == 1 else last_stitch_node_id
    
    bfl_node = {
        "class_type": "FluxKontextProImageNode",
        "inputs": {
            "prompt": "Default prompt",
            "prompt_upsampling": False,
            "guidance": 3.0,
            "aspect_ratio": "16:9",
            "steps": 50, # Default value
            "seed": 1234,  # Default value
            "input_image": [bfl_input_node_id, 0]
        }
    }
    workflow["30"] = bfl_node
    workflow["31"] = {"class_type": "SaveImage", "inputs": {"filename_prefix": "Final_Output", "images": ["30", 0]}}
    
    return workflow

# ------------------------------ ComfyUI Server & Helpers ------------------------------ #
def start_comfyui_server():
    global server_process; cmd = ["python", "main.py", "--listen", "--port", "8188"]; server_process = subprocess.Popen(cmd)

def wait_for_server_ready():
    global comfyui_started
    while not comfyui_started:
        try:
            if requests.get(f"http://{SERVER_ADDRESS}/history/1", timeout=2).status_code in [200, 404]:
                comfyui_started = True
        except requests.exceptions.RequestException: pass
        if not comfyui_started: time.sleep(1)

def prepare_inputs(images):
    input_dir = "/app/input"; os.makedirs(input_dir, exist_ok=True)
    for image_data in images:
        name, b64_img = image_data.get("name"), image_data.get("image")
        if not name or not b64_img: continue
        if ',' in b64_img: b64_img = b64_img.split(',', 1)[1]
        try:
            with open(os.path.join(input_dir, name), 'wb') as f: f.write(base64.b64decode(b64_img))
        except Exception: pass

def get_image_data(filename, subfolder, image_type):
    """Reads an image file and returns its Base64 encoded data."""
    filepath = os.path.join("/app", image_type, subfolder, filename)
    try:
        with open(filepath, 'rb') as f:
            encoded_string = base64.b64encode(f.read()).decode('utf-8')
        return f"data:image/png;base64,{encoded_string}"
    except IOError:
        return None

def run_workflow(workflow):
    prompt_data = json.dumps({"prompt": workflow, "client_id": str(uuid.uuid4())}).encode('utf-8')
    try:
        req = requests.post(f"http://{SERVER_ADDRESS}/prompt", data=prompt_data); req.raise_for_status()
        prompt_id = req.json()['prompt_id']
        
        # Add timeout to prevent infinite loops
        max_wait_time = 300  # 5 minutes timeout
        start_time = time.time()
        
        while True:
            # Check for timeout
            if time.time() - start_time > max_wait_time:
                return {"error": "Workflow execution timed out after 5 minutes"}
            
            res = requests.get(f"http://{SERVER_ADDRESS}/history/{prompt_id}")
            if res.status_code == 200:
                history = res.json()
                if prompt_id in history:
                    prompt_history = history[prompt_id]
                    
                    # Check if workflow failed
                    if prompt_history.get('status', {}).get('status_str') == 'error':
                        error_details = prompt_history.get('status', {}).get('messages', [])
                        return {"error": f"Workflow failed: {error_details}"}
                    
                    # Check if workflow completed successfully
                    if prompt_history.get('outputs'):
                        outputs = prompt_history['outputs']
                        images_output = []
                        for node in outputs.values():
                            for img in node.get('images', []):
                                img_data = get_image_data(img['filename'], img['subfolder'], img['type'])
                                if img_data:
                                    images_output.append({"filename": img['filename'], "data": img_data})
                        return {"images": images_output}
            
            time.sleep(0.5)
    except Exception as e: 
        return {"error": f"Workflow execution failed: {e}"}

# --------------------------------- RunPod Handler --------------------------------- #
def handler(job):
    print(f"[HANDLER] Starting job processing...")
    if not comfyui_started: 
        print("[HANDLER] ERROR: ComfyUI server is not ready")
        return {"error": "ComfyUI server is not ready."}
    
    # Check for API authentication
    auth_token = os.environ.get("AUTH_TOKEN_COMFY_ORG")
    api_key = os.environ.get("API_KEY_COMFY_ORG")
    if not auth_token or not api_key:
        print("[HANDLER] WARNING: Missing API authentication credentials")
        print("[HANDLER] Please set AUTH_TOKEN_COMFY_ORG and API_KEY_COMFY_ORG environment variables")
        return {"error": "Missing API authentication credentials. Please set AUTH_TOKEN_COMFY_ORG and API_KEY_COMFY_ORG environment variables."}
    
    job_input = job['input']; images = job_input.get('images', [])
    num_images = len(images)
    print(f"[HANDLER] Processing {num_images} images")
    
    if not (1 <= num_images <= 5): # Now allows 1 to 5 images
        print(f"[HANDLER] ERROR: Invalid number of images: {num_images}")
        return {"error": f"This endpoint requires 1 to 5 images, but {num_images} were provided."}

    print("[HANDLER] Preparing input images...")
    prepare_inputs(images)
    
    print("[HANDLER] Building workflow...")
    final_workflow = build_workflow(num_images)

    for i in range(num_images):
        final_workflow[str(10 + i)]["inputs"]["image"] = images[i]["name"]

    api_node = final_workflow["30"]["inputs"]
    api_node["prompt"] = job_input.get('prompt', "Default prompt")
    api_node["aspect_ratio"] = job_input.get('aspect_ratio', '16:9')
    api_node["steps"] = job_input.get('steps', 50)
    api_node["seed"] = job_input.get('seed', 1234)
    
    guidance_value = job_input.get('guidance', 3.0)
    api_node["guidance"] = guidance_value
    api_node["prompt_upsampling"] = job_input.get('prompt_upsampling', False)

    print(f"[HANDLER] Final workflow parameters:")
    print(f"  - Prompt: {api_node['prompt']}")
    print(f"  - Aspect ratio: {api_node['aspect_ratio']}")
    print(f"  - Guidance: {api_node['guidance']}")
    print(f"  - Steps: {api_node['steps']}")
    print(f"  - Prompt upsampling: {api_node['prompt_upsampling']}")
    
    print("[HANDLER] Executing workflow...")
    return run_workflow(final_workflow)

if __name__ == "__main__":
    server_thread = threading.Thread(target=start_comfyui_server); server_thread.daemon = True; server_thread.start()
    wait_for_server_ready()
    runpod.serverless.start({"handler": handler})