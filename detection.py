
from ultralytics import YOLO
import os
from config import config
import torch

_model = None
_class_names = {}
if torch.cuda.is_available():
    DEVICE = 0               
else:
    DEVICE = "cpu"
def load_model(model_path=None):
    global _model, _class_names
    if model_path is None:
        model_path = config.model_path
    try:
        print(f"Loading {model_path} for ONNX Runtime inference...")
        _model = YOLO(model_path, task="detect")
        # Get class names
        if hasattr(_model, "names"):
            _class_names = _model.names
        elif hasattr(_model.model, "names"):
            _class_names = _model.model.names
        else:
            _class_names = {}
            config.model_load_error = "Class names not found"
        # Save available classes and model size
        config.model_classes = list(_class_names.values())
        config.model_file_size = os.path.getsize(model_path) if os.path.exists(model_path) else 0
        config.model_load_error = ""
        print(f"Successfully loaded model: {model_path}")
        return _model, _class_names
    except Exception as e:
        config.model_load_error = f"Failed to load model: {e}"
        _model = None
        _class_names = {}
        return None, {}

def reload_model(model_path):
    return load_model(model_path)

def preprocess_image(image):
    """Apply optimized lightweight image preprocessing"""
    import cv2
    import numpy as np
    
    # Simple contrast enhancement (reduced processing)
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    
    # Light contrast stretching for better performance
    l = cv2.convertScaleAbs(l, alpha=1.05, beta=3)
    
    # Merge channels back
    lab = cv2.merge([l, a, b])
    enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    
    # Very light sharpening
    kernel = np.array([[0,-0.25,0], [-0.25,2,-0.25], [0,-0.25,0]], dtype=np.float32)
    sharpened = cv2.filter2D(enhanced, -1, kernel)
    
    # Light blending (25% enhanced, 75% original for minimal processing)
    result = cv2.addWeighted(sharpened, 0.25, image, 0.75, 0)
    
    return result

def perform_detection(model, image):
    """Simple, stable detection like the stable version"""
    try:
        results = model.predict(
            source=image,  # No preprocessing - use raw image like stable version
            imgsz=config.imgsz,
            stream=True,        # Use stream=True like stable version
            conf=config.conf,
            iou=0.5,           # Use stable version's IoU
            device=DEVICE,
            half=True,
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
        
    except Exception as e:
        print(f"[ERROR] Detection failed: {e}")
        return None

def get_class_names():
    return _class_names

def get_model_size(model_path=None):
    if not model_path:
        model_path = config.model_path
    return os.path.getsize(model_path) if os.path.exists(model_path) else 0
