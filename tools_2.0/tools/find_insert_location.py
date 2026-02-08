import json
import sys
import os
import unicodedata
import re

def slugify(value):
    """
    Normalizes string, converts to lowercase, removes non-alpha characters,
    and converts spaces to hyphens.
    """
    value = str(value)
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value).strip().lower()
    value = re.sub(r'[-\s]+', '-', value)
    return value

def generate_snippet(slug, pretty_name):
    snippet = {
        slug: {
            "aliases": [slug],
            "categories": [],
            "name": slug,
            "pretty_name": pretty_name,
            "properties": {
                "summary": "Add a short summary here."
            }
        }
    }
    # Convert to JSON string but remove the outer braces to make it a snippet
    json_str = json.dumps(snippet, indent=4)
    # Remove first and last lines (brackets)
    lines = json_str.split('\n')
    return '\n'.join(lines[1:-1])

def main():
    if len(sys.argv) < 2:
        print("Usage: python find_insert_location.py <Drug Name> [drugs.json path]")
        sys.exit(1)

    drug_name = sys.argv[1]
    
    # Determine path to drugs.json
    # Default to ../../drugs.json relative to this script
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    default_json_path = os.path.join(base_dir, "drugs.json")
    
    json_path = sys.argv[2] if len(sys.argv) > 2 else default_json_path

    if not os.path.exists(json_path):
        print(f"Error: {json_path} not found.")
        sys.exit(2)

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            # We want to find line numbers, so we parse manually or use a library that preserves order/lines?
            # The java version read lines to find line numbers. 
            # Ideally we just want the keys in order. 
            # Let's verify we can find the keys.
            
            # Simple approach: Read file as lines to find line numbers for keys
            f.seek(0)
            lines = f.readlines()
            
        keys = []
        for i, line in enumerate(lines):
            line = line.strip()
            # Match "key": {  at top level roughly
             # Regex for "key": {
            match = re.match(r'^"([^"]+)":\s*\{', line)
            if match:
                keys.append({'key': match.group(1), 'line': i + 1})

        if not keys:
            print(f"No top-level keys found in {json_path}")
            sys.exit(3)

        keys.sort(key=lambda x: x['key'])

        slug = slugify(drug_name)

        # Check if exists
        for kp in keys:
            if kp['key'] == slug:
                print(f"Found existing key '{kp['key']}' at line {kp['line']} in {json_path}")
                sys.exit(0)

        # Find insertion index
        insert_index = 0
        while insert_index < len(keys) and keys[insert_index]['key'] < slug:
            insert_index += 1

        prev_key = keys[insert_index - 1] if insert_index - 1 >= 0 else None
        next_key = keys[insert_index] if insert_index < len(keys) else None

        print(f"Suggested slug: '{slug}' (derived from '{drug_name}')")
        if prev_key:
            print(f"Insert after: '{prev_key['key']}' (line {prev_key['line']})")
        else:
            print(f"Insert at start (before: '{next_key['key']}' at line {next_key['line']})")
        
        if next_key:
            print(f"Insert before: '{next_key['key']}' (line {next_key['line']})")
        else:
            print(f"Insert at end (after: '{prev_key['key']}' at line {prev_key['line']})")

        print("\nSuggested JSON snippet (add comma if needed):")
        print(generate_snippet(slug, drug_name))

    except Exception as e:
        print(f"Error processing file: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
