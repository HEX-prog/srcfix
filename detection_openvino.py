"""
OpenVINO-optimized detection module for better performance and lower CPU usage
"""

import os
import cv2
import numpy as np
from config import config
import torch

# OpenVINO imports
OPENVINO_AVAILABLE = False
try:
    # Try the new import path first
    from openvino import Core, get_model
    from openvino.preprocess import PrePostProcessor
    OPENVINO_AVAILABLE = True
    print("[INFO] OpenVINO imported successfully (new path)")
except ImportError:
    try:
        # Try the old import path
        from openvino.runtime import Core, get_model
        from openvino.preprocess import PrePostProcessor
        OPENVINO_AVAILABLE = True
        print("[INFO] OpenVINO imported successfully (legacy path)")
    except ImportError:
        try:
            # Try just the core import
            from openvino import Core
            OPENVINO_AVAILABLE = True
            print("[INFO] OpenVINO Core imported successfully")
        except ImportError:
            OPENVINO_AVAILABLE = False
            print("[WARN] OpenVINO not available. Install with: pip install openvino")

# Fallback to YOLO if OpenVINO not available
if not OPENVINO_AVAILABLE:
    from ultralytics import YOLO

_model = None
_class_names = {}
_device = "CPU"  # OpenVINO device

def find_openvino_model(original_model_path):
    """Find pre-converted OpenVINO model for the given original model"""
    if not original_model_path:
        return None
    
    # Get the directory and base name
    model_dir = os.path.dirname(original_model_path)
    model_name = os.path.splitext(os.path.basename(original_model_path))[0]
    
    # Look for OpenVINO model with _openvino suffix
    openvino_xml = os.path.join(model_dir, f"{model_name}_openvino.xml")
    openvino_bin = os.path.join(model_dir, f"{model_name}_openvino.bin")
    
    if os.path.exists(openvino_xml) and os.path.exists(openvino_bin):
        return openvino_xml
    
    return None

def load_model(model_path=None):
    """Load model with OpenVINO optimization"""
    global _model, _class_names
    
    if model_path is None:
        model_path = config.model_path
    
    try:
        if not OPENVINO_AVAILABLE:
            print("[WARN] OpenVINO not available, falling back to PyTorch YOLO")
            return load_model_pytorch(model_path)
        
        print(f"[INFO] Loading {model_path} with OpenVINO optimization...")
        
        # Initialize OpenVINO Core
        core = Core()
        
        # Check if there's a pre-converted OpenVINO model
        openvino_model_path = find_openvino_model(model_path)
        
        if openvino_model_path:
            print(f"[INFO] Using pre-converted OpenVINO model: {openvino_model_path}")
            _model = core.read_model(openvino_model_path)
        elif model_path.endswith('.xml'):
            # Load OpenVINO model directly
            _model = core.read_model(model_path)
        elif model_path.endswith('.onnx'):
            # Load ONNX model directly with OpenVINO
            print(f"[INFO] Loading ONNX model with OpenVINO: {model_path}")
            _model = core.read_model(model_path)
        else:
            # Convert PyTorch model to OpenVINO format
            _model = convert_to_openvino(model_path, core)
        
        # Compile model for CPU
        compiled_model = core.compile_model(_model, _device)
        _model = compiled_model
        
        # Get class names (try to extract from model or use default)
        _class_names = extract_class_names(model_path)
        
        # Save model info
        config.model_classes = list(_class_names.values())
        config.model_file_size = os.path.getsize(model_path) if os.path.exists(model_path) else 0
        config.model_load_error = ""
        
        print(f"[SUCCESS] OpenVINO model loaded: {model_path}")
        print(f"[INFO] Device: {_device}, Classes: {len(_class_names)}")
        
        return _model, _class_names
        
    except Exception as e:
        print(f"[ERROR] OpenVINO model loading failed: {e}")
        print("[FALLBACK] Trying PyTorch YOLO...")
        return load_model_pytorch(model_path)

def load_model_pytorch(model_path):
    """Fallback to PyTorch YOLO if OpenVINO fails"""
    global _model, _class_names
    
    try:
        from ultralytics import YOLO
        print(f"[INFO] Loading {model_path} with PyTorch YOLO...")
        
        _model = YOLO(model_path, task="detect")
        
        # Get class names
        if hasattr(_model, "names"):
            _class_names = _model.names
        elif hasattr(_model.model, "names"):
            _class_names = _model.model.names
        else:
            _class_names = {}
            config.model_load_error = "Class names not found"
        
        # Save model info
        config.model_classes = list(_class_names.values())
        config.model_file_size = os.path.getsize(model_path) if os.path.exists(model_path) else 0
        config.model_load_error = ""
        
        print(f"[SUCCESS] PyTorch YOLO model loaded: {model_path}")
        return _model, _class_names
        
    except Exception as e:
        config.model_load_error = f"Failed to load model: {e}"
        _model = None
        _class_names = {}
        return None, {}

def convert_to_openvino(model_path, core):
    """Convert PyTorch/ONNX model to OpenVINO format"""
    try:
        # Try to load as ONNX first
        if model_path.endswith('.onnx'):
            return core.read_model(model_path)
        
        # For PyTorch models, we need to convert to ONNX first
        # This is a simplified approach - in production, you'd want to handle this more robustly
        print("[INFO] Converting PyTorch model to OpenVINO format...")
        
        # Load PyTorch model
        from ultralytics import YOLO
        yolo_model = YOLO(model_path, task="detect")
        
        # Export to ONNX
        onnx_path = model_path.replace('.pt', '.onnx')
        yolo_model.export(format='onnx', imgsz=640, optimize=True)
        
        # Load ONNX model
        return core.read_model(onnx_path)
        
    except Exception as e:
        print(f"[ERROR] Model conversion failed: {e}")
        raise e

def extract_class_names(model_path):
    """Extract class names from model or use defaults"""
    try:
        # Try to load class names from YOLO model
        from ultralytics import YOLO
        yolo_model = YOLO(model_path, task="detect")
        
        if hasattr(yolo_model, "names"):
            return yolo_model.names
        elif hasattr(yolo_model.model, "names"):
            return yolo_model.model.names
        else:
            # Default COCO classes
            return {i: f"class_{i}" for i in range(80)}
            
    except Exception:
        # Default COCO classes
        return {i: f"class_{i}" for i in range(80)}

def preprocess_image(image):
    """Apply lightweight image preprocessing optimized for OpenVINO"""
    # Lightweight contrast enhancement
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    
    # Simple contrast stretching
    l = cv2.convertScaleAbs(l, alpha=1.1, beta=5)
    
    # Merge channels back
    lab = cv2.merge([l, a, b])
    enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    
    # Lightweight sharpening
    kernel = np.array([[0,-1,0], [-1,5,-1], [0,-1,0]])
    sharpened = cv2.filter2D(enhanced, -1, kernel)
    
    # Blend original with enhanced
    result = cv2.addWeighted(sharpened, 0.5, image, 0.5, 0)
    
    return result

def preprocess_for_openvino(image, target_size=640):
    """Preprocess image specifically for OpenVINO inference"""
    # Resize image
    h, w = image.shape[:2]
    scale = min(target_size / h, target_size / w)
    new_h, new_w = int(h * scale), int(w * scale)
    
    resized = cv2.resize(image, (new_w, new_h))
    
    # Pad to square
    pad_h = target_size - new_h
    pad_w = target_size - new_w
    padded = cv2.copyMakeBorder(resized, 0, pad_h, 0, pad_w, cv2.BORDER_CONSTANT, value=(114, 114, 114))
    
    # Convert to RGB and normalize
    rgb = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB)
    normalized = rgb.astype(np.float32) / 255.0
    
    # Add batch dimension and transpose to NCHW
    input_tensor = np.expand_dims(normalized.transpose(2, 0, 1), axis=0)
    
    return input_tensor, scale, (new_h, new_w)

def postprocess_openvino_output(outputs, scale, original_size, conf_threshold=0.5, iou_threshold=0.4):
    """Postprocess OpenVINO model outputs to YOLO format"""
    try:
        # Extract predictions (assuming YOLOv8 format)
        predictions = outputs[0]  # Shape: [1, 84, 8400] for YOLOv8
        
        # Transpose to [1, 8400, 84]
        predictions = predictions.transpose(0, 2, 1)
        
        # Extract boxes and scores
        boxes = predictions[0, :, :4]  # [x_center, y_center, width, height]
        scores = predictions[0, :, 4:]  # class scores
        
        # Get max class scores and indices
        class_scores = np.max(scores, axis=1)
        class_ids = np.argmax(scores, axis=1)
        
        # Filter by confidence
        valid_indices = class_scores > conf_threshold
        boxes = boxes[valid_indices]
        class_scores = class_scores[valid_indices]
        class_ids = class_ids[valid_indices]
        
        if len(boxes) == 0:
            return []
        
        # Convert from center format to corner format
        x_center, y_center, width, height = boxes.T
        x1 = (x_center - width / 2) / scale
        y1 = (y_center - height / 2) / scale
        x2 = (x_center + width / 2) / scale
        y2 = (y_center + height / 2) / scale
        
        # Clip to image bounds
        x1 = np.clip(x1, 0, original_size[1])
        y1 = np.clip(y1, 0, original_size[0])
        x2 = np.clip(x2, 0, original_size[1])
        y2 = np.clip(y2, 0, original_size[0])
        
        # Apply NMS
        boxes_corners = np.column_stack([x1, y1, x2, y2])
        indices = cv2.dnn.NMSBoxes(
            boxes_corners.tolist(), 
            class_scores.tolist(), 
            conf_threshold, 
            iou_threshold
        )
        
        if len(indices) == 0:
            return []
        
        # Format results similar to YOLO output
        results = []
        for i in indices.flatten():
            results.append({
                'x1': int(x1[i]),
                'y1': int(y1[i]),
                'x2': int(x2[i]),
                'y2': int(y2[i]),
                'conf': float(class_scores[i]),
                'class': int(class_ids[i])
            })
        
        return results
        
    except Exception as e:
        print(f"[ERROR] OpenVINO postprocessing failed: {e}")
        return []

def perform_detection(model, image, imgsz=None, conf=None):
    """Perform detection using OpenVINO or PyTorch fallback"""
    global _model, _class_names
    
    if imgsz is None:
        imgsz = config.imgsz
    if conf is None:
        conf = config.conf
    
    try:
        # Check if we're using OpenVINO
        if OPENVINO_AVAILABLE and hasattr(model, 'infer'):
            return perform_openvino_detection(model, image, imgsz, conf)
        else:
            return perform_pytorch_detection(model, image, imgsz, conf)
            
    except Exception as e:
        print(f"[ERROR] Detection failed: {e}")
        return None

def perform_openvino_detection(model, image, imgsz, conf):
    """Perform detection using OpenVINO"""
    # Preprocess image
    processed_image = preprocess_image(image)
    input_tensor, scale, new_size = preprocess_for_openvino(processed_image, imgsz)
    
    # Run inference
    outputs = model.infer(inputs={'images': input_tensor})
    
    # Postprocess results
    results = postprocess_openvino_output(outputs, scale, image.shape[:2], conf)
    
    # Convert to YOLO-like format for compatibility
    class MockResult:
        def __init__(self, boxes, conf, cls):
            self.boxes = boxes
            self.conf = conf
            self.cls = cls
    
    # Create mock results that match YOLO format
    if results:
        boxes = np.array([[r['x1'], r['y1'], r['x2'], r['y2']] for r in results])
        confs = np.array([r['conf'] for r in results])
        classes = np.array([r['class'] for r in results])
        
        mock_result = MockResult(boxes, confs, classes)
        return [mock_result]
    else:
        return []

def perform_pytorch_detection(model, image, imgsz, conf):
    """Perform detection using PyTorch YOLO (fallback)"""
    # Apply image preprocessing
    processed_image = preprocess_image(image)
    
    # Run YOLO inference
    results = model.predict(
        source=processed_image,
        imgsz=imgsz,
        stream=False,
        conf=conf,
        iou=0.4,
        device="cpu",  # Force CPU for consistency
        half=False,    # Disable half precision for stability
        max_det=config.max_detect,
        agnostic_nms=False,
        augment=False,
        vid_stride=False,
        visualize=False,
        verbose=False,
        show_boxes=False,
        show_labels=False,
        show_conf=False,
        save=False,
        show=False
    )
    
    return results

def get_class_names():
    """Get class names"""
    return _class_names

def get_model_size(model_path=None):
    """Get model file size"""
    if not model_path:
        model_path = config.model_path
    return os.path.getsize(model_path) if os.path.exists(model_path) else 0

def reload_model(model_path):
    """Reload model"""
    return load_model(model_path)
