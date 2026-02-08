import json
import os
import sys

def main():
    # Paths
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    drugs_json_path = os.path.join(base_dir, "drugs.json")
    generated_data_dir = os.path.join(base_dir, "tools_2.0", "data")
    extracted_doses_path = os.path.join(generated_data_dir, "extracted_doses.json")

    print(f"Reading {drugs_json_path}...")
    if not os.path.exists(drugs_json_path):
        print(f"Error: {drugs_json_path} does not exist.")
        sys.exit(1)
    
    if not os.path.exists(extracted_doses_path):
         print(f"Error: {extracted_doses_path} does not exist.")
         sys.exit(1)

    try:
        with open(drugs_json_path, 'r', encoding='utf-8') as f:
            drugs_data = json.load(f)
        
        ordered_pretty_names = []
        for key, value in drugs_data.items():
            if "pretty_name" in value:
                ordered_pretty_names.append(value["pretty_name"])
            else:
                 # If no pretty_name, maybe use key or name? The C# code specifically looked for pretty_name
                 pass
        
        print(f"Reading {extracted_doses_path}...")
        with open(extracted_doses_path, 'r', encoding='utf-8') as f:
            extracted_data = json.load(f)

        # Reorder
        reordered_data = {}
        count = 0
        for pretty_name in ordered_pretty_names:
            if pretty_name in extracted_data:
                reordered_data[pretty_name] = extracted_data[pretty_name]
                count += 1
        
        # Add any remaining keys that weren't in ordered list? 
        # C# code only added keys that appeared in orderedPrettyNames. 
        # "if (extractedNode[prettyName] != null)"
        # So it filters out entries not in drugs.json or not having pretty_name match.
        # It implies extracted_doses.json keys are pretty names.

        print(f"Reordered {count} entries.")

        with open(extracted_doses_path, 'w', encoding='utf-8') as f:
            json.dump(reordered_data, f, indent=4, ensure_ascii=False)
        
        print(f"Successfully reordered {extracted_doses_path} to match drugs.json order.")

    except Exception as e:
        print(f"An error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
