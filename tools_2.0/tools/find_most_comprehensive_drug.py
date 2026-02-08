import json
import os
import sys

def count_non_empty_fields(obj):
    count = 0
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "combos":
                continue
            if is_non_empty(value):
                count += 1
    return count

def is_non_empty(value):
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (int, float, bool)):
        return True
    if isinstance(value, list):
        return len(value) > 0
    if isinstance(value, dict):
        return len(value) > 0
    return False

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    drugs_json_path = os.path.join(base_dir, "drugs.json")

    if not os.path.exists(drugs_json_path):
        print(f"Error: {drugs_json_path} does not exist.")
        sys.exit(1)

    try:
        with open(drugs_json_path, 'r', encoding='utf-8') as f:
            drugs = json.load(f)

        most_comprehensive_drug = None
        max_count = 0

        for drug_name, drug_data in drugs.items():
            count = count_non_empty_fields(drug_data)
            if count > max_count:
                max_count = count
                most_comprehensive_drug = drug_name

        print(f"Most comprehensive drug: {most_comprehensive_drug} with {max_count} filled fields.")

    except Exception as e:
        print(f"An error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
