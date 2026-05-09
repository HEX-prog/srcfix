import os
import json
import shutil
from typing import List, Dict, Any
from datetime import datetime

class ConfigManager:
    """Configuration file management system for EVENTURI-AI"""
    
    def __init__(self, config_dir: str = "config"):
        self.config_dir = config_dir
        self.ensure_config_dir()
    
    def ensure_config_dir(self):
        """Ensure config directory exists"""
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir)
    
    def get_config_files(self) -> List[str]:
        """Get list of all configuration files in config directory"""
        config_files = []
        if os.path.exists(self.config_dir):
            for file in os.listdir(self.config_dir):
                if file.endswith('.json'):
                    config_files.append(file[:-5])  # Remove .json extension
        return sorted(config_files)
    
    def get_config_path(self, config_name: str) -> str:
        """Get full path for a configuration file"""
        return os.path.join(self.config_dir, f"{config_name}.json")
    
    def config_exists(self, config_name: str) -> bool:
        """Check if a configuration file exists"""
        return os.path.exists(self.get_config_path(config_name))
    
    def create_config(self, config_name: str, config_data: Dict[str, Any]) -> bool:
        """Create a new configuration file"""
        try:
            config_path = self.get_config_path(config_name)
            if os.path.exists(config_path):
                return False  # Config already exists
            
            # Add metadata
            config_data['_metadata'] = {
                'created_at': datetime.now().isoformat(),
                'version': '1.0'
            }
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            
            return True
        except Exception as e:
            print(f"[ERROR] Failed to create config '{config_name}': {e}")
            return False
    
    def save_config(self, config_name: str, config_data: Dict[str, Any]) -> bool:
        """Save configuration data to file"""
        try:
            config_path = self.get_config_path(config_name)
            
            # Add metadata
            config_data['_metadata'] = {
                'updated_at': datetime.now().isoformat(),
                'version': '1.0'
            }
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            
            return True
        except Exception as e:
            print(f"[ERROR] Failed to save config '{config_name}': {e}")
            return False
    
    def load_config(self, config_name: str) -> Dict[str, Any]:
        """Load configuration data from file"""
        try:
            config_path = self.get_config_path(config_name)
            if not os.path.exists(config_path):
                return {}
            
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[ERROR] Failed to load config '{config_name}': {e}")
            return {}
    
    def delete_config(self, config_name: str) -> bool:
        """Delete a configuration file"""
        try:
            config_path = self.get_config_path(config_name)
            if os.path.exists(config_path):
                os.remove(config_path)
                return True
            return False
        except Exception as e:
            print(f"[ERROR] Failed to delete config '{config_name}': {e}")
            return False
    
    def rename_config(self, old_name: str, new_name: str) -> bool:
        """Rename a configuration file"""
        try:
            old_path = self.get_config_path(old_name)
            new_path = self.get_config_path(new_name)
            
            if not os.path.exists(old_path):
                return False
            
            if os.path.exists(new_path):
                return False  # Target already exists
            
            shutil.move(old_path, new_path)
            return True
        except Exception as e:
            print(f"[ERROR] Failed to rename config '{old_name}' to '{new_name}': {e}")
            return False
