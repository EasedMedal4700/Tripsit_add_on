import os
import json
import glob
from utils import load_json, save_json, normalize
import datetime

class DataManager:
    def __init__(self, config_manager, base_dir):
        self.config = config_manager
        self.base_dir = base_dir # tools_2.0 directory
        
    def resolve_path(self, path_key):
        # Get path from config 'paths' section
        rel_path = self.config.get('paths', path_key)
        if not rel_path: return None
        return os.path.join(self.base_dir, rel_path)

    def load_drugs_list(self):
        path = self.resolve_path('drugs_json_file')
        data = load_json(path)
        
        order = []
        lookup = {}
        for key, val in data.items():
            if 'pretty_name' in val:
                pname = val['pretty_name']
                order.append(pname)
                lookup[normalize(pname)] = pname
        return order, lookup

    def load_erowid_links(self):
        path = self.resolve_path('substance_links_file')
        return load_json(path)

    def load_progress(self):
        path = self.resolve_path('progress_file')
        return load_json(path)

    def update_progress(self, url, status):
        path = self.resolve_path('progress_file')
        # Load existing (inefficient but safe)
        data = load_json(path)
        data[url] = status
        save_json(path, data)

    def save_temp_report(self, report_id, data):
        temp_dir = self.resolve_path('temp_dir')
        path = os.path.join(temp_dir, f"dose_{report_id}.json")
        save_json(path, data)

    def save_missing_dose_log(self, data):
        path = self.resolve_path('missing_doses_file')
        # Append or overwrite? Using simpler overwrite for now
        # We should probably load existing and append
        existing = load_json(path, [])
        existing.append(data)
        save_json(path, existing)

    def load_json_absolute(self, rel_path):
        return load_json(os.path.join(self.base_dir, rel_path))

    def save_json_absolute(self, rel_path, data):
        save_json(os.path.join(self.base_dir, rel_path), data)

    def merge_temp_files(self):
        temp_dir = self.resolve_path('temp_dir')
        files = glob.glob(os.path.join(temp_dir, "*.json"))
        merged = []
        for f in files:
            try:
                with open(f, 'r', encoding='utf-8') as jf:
                     merged.append(json.load(jf))
            except: pass
        return merged

    def save_final_output(self, data):
        output_dir = self.resolve_path('output_dir')
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"extracted_doses_{timestamp}.json"
        save_json(os.path.join(output_dir, filename), data)
