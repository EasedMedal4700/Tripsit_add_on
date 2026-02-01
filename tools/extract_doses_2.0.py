import json
import requests
from bs4 import BeautifulSoup
import re
import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import math
import yaml

# -------------------------
# Config
# -------------------------

CONFIG_FILE = "config.yaml"
EROWID_LINKS_JSON_PATH = "../substances_erowid_links.json"
DRUGS_JSON_PATH = "../drugs.json"
OUTPUT_FILE = "data/extracted_doses.json"
MAX_WORKERS = 10  # Reduced to be safer, increase if reliable
MAX_REPORTS_PER_CATEGORY = 5  # Limit reports for speed 

# Categories to scan
VALID_CATEGORIES = {
    "General", "First Times", "Combinations", "Retrospective / Summary",
    "Preparation / Recipes", "Difficult Experiences", "Bad Trips",
    "Health Problems", "Train Wrecks & Trip Disasters", "Addiction & Habituation",
    "Glowing Experiences", "Mystical Experiences", "Health Benefits",
    "Families", "What Was in That?",
}

# -------------------------
# Utilities
# -------------------------

def normalize(name: str) -> str:
    """Normalize substance names for matching."""
    return re.sub(r"[- ,]", "", name.lower())

def load_drugs_json():
    """Load drugs.json to get substance list and order."""
    if not os.path.exists(DRUGS_JSON_PATH):
        print(f"Error: {DRUGS_JSON_PATH} not found.")
        return [], {}
        
    with open(DRUGS_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    order = []
    lookup = {}
    for key, val in data.items():
        if 'pretty_name' in val:
            pname = val['pretty_name']
            order.append(pname)
            lookup[normalize(pname)] = pname
            
    return order, lookup

def load_erowid_links_json():
    if not os.path.exists(EROWID_LINKS_JSON_PATH):
        print(f"Error: {EROWID_LINKS_JSON_PATH} not found.")
        return {}
    with open(EROWID_LINKS_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

# -------------------------
# Scraping Logic
# -------------------------

def get_report_urls(session, category_url):
    """Fetch a category page and get individual report URLs."""
    try:
        response = session.get(category_url, timeout=20)
        
        # Check for block
        if response.status_code == 403 or "Blocked" in response.text[:500]:
            print("Blocked by Erowid (403). stopping these requests.")
            return 'BLOCKED'
            
        soup = BeautifulSoup(response.text, "html.parser")
        
        urls = []
        for a in soup.find_all('a', href=re.compile(r'exp\.php\?ID=\d+')):
            url = 'https://www.erowid.org/experiences/' + a['href']
            if url not in urls:
                urls.append(url)
        return urls
    except Exception as e:
        # print(f"Error fetching {category_url}: {e}")
        return []

def extract_doses_from_text(text):
    """Parse text for dose info."""
    # Pattern: dose unit method substance
    dose_pattern = re.compile(r'(\d+(?:\.\d+)?)\s*(mg|g|ug|µg|ml|drops?|capsules?)\s*(oral|IM|IV|SC|intranasal|smoked|insufflated|rectal|subcutaneous|intravenous|buccal|sublingual|intramuscular|intravenous|subcutaneous)\s*([A-Za-z0-9,\-\s]+?)(?:\s*\(|$)', re.IGNORECASE)
    matches = dose_pattern.findall(text)
    
    results = []
    for match in matches:
        dose_amount, unit, method, sub_name = match
        dose = f"{dose_amount} {unit}"
        # Clean substance name
        clean_sub = re.sub(r'\s+', ' ', sub_name.strip())
        clean_sub = re.sub(r'[^\w\s,-]', '', clean_sub)
        results.append({'substance': clean_sub, 'dose': dose, 'method': method.lower()})
    return results

def process_report(session, report_url):
    """Fetch report and extract doses."""
    try:
        response = session.get(report_url, timeout=20)
        
        if response.status_code == 403 or "Blocked" in response.text[:500]:
            return 'BLOCKED'

        soup = BeautifulSoup(response.text, "html.parser")
        
        report_div = soup.find('div', class_='report-text') or soup.find('div', id='report')
        text = report_div.get_text() if report_div else soup.get_text()
        
        return extract_doses_from_text(text)
    except:
        return []

# -------------------------
# Analysis Logic 
# -------------------------

def analyze_doses(doses):
    # Parse doses to (number, unit)
    parsed = []
    for d in doses:
        d_str = d.strip().lower()
        match = re.match(r'(\d+(?:\.\d+)?)\s*([a-zµ]+)', d_str)
        if match:
            val = float(match.group(1))
            unit = match.group(2)
            parsed.append((val, unit))
    
    if not parsed:
        return None

    unit_counts = defaultdict(int)
    for _, u in parsed:
        unit_counts[u] += 1
    most_common_unit = max(unit_counts, key=unit_counts.get)
    
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
        "Threshold": "", "Light": "", "Common": "", "Strong": "", "Heavy": "",
        "Dangerous": "", "Fatal": "Unknown", "_stats": stats
    }
    
    unit = most_common_unit
    
    if count == 0: return None
        
    if count == 1:
        ranges["Common"] = f"{valid_doses[0]} {unit}"
        return ranges
        
    if count < 5:
        min_v = valid_doses[0]
        max_v = valid_doses[-1]
        range_str = f"{min_v} {unit}" if min_v == max_v else f"{min_v}-{max_v} {unit}"
        ranges["Common"] = range_str
        return ranges

    def get_p(pct):
        return valid_doses[min(int(count * pct), count-1)]
        
    p10 = get_p(0.10)
    p30 = get_p(0.30)
    p70 = get_p(0.70)
    p90 = get_p(0.90)
    
    def fmt(start, end):
        return f"{start} {unit}" if start == end else f"{start}-{end} {unit}"

    if valid_doses[0] <= p10: ranges["Threshold"] = fmt(valid_doses[0], p10)
    if p30 > p10: ranges["Light"] = fmt(p10, p30)
    if p70 >= p30: ranges["Common"] = fmt(p30, p70)
    if p90 > p70: ranges["Strong"] = fmt(p70, p90)
    ranges["Heavy"] = f"{p90}+ {unit}"

    return ranges

# -------------------------
# Main 
# -------------------------

def main():
    start_time = time.time()
    
    # 1. Load Drugs
    drugs_order, drugs_lookup = load_drugs_json()
    print(f"Loaded {len(drugs_order)} drugs from drugs.json.")
    
    # 2. Load Erowid Links directly
    erowid_data = load_erowid_links_json()
    print(f"Loaded Erowid links for {len(erowid_data)} substances.")

    # Load Config
    max_substances = "ALL"
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            config = yaml.safe_load(f)
            max_substances = config.get('max_substances', "ALL")
            
    # Apply limit
    if isinstance(max_substances, int):
        print(f"Debug Mode: Limiting to first {max_substances} substances.")
        # Slice the dictionary
        limited_erowid_data = {}
        for i, (k, v) in enumerate(erowid_data.items()):
            if i >= max_substances: break
            limited_erowid_data[k] = v
        erowid_data = limited_erowid_data

    session = requests.Session()
    headers = {'User-Agent': 'TripSit Drug Database Scraper (https://tripsit.me) - Volunteer at TripSit, fquaaden@gmail.com'}
    session.headers.update(headers)

    # 3. Gather Category URLs
    # Structure: substance -> category_name -> url
    all_category_urls = set()
    for sub, cats in erowid_data.items():
        for cat, url in cats.items():
            if cat in VALID_CATEGORIES:
                all_category_urls.add(url)
    
    print(f"Processing {len(all_category_urls)} category URLs...")
    
    # 4. Fetch Reports URLs
    all_report_urls = set()
    blocked = False
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(get_report_urls, session, url): url for url in all_category_urls}
        
        cnt = 0
        for future in as_completed(futures):
            res = future.result()
            if res == 'BLOCKED':
                blocked = True
                executor.shutdown(wait=False, cancel_futures=True)
                break
            
            if res:
                for u in res[:MAX_REPORTS_PER_CATEGORY]:
                    all_report_urls.add(u)
            cnt += 1
            if cnt % 50 == 0:
                print(f"Scraped {cnt} categories...")
    
    if blocked:
        print("Scraping stopped due to Erowid Block.")
        
    print(f"Found {len(all_report_urls)} unique reports to scrape.")
    
    # 5. Scrape Reports
    all_doses = defaultdict(lambda: defaultdict(list))
    
    cnt = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_report, session, url): url for url in all_report_urls}
        for future in as_completed(futures):
            cnt += 1
            if cnt % 50 == 0:
                print(f"Processed {cnt}/{len(all_report_urls)} reports...")
            
            res = future.result()
            if res == 'BLOCKED':
                print("Blocked during report scraping.")
                break
                
            for item in res:
                all_doses[item['substance']][item['method']].append(item['dose'])

    # 6. Analyze and Format
    formatted_data = {}
    for sub, methods in all_doses.items():
        formatted_dose = {}
        for method, doses in methods.items():
            rng = analyze_doses(doses)
            if rng:
                formatted_dose[method] = rng
        if formatted_dose:
            formatted_data[sub] = {'formatted_dose': formatted_dose}

    # 7. Sort and Save
    normalized_data = {}
    for sub, data in formatted_data.items():
        normalized_data[normalize(sub)] = data
        
    final_output = {}
    
    for pretty_name in drugs_order:
        norm = normalize(pretty_name)
        if norm in normalized_data:
            final_output[pretty_name] = normalized_data[norm]
            
    for sub, data in formatted_data.items():
        if normalize(sub) not in [normalize(x) for x in drugs_order]:
            final_output[sub] = data

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_output, f, indent=2, ensure_ascii=False)
        
    print(f"Done! Saved to {OUTPUT_FILE}")
    print(f"Total time: {time.time() - start_time:.2f}s")
    if blocked:
        print("Warning: Process was incomplete due to IP block.")

if __name__ == "__main__":
    main()
