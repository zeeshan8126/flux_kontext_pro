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

# Verify critical dependencies at startup
try:
    import numpy as np
    print(f"[STARTUP] NumPy version: {np.__version__}")
except ImportError as e:
    print(f"[STARTUP] CRITICAL ERROR: NumPy not available: {e}")
    raise

# ---------------------------------- Globals --------------------------------- #
server_process = None
SERVER_ADDRESS = "127.0.0.1:8188"
comfyui_started = False

# -------------------------- Dynamic Workflow Builder -------------------------- #
def build_workflow(num_images):
    """Dynamically builds a workflow to chain-stitch a variable number of images."""
    print(f"[WORKFLOW] Building workflow for {num_images} images")
    
    workflow = {}
    load_node_ids = []
    
    # Build LoadImage nodes
    for i in range(num_images):
        node_id = str(10 + i)
        load_node_ids.append(node_id)
        workflow[node_id] = {
            "class_type": "LoadImage", 
            "inputs": {"image": f"image_{i+1}.png"}
        }
        print(f"[WORKFLOW] Added LoadImage node {node_id} for image_{i+1}.png")

    # Build ImageStitch nodes if multiple images
    last_stitch_node_id = ""
    if num_images >= 2:
        stitch_node_id = "20"
        last_stitch_node_id = stitch_node_id
        workflow[stitch_node_id] = {
            "class_type": "ImageStitch",
            "inputs": {
                "image1": [load_node_ids[0], 0], 
                "image2": [load_node_ids[1], 0],
                "direction": "right",
                "match_image_size": True,
                "spacing_width": 0,
                "spacing_color": "white"
            }
        }
        print(f"[WORKFLOW] Added first ImageStitch node {stitch_node_id}")
        
        # Chain additional images
        for i in range(2, num_images):
            prev_stitch_node_id = last_stitch_node_id
            stitch_node_id = str(20 + i - 1)
            last_stitch_node_id = stitch_node_id
            workflow[stitch_node_id] = {
                "class_type": "ImageStitch",
                "inputs": {
                    "image1": [prev_stitch_node_id, 0], 
                    "image2": [load_node_ids[i], 0],
                    "direction": "right",
                    "match_image_size": True,
                    "spacing_width": 0,
                    "spacing_color": "white"
                }
            }
            print(f"[WORKFLOW] Added chained ImageStitch node {stitch_node_id}")
    
    # Determine input for FluxKontextProImageNode
    bfl_input_node_id = load_node_ids[0] if num_images == 1 else last_stitch_node_id
    print(f"[WORKFLOW] BFL input will come from node {bfl_input_node_id}")
    
    # Build FluxKontextProImageNode
    bfl_node = {
        "class_type": "FluxKontextProImageNode",
        "inputs": {
            "prompt": "Default prompt",
            "prompt_upsampling": False,
            "guidance": 3.0,
            "aspect_ratio": "16:9",
            "steps": 50,
            "seed": 1234,
            "input_image": [bfl_input_node_id, 0]
        }
    }
    workflow["30"] = bfl_node
    print(f"[WORKFLOW] Added FluxKontextProImageNode")
    
    # Build SaveImage node
    workflow["31"] = {
        "class_type": "SaveImage", 
        "inputs": {
            "filename_prefix": "Final_Output", 
            "images": ["30", 0]
        }
    }
    print(f"[WORKFLOW] Added SaveImage node")
    
    # Validate workflow structure
    print(f"[WORKFLOW] Workflow validation:")
    print(f"[WORKFLOW] - Total nodes: {len(workflow)}")
    print(f"[WORKFLOW] - LoadImage nodes: {len(load_node_ids)}")
    print(f"[WORKFLOW] - ImageStitch nodes: {max(0, num_images - 1)}")
    print(f"[WORKFLOW] - API nodes: 1 (FluxKontextProImageNode)")
    print(f"[WORKFLOW] - SaveImage nodes: 1")
    
    return workflow

# ------------------------------ ComfyUI Server & Helpers ------------------------------ #
def validate_workflow(workflow):
    """Validate workflow structure before sending to ComfyUI"""
    print("[VALIDATION] Checking workflow structure...")
    
    # Check for required nodes
    required_classes = ["LoadImage", "FluxKontextProImageNode", "SaveImage"]
    found_classes = set()
    
    for node_id, node_data in workflow.items():
        class_type = node_data.get("class_type")
        if class_type:
            found_classes.add(class_type)
        
        # Check node structure
        if "inputs" not in node_data:
            print(f"[VALIDATION] ERROR: Node {node_id} missing 'inputs'")
            return False
        
        # Check for proper connections
        inputs = node_data["inputs"]
        for input_name, input_value in inputs.items():
            if isinstance(input_value, list) and len(input_value) == 2:
                source_node, output_index = input_value
                if source_node not in workflow:
                    print(f"[VALIDATION] ERROR: Node {node_id} references non-existent node {source_node}")
                    return False
    
    # Check if we have all required classes
    missing_classes = set(required_classes) - found_classes
    if missing_classes:
        print(f"[VALIDATION] ERROR: Missing required node classes: {missing_classes}")
        return False
    
    print(f"[VALIDATION] Found node classes: {sorted(found_classes)}")
    print("[VALIDATION] Workflow structure looks valid")
    return True

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

def check_server_health():
    """Check ComfyUI server health and available nodes"""
    try:
        # Test basic connectivity
        response = requests.get(f"http://{SERVER_ADDRESS}/history/1", timeout=5)
        print(f"[HEALTH] Server status: {response.status_code}")
        
        # Try to get object info (available nodes)
        try:
            object_info_response = requests.get(f"http://{SERVER_ADDRESS}/object_info", timeout=5)
            if object_info_response.status_code == 200:
                object_info = object_info_response.json()
                print(f"[HEALTH] Available node classes: {len(object_info)} nodes")
                
                # Check for our required nodes
                required_nodes = ["LoadImage", "FluxKontextProImageNode", "SaveImage", "ImageStitch"]
                missing_nodes = []
                for node in required_nodes:
                    if node not in object_info:
                        missing_nodes.append(node)
                
                if missing_nodes:
                    print(f"[HEALTH] WARNING: Missing required nodes: {missing_nodes}")
                    # List available nodes that might be similar
                    available_nodes = list(object_info.keys())
                    print(f"[HEALTH] Available nodes (first 20): {available_nodes[:20]}")
                else:
                    print(f"[HEALTH] All required nodes are available")
                    
                return True, missing_nodes
            else:
                print(f"[HEALTH] Could not get object info: {object_info_response.status_code}")
        except Exception as e:
            print(f"[HEALTH] Error getting object info: {e}")
            
        return True, []
    except Exception as e:
        print(f"[HEALTH] Server health check failed: {e}")
        return False, []

def prepare_inputs(images):
    input_dir = "input"; os.makedirs(input_dir, exist_ok=True)
    for image_data in images:
        name, b64_img = image_data.get("name"), image_data.get("image")
        if not name or not b64_img: continue
        if ',' in b64_img: b64_img = b64_img.split(',', 1)[1]
        try:
            with open(os.path.join(input_dir, name), 'wb') as f: f.write(base64.b64decode(b64_img))
        except Exception: pass

def get_image_data(filename, subfolder, image_type):
    """Reads an image file and returns its Base64 encoded data."""
    filepath = os.path.join(image_type, subfolder, filename)
    try:
        with open(filepath, 'rb') as f:
            encoded_string = base64.b64encode(f.read()).decode('utf-8')
        return f"data:image/png;base64,{encoded_string}"
    except IOError:
        return None

def run_workflow(workflow):
    # Validate workflow before sending
    if not validate_workflow(workflow):
        return {"error": "Workflow validation failed - check logs for details"}
    
    # Include authentication credentials in extra_data for API nodes
    extra_data = {}
    auth_token = os.environ.get("AUTH_TOKEN_COMFY_ORG")
    api_key = os.environ.get("API_KEY_COMFY_ORG")
    
    # DEBUG: Print authentication status for troubleshooting
    print(f"[AUTH_DEBUG] AUTH_TOKEN_COMFY_ORG: {'SET (' + auth_token[:20] + '...)' if auth_token else 'NOT SET OR EMPTY'}")
    print(f"[AUTH_DEBUG] API_KEY_COMFY_ORG: {'SET (' + api_key[:20] + '...)' if api_key else 'NOT SET OR EMPTY'}")
    
    if auth_token:
        extra_data["auth_token_comfy_org"] = auth_token
    if api_key:
        extra_data["api_key_comfy_org"] = api_key
    
    prompt_payload = {"prompt": workflow, "client_id": str(uuid.uuid4())}
    if extra_data:
        prompt_payload["extra_data"] = extra_data
    
    # Debug: Print the workflow being sent
    print(f"[DEBUG] Sending workflow to ComfyUI:")
    print(f"[DEBUG] Workflow structure: {json.dumps(workflow, indent=2)}")
    print(f"[DEBUG] Extra data: {extra_data}")
    
    prompt_data = json.dumps(prompt_payload).encode('utf-8')
    try:
        # Send request with proper Content-Type header
        headers = {'Content-Type': 'application/json'}
        req = requests.post(f"http://{SERVER_ADDRESS}/prompt", data=prompt_data, headers=headers)
        
        # Debug: Print response details for 400 errors
        if req.status_code == 400:
            print(f"[ERROR] ComfyUI returned 400 Bad Request")
            print(f"[ERROR] Response content: {req.text}")
            try:
                error_data = req.json()
                print(f"[ERROR] Parsed error: {json.dumps(error_data, indent=2)}")
            except:
                print(f"[ERROR] Could not parse error response as JSON")
            return {"error": f"ComfyUI workflow validation failed: {req.text}"}
        
        req.raise_for_status()
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
        print(f"[ERROR] Exception in run_workflow: {str(e)}")
        return {"error": f"Workflow execution failed: {e}"}

# --------------------------------- RunPod Handler --------------------------------- #
def handler(job):
    print(f"[HANDLER] Starting job processing...")
    if not comfyui_started: 
        print("[HANDLER] ERROR: ComfyUI server is not ready")
        return {"error": "ComfyUI server is not ready."}
    
    # Check server health and available nodes
    server_healthy, missing_nodes = check_server_health()
    if not server_healthy:
        return {"error": "ComfyUI server is not responding properly"}
    
    if missing_nodes:
        return {"error": f"Required ComfyUI nodes are not available: {missing_nodes}. Please check your ComfyUI installation."}
    
    # Note: Authentication credentials are now handled by ComfyUI system via extra_data
    # The credentials will be checked when the API node executes
    
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