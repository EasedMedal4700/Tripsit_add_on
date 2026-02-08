import json
import requests
from bs4 import BeautifulSoup
import re
import os
import yaml
from collections import defaultdict
import math

def load_config():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    config_path = os.path.join(base_dir, 'config.yaml')
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    return {}

def load_erowid_links():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base_dir, 'data', 'substances_erowid_links.json')
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    config = load_config()
    max_sub = config.get('max_substances')
    if isinstance(max_sub, int):
        print(f"Limiting usage to first {max_sub} substances based on config.")
        limited_data = {}
        for i, (k, v) in enumerate(data.items()):
            if i >= max_sub: break
            limited_data[k] = v
        return limited_data
    
    return data

def load_drugs_json_order():
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        path = os.path.join(base_dir, 'drugs.json')
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            order = []
            for k, v in data.items():
                if 'pretty_name' in v:
                    order.append(v['pretty_name'])
            return order
    except Exception as e:
        print(f"Could not load drugs.json for ordering: {e}")
        return []

def get_report_links(category_url):
    response = requests.get(category_url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    
    report_links = []
    # Find links to individual reports, usually in <a> with href like /experiences/exp.php?ID=...
    for a in soup.find_all('a', href=re.compile(r'/experiences/exp\.php\?ID=\d+')):
        report_links.append('https://www.erowid.org' + a['href'])
    
    return report_links

def extract_doses_from_report(report_url, substance):
    response = requests.get(report_url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Find the report text
    report_div = soup.find('div', class_='report-text') or soup.find('div', id='report')
    if not report_div:
        text = soup.get_text()
    else:
        text = report_div.get_text()
    
    # Find doses using regex
    # Pattern: dose unit method substance
    dose_pattern = re.compile(r'(\d+(?:\.\d+)?)\s*(mg|g|ug|µg|ml|drops?|capsules?)\s*(oral|IM|IV|SC|intranasal|smoked|insufflated|rectal|subcutaneous|intravenous|buccal|sublingual|intramuscular|intravenous|subcutaneous)\s*([A-Za-z0-9,\-\s]+?)(?:\s*\(|$)', re.IGNORECASE)
    matches = dose_pattern.findall(text)
    
    doses = []
    for match in matches:
        dose_amount, unit, method, sub_name = match
        dose = f"{dose_amount} {unit}"
        # Clean substance name
        sub_name = re.sub(r'\s+', ' ', sub_name.strip())
        sub_name = re.sub(r'[^\w\s,-]', '', sub_name)  # Remove special chars except , - space
        # If the report is for the target substance, but since we might have multiple, collect all
        doses.append({'substance': sub_name, 'dose': dose, 'method': method.lower()})
    
    return doses

def extract_dose_from_category(category_url, substance):
    report_links = get_report_links(category_url)
    print(f"Found {len(report_links)} report links")
    
    all_doses = []
    # Limit to first 1 for testing/speed
    for url in report_links[:1]:
        try:
            doses = extract_doses_from_report(url, substance)
            all_doses.extend(doses)
            print(f"  Report {url}: found {len(doses)} doses")
        except Exception as e:
            print(f"  Error scraping {url}: {e}")
    
    return all_doses

def analyze_doses(doses):
    # Parse doses to (number, unit)
    parsed = []
    for d in doses:
        # Basic cleanup and parsing
        d_str = d.strip().lower()
        # regex for value and unit
        match = re.match(r'(\d+(?:\.\d+)?)\s*([a-zµ]+)', d_str)
        if match:
            val = float(match.group(1))
            unit = match.group(2)
            parsed.append((val, unit))
    
    if not parsed:
        return None

    # Normalize units if possible? (e.g. g vs mg). For now assume majority unit or separate?
    # Simple check: take the most common unit
    unit_counts = defaultdict(int)
    for _, u in parsed:
        unit_counts[u] += 1
    most_common_unit = max(unit_counts, key=unit_counts.get)
    
    # Filter for most common unit to be safe
    valid_doses = [p[0] for p in parsed if p[1] == most_common_unit]
    valid_doses.sort()
    
    count = len(valid_doses)
    distribution = defaultdict(int)
    for v in valid_doses:
        distribution[v] += 1
        
    stats = {
        "total_reports": count,
        "distribution": {f"{k} {most_common_unit}": v for k, v in sorted(distribution.items())}
    }
    
    ranges = {
        "Threshold": "",
        "Light": "",
        "Common": "",
        "Strong": "",
        "Heavy": "",
        "Dangerous": "",
        "Fatal": "Unknown",
        "_stats": stats
    }
    
    unit = most_common_unit
    
    if count == 0:
        return None
        
    if count == 1:
        ranges["Common"] = f"{valid_doses[0]} {unit}"
        return ranges
        
    if count < 5:
        # Small sample size, just give the range in Common
        min_v = valid_doses[0]
        max_v = valid_doses[-1]
        range_str = f"{min_v} {unit}" if min_v == max_v else f"{min_v}-{max_v} {unit}"
        ranges["Common"] = range_str
        return ranges

    # Quantiles for larger samples
    def get_p(pct):
        return valid_doses[min(int(count * pct), count-1)]
        
    p10 = get_p(0.10)
    p30 = get_p(0.30)
    p70 = get_p(0.70)
    p90 = get_p(0.90)
    
    # Helper to format
    def fmt(start, end):
        if start == end:
            return f"{start} {unit}"
        return f"{start}-{end} {unit}"

    # Threshold: lowest to p10
    if valid_doses[0] <= p10:
        ranges["Threshold"] = fmt(valid_doses[0], p10)
    
    # Light: p10 to p30
    if p30 > p10:
        ranges["Light"] = fmt(p10, p30)
        
    # Common: p30 to p70
    if p70 >= p30:
         ranges["Common"] = fmt(p30, p70)
    
    # Strong: p70 to p90
    if p90 > p70:
        ranges["Strong"] = fmt(p70, p90)
        
    # Heavy: p90+
    ranges["Heavy"] = f"{p90}+ {unit}"

    return ranges

    report_links = get_report_links(category_url)
    print(f"Found {len(report_links)} report links")
    
    all_doses = []
    # Limit to first 5 for testing
    for url in report_links[:5]:
        try:
            doses = extract_doses_from_report(url, substance)
            all_doses.extend(doses)
            print(f"  Report {url}: found {len(doses)} doses")
        except Exception as e:
            print(f"  Error scraping {url}: {e}")
    
    return all_doses

def extract_dose_from_chemicals(substance):
    # Normalize substance to code
    code = substance.lower().replace(',', '_').replace(' ', '_').replace('-', '_')
    
    main_url = f"https://www.erowid.org/chemicals/{code}/{code}.shtml"
    print(f"Trying main URL: {main_url}")
    
    try:
        response = requests.get(main_url)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch main URL {main_url}: {e}")
        return {}
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Check for dose link
    dose_link = soup.find('a', href=re.compile(rf'{re.escape(code)}_dose\.shtml'))
    if dose_link:
        dose_url = f"https://www.erowid.org/chemicals/{code}/{code}_dose.shtml"
        print(f"Found dose link, fetching {dose_url}")
        try:
            response = requests.get(dose_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
        except requests.exceptions.RequestException as e:
            print(f"Failed to fetch dose URL {dose_url}: {e}")
            return {}
    else:
        print("No dose link, parsing main page")
    
    # Find the dose header
    dose_header = None
    for tag in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'b', 'strong', 'p']):
        if 'dose' in tag.get_text().lower():
            dose_header = tag
            print(f"Found dose header: {tag.name} - {tag.get_text().strip()}")
            break
    if dose_header:
        table = dose_header.find_next('table')
    else:
        # No header, find the first table
        table = soup.find('table')
        print("No dose header, using first table")
    
    if not table:
        print("No dose table found")
        return {}
    
    doses = {}
    rows = table.find_all('tr')
    for row in rows:
        cells = row.find_all(['td', 'th'])
        if len(cells) > 1:
            method = cells[0].get_text().strip()
            if method and method.lower() not in ['method', 'route']:  # Skip header
                doses[method] = {}
                categories = ['Threshold', 'Light', 'Common', 'Strong', 'Heavy', 'Dangerous', 'Fatal']
                for i, cat in enumerate(categories, 1):
                    if i < len(cells):
                        value = cells[i].get_text().strip()
                        if value and value != '-':
                            doses[method][cat] = value
    
    return doses

def main():
    erowid_links = load_erowid_links()
    
    all_doses = defaultdict(lambda: defaultdict(list))
    
    # Process all substances with erowid links
    for substance in erowid_links:
        print(f"Processing {substance}")
        for cat, url in erowid_links[substance].items():
            print(f"  Category: {cat}")
            try:
                doses = extract_dose_from_category(url, substance)
                print(f"    Found {len(doses)} doses")
                for dose_info in doses:
                    sub = dose_info['substance']
                    meth = dose_info['method']
                    dos = dose_info['dose']
                    all_doses[sub][meth].append(dos)
            except Exception as e:
                print(f"    Error processing category {url}: {e}")
    
    # Process all_doses to create formatted_dose
    formatted_data = {}
    for sub, methods in all_doses.items():
        formatted_dose = {}
        for method, doses in methods.items():
            # Remove duplicates? No, keep them for stats in analyze_doses
            # unique_doses = list(set(doses))
            
            # Analyze doses
            ranges = analyze_doses(doses)
            if ranges:
                formatted_dose[method] = ranges
        if formatted_dose:
            formatted_data[sub] = {'formatted_dose': formatted_dose}
    
    # Sort data according to drugs.json
    order = load_drugs_json_order()
    sorted_formatted_data = {}
    
    # First add keys present in order
    for key in order:
        if key in formatted_data:
            sorted_formatted_data[key] = formatted_data[key]
            
    # Then add any remaining keys (in case of mismatches)
    for key in sorted(formatted_data.keys()):
        if key not in sorted_formatted_data:
            sorted_formatted_data[key] = formatted_data[key]

    # Save to tools_2.0/data/extracted_doses.json
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_path = os.path.join(base_dir, 'data', 'extracted_doses.json')
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(sorted_formatted_data, f, indent=2, ensure_ascii=False)
    
    print(f"Saved extracted doses to {output_path}")

if __name__ == "__main__":
    main()