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

# Debug all environment variables at startup
print(f"[STARTUP] Environment variable debugging:")
print(f"[STARTUP] Total environment variables: {len(os.environ)}")
auth_vars = [(k, v[:50] + '...' if len(v) > 50 else v) for k, v in os.environ.items() 
             if any(term in k.upper() for term in ['AUTH', 'TOKEN', 'API', 'KEY', 'COMFY', 'BFL'])]
if auth_vars:
    print(f"[STARTUP] Auth-related environment variables:")
    for k, v in auth_vars:
        print(f"[STARTUP]   {k}: {v}")
else:
    print(f"[STARTUP] No auth-related environment variables found")

# Check for common environment variable variations
possible_auth_vars = [
    'AUTH_TOKEN_COMFY_ORG', 'API_KEY_COMFY_ORG', 'COMFY_API_TOKEN', 'COMFY_API_KEY',
    'BFL_API_KEY', 'BLACKFORESTLABS_API_KEY', 'TOKEN_COMFY_ORG', 'KEY_COMFY_ORG'
]
print(f"[STARTUP] Checking for expected auth variables:")
for var in possible_auth_vars:
    value = os.environ.get(var)
    if value:
        print(f"[STARTUP]   {var}: SET ({value[:20]}...)")
    else:
        print(f"[STARTUP]   {var}: NOT SET")

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
    global server_process
    
    # Create a verification script to check environment variables in the subprocess
    verify_script = """
import os
import sys

print(f"[SUBPROCESS_VERIFY] Python executable: {sys.executable}")
print(f"[SUBPROCESS_VERIFY] Working directory: {os.getcwd()}")
print(f"[SUBPROCESS_VERIFY] Total environment variables: {len(os.environ)}")

# Check for auth-related environment variables
auth_vars = [(k, v[:50] + '...' if len(v) > 50 else v) for k, v in os.environ.items() 
             if any(term in k.upper() for term in ['AUTH', 'TOKEN', 'API', 'KEY', 'COMFY', 'BFL'])]
if auth_vars:
    print(f"[SUBPROCESS_VERIFY] Auth-related environment variables in subprocess:")
    for k, v in auth_vars:
        print(f"[SUBPROCESS_VERIFY]   {k}: {v}")
else:
    print(f"[SUBPROCESS_VERIFY] No auth-related environment variables found in subprocess")

# Check specific variables
possible_auth_vars = [
    'AUTH_TOKEN_COMFY_ORG', 'API_KEY_COMFY_ORG', 'COMFY_API_TOKEN', 'COMFY_API_KEY',
    'BFL_API_KEY', 'BLACKFORESTLABS_API_KEY', 'TOKEN_COMFY_ORG', 'KEY_COMFY_ORG'
]
print(f"[SUBPROCESS_VERIFY] Checking for expected auth variables in subprocess:")
for var in possible_auth_vars:
    value = os.environ.get(var)
    if value:
        print(f"[SUBPROCESS_VERIFY]   {var}: SET ({value[:20]}...)")
    else:
        print(f"[SUBPROCESS_VERIFY]   {var}: NOT SET")
"""
    
    # Write verification script
    with open("verify_env.py", "w") as f:
        f.write(verify_script)
    
    # Prepare environment variables
    env = os.environ.copy()
    
    # Log what we're passing to the subprocess
    print(f"[COMFYUI_START] Starting ComfyUI subprocess...")
    auth_token = env.get('AUTH_TOKEN_COMFY_ORG')
    api_key = env.get('API_KEY_COMFY_ORG')
    print(f"[COMFYUI_START] AUTH_TOKEN_COMFY_ORG: {'SET (' + auth_token[:20] + '...)' if auth_token else 'NOT SET'}")
    print(f"[COMFYUI_START] API_KEY_COMFY_ORG: {'SET (' + api_key[:20] + '...)' if api_key else 'NOT SET'}")
    
    # Ensure both are available in the subprocess environment
    # The BFL nodes read these directly from environment variables
    if auth_token:
        env['AUTH_TOKEN_COMFY_ORG'] = auth_token
        print(f"[COMFYUI_START] Set AUTH_TOKEN_COMFY_ORG in subprocess environment")
    
    if api_key:
        env['API_KEY_COMFY_ORG'] = api_key  
        print(f"[COMFYUI_START] Set API_KEY_COMFY_ORG in subprocess environment")
    
    # First run verification script
    print(f"[COMFYUI_START] Running environment verification in subprocess...")
    verify_process = subprocess.run(["python", "verify_env.py"], env=env, capture_output=True, text=True)
    print(f"[COMFYUI_START] Verification output:\n{verify_process.stdout}")
    if verify_process.stderr:
        print(f"[COMFYUI_START] Verification errors:\n{verify_process.stderr}")
    
    # Start ComfyUI
    cmd = ["python", "main.py", "--listen", "--port", "8188"]
    print(f"[COMFYUI_START] Starting ComfyUI with command: {' '.join(cmd)}")
    server_process = subprocess.Popen(cmd, env=env)
    print(f"[COMFYUI_START] ComfyUI process started with PID: {server_process.pid}")

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
    
    # Get both possible authentication tokens from environment
    auth_token = os.environ.get("AUTH_TOKEN_COMFY_ORG")
    api_key = os.environ.get("API_KEY_COMFY_ORG") 
    
    print(f"[AUTH_DEBUG] === COMPREHENSIVE AUTH DEBUGGING ===")
    print(f"[AUTH_DEBUG] AUTH_TOKEN_COMFY_ORG: {'SET (' + auth_token[:20] + '...)' if auth_token else 'NOT SET OR EMPTY'}")
    print(f"[AUTH_DEBUG] API_KEY_COMFY_ORG: {'SET (' + api_key[:20] + '...)' if api_key else 'NOT SET OR EMPTY'}")
    
    # For ComfyUI API proxy endpoints (like BFL), we need to use ONLY the ComfyUI platform API key
    # The ApiClient prioritizes auth_token (Bearer) over comfy_api_key (X-API-KEY)
    # But ComfyUI API expects X-API-KEY, so we should only set comfy_api_key
    
    # Use the ComfyUI platform API key (starts with "comfyui-") if available
    if api_key and api_key.startswith("comfyui-"):
        # Use direct parameter name that BFL nodes expect
        extra_data["comfy_api_key"] = api_key  # Maps to X-API-KEY header
        print(f"[AUTH_DEBUG] Using ComfyUI platform API key (comfy_api_key)")
    elif api_key:
        extra_data["comfy_api_key"] = api_key  # Use any API key available
        print(f"[AUTH_DEBUG] Using API_KEY_COMFY_ORG as comfy_api_key")
    elif auth_token:
        # Only fallback to auth_token if no proper API key is available
        extra_data["comfy_api_key"] = auth_token
        print(f"[AUTH_DEBUG] Fallback: Using AUTH_TOKEN_COMFY_ORG as comfy_api_key")
    
    # DO NOT set 'auth_token' key to avoid Bearer authentication
    # The ApiClient will use Bearer auth if auth_token is set, but we need X-API-KEY
    
    # Additional debugging: try both key naming conventions
    if api_key:
        # Also try the environment variable mapping style
        extra_data["api_key_comfy_org"] = api_key
        print(f"[AUTH_DEBUG] Also set api_key_comfy_org for compatibility")
    
    print(f"[AUTH_DEBUG] Strategy: Only using comfy_api_key to force X-API-KEY authentication")
    
    # If we have neither, that's an error
    if not auth_token and not api_key:
        print(f"[AUTH_DEBUG] ERROR: No authentication tokens found!")
        print(f"[AUTH_DEBUG] RunPod should set AUTH_TOKEN_COMFY_ORG and/or API_KEY_COMFY_ORG")
        print(f"[AUTH_DEBUG] Available environment variables:")
        for key in sorted(os.environ.keys()):
            if any(term in key.upper() for term in ['AUTH', 'TOKEN', 'API', 'KEY', 'COMFY']):
                value = os.environ[key]
                print(f"[AUTH_DEBUG]   {key}: {value[:30]}..." if len(value) > 30 else f"[AUTH_DEBUG]   {key}: {value}")
    
    print(f"[AUTH_DEBUG] Final extra_data: {extra_data}")
    print(f"[AUTH_DEBUG] This will use X-API-KEY header (not Bearer) for ComfyUI API")
    
    prompt_payload = {"prompt": workflow, "client_id": str(uuid.uuid4())}
    if extra_data:
        prompt_payload["extra_data"] = extra_data
    
    # Debug: Print the workflow being sent
    print(f"[WORKFLOW_DEBUG] Sending workflow to ComfyUI:")
    print(f"[WORKFLOW_DEBUG] Workflow has {len(workflow)} nodes")
    print(f"[WORKFLOW_DEBUG] Extra data keys: {list(extra_data.keys())}")
    
    prompt_data = json.dumps(prompt_payload).encode('utf-8')
    try:
        # Send request with proper Content-Type header
        headers = {'Content-Type': 'application/json'}
        print(f"[WORKFLOW_DEBUG] Sending POST request to http://{SERVER_ADDRESS}/prompt")
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
        print(f"[WORKFLOW_DEBUG] Got prompt_id: {prompt_id}")
        
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
                        print(f"[ERROR] Workflow failed with error: {error_details}")
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