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
import datetime
import random
import hashlib
import glob

# -------------------------
# Config
# -------------------------

# This file is in tools_2.0/tools/
# BASE_DIR should be tools_2.0/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_DIR = os.path.dirname(BASE_DIR)

CONFIG_FILE = os.path.join(ROOT_DIR, "config.yaml")
EROWID_LINKS_JSON_PATH = os.path.join(BASE_DIR, "data", "substances_erowid_links.json")
DRUGS_JSON_PATH = os.path.join(ROOT_DIR, "drugs.json")
PROGRESS_FILE = os.path.join(BASE_DIR, "data", "progress.json")
TEMP_DATA_DIR = os.path.join(BASE_DIR, "data", "temp_doses")

MAX_WORKERS = 4
MAX_REPORTS_PER_CATEGORY = 500

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
# Progress & Persistence
# -------------------------

def load_progress():
    if not os.path.exists(PROGRESS_FILE):
        return {}
    try:
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def update_progress(url, status):
    """Update progress for a specific URL."""
    try:
        # Optimization: Don't read-write for every single update if high volume, 
        # but for safety against crashes, we do it here.
        # Ideally we might hold a memory cache and flush every N updates, 
        # but to ensure "stop and resume" works perfectly, atomic writes are better.
        
        data = load_progress()
        data[url] = status
        with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=1)
    except Exception as e:
        print(f"[WARN] Failed to update progress for {url}: {e}")

def get_report_id(url):
    match = re.search(r'ID=(\d+)', url)
    if match:
        return match.group(1)
    return hashlib.md5(url.encode()).hexdigest()

def save_temp_report(url, doses):
    """Save the extraction result for a single report."""
    report_id = get_report_id(url)
    filename = os.path.join(TEMP_DATA_DIR, f"dose_{report_id}.json")
    data = {
        "url": url,
        "doses": doses,
        "timestamp": datetime.datetime.now().isoformat()
    }
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

# -------------------------
# Scraping Logic
# -------------------------

def get_report_urls(session, category_url):
    """Fetch a category page and get individual report URLs."""
    try:
        # Sleep randomly between 1-3 seconds to prevent blocks
        time.sleep(random.uniform(1.0, 3.0))
        response = session.get(category_url, timeout=20)
        
        # Check for block
        if response.status_code == 403 or "Blocked" in response.text[:500]:
            print(f"Blocked by Erowid (403) on {category_url}.")
            return 'BLOCKED'
            
        soup = BeautifulSoup(response.text, "html.parser")
        
        urls = []
        for a in soup.find_all('a', href=re.compile(r'exp\.php\?ID=\d+')):
            href = a['href']
            if href.startswith('http'):
                url = href
            elif href.startswith('/'):
                url = 'https://www.erowid.org' + href
            else:
                url = 'https://www.erowid.org/experiences/' + href
            
            if url not in urls:
                urls.append(url)
        return urls
    except Exception as e:
        # print(f"Error fetching {category_url}: {e}")
        return []

def extract_doses_from_text(text):
    """Parse text for dose info."""
    # Updated regex to handle '130 mg' style properly
    dose_pattern = re.compile(r'(\d+(?:\.\d+)?)\s*(mg|g|ug|µg|ml|drops?|capsules?)\s*(oral|IM|IV|SC|intranasal|smoked|insufflated|rectal|subcutaneous|intravenous|buccal|sublingual|intramuscular|intravenous|subcutaneous)\s*([A-Za-z0-9,\-\s]+?)(?:\s*\(|$)', re.IGNORECASE)
    matches = dose_pattern.findall(text)
    
    results = []
    for match in matches:
        dose_amount, unit, method, sub_name = match
        dose = f"{dose_amount} {unit}"
        clean_sub = re.sub(r'\s+', ' ', sub_name.strip())
        clean_sub = re.sub(r'[^\w\s,-]', '', clean_sub)
        results.append({'substance': clean_sub, 'dose': dose, 'method': method.lower()})
    return results

def process_report(session, report_url):
    """Fetch report and extract doses."""
    try:
        # Sleep randomly between 1-2 seconds
        time.sleep(random.uniform(1.0, 2.0))
        
        response = session.get(report_url, timeout=20)
        
        if response.status_code == 403 or "Blocked" in response.text[:500]:
            update_progress(report_url, "failed_blocked")
            return 'BLOCKED'

        soup = BeautifulSoup(response.text, "html.parser")
        
        report_div = soup.find('div', class_='report-text') or soup.find('div', id='report')
        text = report_div.get_text() if report_div else soup.get_text()
        
        results = extract_doses_from_text(text)
        
        # SAVE & UPDATE
        save_temp_report(report_url, results)
        update_progress(report_url, "done")
        
        return results
    except Exception as e:
        # print(f"Error processing {report_url}: {e}")
        update_progress(report_url, "failed")
        return []

# -------------------------
# Analysis Logic 
# -------------------------

def analyze_doses(doses):
    parsed = []
    for d in doses:
        d_str = d.strip().lower()
        d_str = d_str.replace(",", "")
        
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
    
    def fmt(start, end):
        return f"{start} {unit}" if start == end else f"{start}-{end} {unit}"
        
    if count < 5:
        min_v = valid_doses[0]
        max_v = valid_doses[-1]
        range_str = fmt(min_v, max_v)
        ranges["Common"] = range_str
        return ranges

    def get_p(pct):
        return valid_doses[min(int(count * pct), count-1)]
        
    p10 = get_p(0.10)
    p30 = get_p(0.30)
    p70 = get_p(0.70)
    p90 = get_p(0.90)

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
    
    os.makedirs(TEMP_DATA_DIR, exist_ok=True)
    
    print("-" * 50)
    print(f"Extract Doses Tool (Progress Tracking Enabled)")
    print(f"Progress File: {PROGRESS_FILE}")
    print(f"Temp Data Dir: {TEMP_DATA_DIR}")
    print("-" * 50)

    # 1. Load Drugs
    drugs_order, drugs_lookup = load_drugs_json()
    print(f"Loaded {len(drugs_order)} drugs from drugs.json.")
    
    # 2. Load Erowid Links directly
    erowid_data = load_erowid_links_json()
    print(f"Loaded Erowid links for {len(erowid_data)} substances.")

    # Load Progress
    progress = load_progress()
    print(f"Loaded {len(progress)} processed URLs from progress.json")

    # Load Config
    max_substances = "ALL"
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            config = yaml.safe_load(f)
            max_substances = config.get('max_substances', "ALL")
            
    # Apply limit
    if isinstance(max_substances, int):
        print(f"Debug Mode: Limiting to first {max_substances} substances.")
        limited_erowid_data = {}
        for i, (k, v) in enumerate(erowid_data.items()):
            if i >= max_substances: break
            limited_erowid_data[k] = v
        erowid_data = limited_erowid_data
    elif isinstance(max_substances, list):
         print(f"Debug Mode: Targeting specific substances: {max_substances}")
         limited = {}
         for k, v in erowid_data.items():
             if any(tgt.lower() == k.lower() for tgt in max_substances):
                 limited[k] = v
         erowid_data = limited

    session = requests.Session()
    headers = {'User-Agent': 'TripSit Drug Database Scraper (https://tripsit.me) - Volunteer at TripSit, fquaaden@gmail.com'}
    session.headers.update(headers)

    # 3. Gather Category URLs
    all_category_urls = set()
    VALID_CATEGORIES = {
    "General", "First Times", "Combinations", "Retrospective / Summary",
    "Preparation / Recipes", "Difficult Experiences", "Bad Trips",
    "Health Problems", "Train Wrecks & Trip Disasters", "Addiction & Habituation",
    "Glowing Experiences", "Mystical Experiences", "Health Benefits",
    "Families", "What Was in That?",
    }
    
    for sub, cats in erowid_data.items():
        for cat, url in cats.items():
            if cat in VALID_CATEGORIES:
                all_category_urls.add(url)
    
    print(f"Processing {len(all_category_urls)} category URLs...")
    
    # 4. Fetch Reports URLs
    all_report_urls = set()
    blocked = False
    
    # Optimization: Filter category URLs? 
    # Usually we need to re-scan categories to find new reports, 
    # but for now we re-scan them every time. 
    # We could cache category contents too, but that's overkill for now.
    
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
                print(f"Scanned {cnt} categories...")
    
    if blocked:
        print("Scraping stopped temporarily due to Erowid Block (during category phase).")
        
    print(f"Found {len(all_report_urls)} unique reports on category pages.")
    
    # FILTER URLs based on progress
    urls_to_scrape = [u for u in all_report_urls if progress.get(u) != "done"]
    skipped_count = len(all_report_urls) - len(urls_to_scrape)
    print(f"Skipping {skipped_count} already processed reports.")
    print(f"Queued {len(urls_to_scrape)} reports for scraping.")
    
    # 5. Scrape Reports
    cnt = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_report, session, url): url for url in urls_to_scrape}
        for future in as_completed(futures):
            cnt += 1
            if cnt % 10 == 0:
                print(f"Processed {cnt}/{len(urls_to_scrape)} reports...")
            
            res = future.result()
            if res == 'BLOCKED':
                print("Blocked during report scraping.")
                break

    print("Merging data...")
    # 6. Merge & Analyze logic
    all_doses = defaultdict(lambda: defaultdict(list))
    
    temp_files = glob.glob(os.path.join(TEMP_DATA_DIR, "*.json"))
    print(f"Found {len(temp_files)} temp data files to merge.")
    
    for tf in temp_files:
        try:
            with open(tf, 'r', encoding='utf-8') as f:
                tdata = json.load(f)
                doses_list = tdata.get('doses', [])
                if isinstance(doses_list, list):
                    for item in doses_list:
                        if 'substance' in item and 'method' in item and 'dose' in item:
                            all_doses[item['substance']][item['method']].append(item['dose'])
        except Exception as e:
            # print(f"Error reading {tf}: {e}")
            pass

    # 7. Analyze
    formatted_data = {}
    for sub, methods in all_doses.items():
        formatted_dose = {}
        for method, doses in methods.items():
            rng = analyze_doses(doses)
            if rng:
                formatted_dose[method] = rng
        if formatted_dose:
            formatted_data[sub] = {'formatted_dose': formatted_dose}

    # 8. Sort and Save Final
    normalized_data = {}
    for sub, data in formatted_data.items():
        normalized_data[normalize(sub)] = data
        
    final_output = {}
    
    for pretty_name in drugs_order:
        norm = normalize(pretty_name)
        if norm in normalized_data:
            final_output[pretty_name] = normalized_data[norm]
            
    # Add any unknown substances
    for sub, data in formatted_data.items():
        norm_sub = normalize(sub)
        
        # Check against drugs_order
        found_in_order = False
        if norm_sub in [normalize(x) for x in drugs_order]:
            found_in_order = True
            
        if not found_in_order:
             # Check via lookup
            if norm_sub in drugs_lookup:
                 pname = drugs_lookup[norm_sub]
                 if pname not in final_output:
                     final_output[pname] = data
            else:
                 # Truly new
                 final_output[sub] = data

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_filename = f"extracted_doses_{timestamp}.json"
    output_path = os.path.join(BASE_DIR, "data", output_filename)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(final_output, f, indent=2, ensure_ascii=False)
        
    print(f"Done! Saved to {output_path}")
    print(f"Total time: {time.time() - start_time:.2f}s")
    if blocked:
        print("Warning: Process was incomplete due to IP block.")

if __name__ == "__main__":
    main()
