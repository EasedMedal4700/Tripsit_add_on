import os
import yaml

class ConfigManager:
    def __init__(self, config_path):
        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self):
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found at {self.config_path}")
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def get(self, section, key, default=None):
        return self.config.get(section, {}).get(key, default)

    def get_section(self, section):
        return self.config.get(section, {})
