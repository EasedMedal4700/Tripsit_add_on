import json
import yaml
import os
import re
from typing import Dict, Any, Optional, Tuple

class DoseComparator:
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config = self._load_config()
        self.drugs_data = {}
        self.extracted_data = {}
        self.report = {
            "summary": {"total_compared": 0, "identical": 0, "minor_diff": 0, "major_diff": 0, "new_data": 0, "missing_data": 0},
            "details": {}
        }

    def _load_config(self) -> Dict[str, Any]:
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def load_data(self):
        drugs_path = os.path.join(os.path.dirname(self.config_path), self.config['compare']['drugs_file'])
        extracted_path = os.path.join(os.path.dirname(self.config_path), self.config['compare']['extracted_doses_file'])

        # Resolve paths relative to the script/config location or CWD if needed
        # Assuming config paths are relative to the config file location for simplicity, or CWD.
        # Let's try absolute path resolution if they don't exist
        if not os.path.exists(drugs_path):
             # Try relative to CWD
             drugs_path = self.config['compare']['drugs_file']
        
        if not os.path.exists(extracted_path):
             extracted_path = self.config['compare']['extracted_doses_file']

        print(f"Loading drugs.json from: {drugs_path}")
        with open(drugs_path, 'r', encoding='utf-8') as f:
            self.drugs_data = json.load(f)

        print(f"Loading extracted doses from: {extracted_path}")
        with open(extracted_path, 'r', encoding='utf-8') as f:
            self.extracted_data = json.load(f)

    def parse_dose(self, dose_str: str) -> Optional[Dict[str, Any]]:
        if not dose_str or dose_str.lower() == "unknown":
            return None
        
        # Regex to capture numeric range and unit
        # Examples: "10-20 mg", "50 ug", "1.5 g", "0.5-1.0 ml"
        match = re.search(r'([\d\.]+)(?:-([\d\.]+))?\s*([a-zA-Z]+)?', dose_str)
        if match:
            min_val = float(match.group(1))
            max_val = float(match.group(2)) if match.group(2) else min_val
            unit = match.group(3).lower() if match.group(3) else ""
            return {"min": min_val, "max": max_val, "unit": unit}
        return None

    def compare_values(self, old_val: float, new_val: float) -> str:
        if old_val == 0:
            return "major" if new_val != 0 else "identical"
        
        diff_ratio = abs(new_val - old_val) / old_val
        minor_thresh = self.config['compare']['thresholds'].get('minor', 0.1)
        major_thresh = self.config['compare']['thresholds'].get('major', 0.5)

        if diff_ratio <= minor_thresh:
            return "identical" # Treat as identical if within minor threshold? Or distinct category?
                               # User asked: "if the dose arent that diffrent it doesnt flag it"
                               # So maybe "identical" or "negligible"
        elif diff_ratio <= major_thresh:
            return "minor"
        else:
            return "major"

    def compare_dose_entry(self, old_dose: str, new_dose: str) -> Dict[str, Any]:
        parsed_old = self.parse_dose(old_dose)
        parsed_new = self.parse_dose(new_dose)

        if not parsed_old and not parsed_new:
            return {"status": "identical", "diff": None}
        if not parsed_old and parsed_new:
            return {"status": "new_data", "diff": f"New: {new_dose}"}
        if parsed_old and not parsed_new:
            return {"status": "missing_data", "diff": f"Was: {old_dose}"}
        
        # Check if units are compatible
        # Basic normalization for comparison
        unit_old = parsed_old['unit']
        unit_new = parsed_new['unit']
        
        if unit_old != unit_new:
             return {"status": "major_diff", "diff": f"Unit mismatch: {unit_old} vs {unit_new}"}

        min_status = self.compare_values(parsed_old['min'], parsed_new['min'])
        max_status = self.compare_values(parsed_old['max'], parsed_new['max'])

        if min_status == "major" or max_status == "major":
            return {"status": "major_diff", "diff": f"{old_dose} -> {new_dose}"}
        elif min_status == "minor" or max_status == "minor":
            # If user said "dose arent that diffrent it doesnt flag it", maybe we don't flag minor? 
            # But "create a tiering system in it not a black and white mdoel" suggests we should categorize it.
            return {"status": "minor_diff", "diff": f"{old_dose} -> {new_dose}"}
        
        return {"status": "identical", "diff": None}

    def run_comparison(self):
        # We iterate over extracted data to see if it matches drugs.json
        # Case insensitive mapping for drugs.json keys
        drugs_map = {k.lower(): k for k in self.drugs_data.keys()}

        for drug_name, new_data in self.extracted_data.items():
            drug_lower = drug_name.lower()
            if drug_lower not in drugs_map:
                # Completely new drug or name mismatch
                self.report['details'][drug_name] = {"status": "new_drug", "msg": "Drug not found in drugs.json"}
                continue
            
            original_key = drugs_map[drug_lower]
            existing_drug = self.drugs_data[original_key]
            
            existing_formatted = existing_drug.get('formatted_dose', {})
            new_formatted = new_data.get('formatted_dose', {})

            if not new_formatted:
                continue

            drug_report = {}
            has_changes = False
            max_severity = 0 # 0: same, 1: minor, 2: major

            # Compare Routes
            # Normalize keys to lowercase for comparison
            formatted_existing_lower = {k.lower(): v for k, v in existing_formatted.items()}
            formatted_new_lower = {k.lower(): v for k, v in new_formatted.items()}
            
            all_routes = set(list(formatted_existing_lower.keys()) + list(formatted_new_lower.keys()))
            
            for route in all_routes:
                if route == "_stats": continue
                
                if route not in formatted_existing_lower:
                    drug_report[route] = "New Route"
                    has_changes = True
                    # Treat new route as 'new_data' which might be minor or major depending on preference
                    max_severity = max(max_severity, 1) 
                    continue
                
                # If missing in new, extraction might just not have picked it up. Only flag if needed.
                if route not in formatted_new_lower:
                    continue

                route_changes = {}
                existing_route = formatted_existing_lower[route]
                new_route = formatted_new_lower[route]

                # Levels: Threshold, Light, Common, Strong, Heavy
                levels = ["Threshold", "Light", "Common", "Strong", "Heavy", "Fatal"]
                
                for level in levels:
                    # Case insensitive level check? Usually Title Case in both
                    # But keys might be inconsistent. Let's assume title case "Light", "Common" etc based on snippet.
                    val_old = existing_route.get(level)
                    val_new = new_route.get(level)

                    res = self.compare_dose_entry(val_old, val_new)
                    if res['status'] != "identical":
                        route_changes[level] = res
                        if "major" in res['status']:
                            max_severity = max(max_severity, 2)
                        elif "minor" in res['status']:
                            max_severity = max(max_severity, 1)
                        elif "new" in res['status']:
                            max_severity = max(max_severity, 1) # Treat new data as minor/interesting
                
                if route_changes:
                    drug_report[route] = route_changes
                    has_changes = True

            if has_changes:
                status_label = "minor_diff" if max_severity == 1 else "major_diff"
                if max_severity == 0: status_label = "identical" # Should be covered but just in case
                
                self.report['summary'][status_label] += 1
                self.report['details'][drug_name] = {
                    "status": status_label,
                    "changes": drug_report
                }
            else:
                self.report['summary']['identical'] += 1

        self.report['summary']['total_compared'] = len(self.extracted_data)
        
        output_file = self.config['compare']['output_file']
        # Resolve output file relative to config file location just like input files
        if not os.path.isabs(output_file):
            output_file = os.path.join(os.path.dirname(self.config_path), output_file)
            
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        print(f"Writing report to {output_file}")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.report, f, indent=2)

if __name__ == "__main__":
    # Assuming config is in same dir as script
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    comparator = DoseComparator(config_path)
    comparator.load_data()
    comparator.run_comparison()
