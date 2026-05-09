"""
OpenVINO-optimized version of main.py for better performance
"""

# Import the original main.py and override the detection module
import sys
import os

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Override the detection module before importing main
import detection_openvino as detection
sys.modules['detection'] = detection

# Now import and run the main application
if __name__ == "__main__":
    # Import the main application
    from Eventuri_AI import EventuriGUI
    
    # Create and run the GUI
    app = EventuriGUI()
    app.run()
