import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add current dir to path to import modules if running as script
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from config_manager import ConfigManager
from data_manager import DataManager
from scraper import ErowidScraper
from html_parser import ReportParser
from utils import get_report_id, normalize, load_json

def build_distribution(doses_list):
    # doses_list is a list of {dose: "10 mg", form: "...", ...}
    
    # 1. Normalize doses to mg (or standardized unit) if possible
    normalized = []
    
    for item in doses_list:
        if not isinstance(item, dict): continue 
        
        raw_dose = item.get('dose', '')
        
        # Try to parse number and unit
        import re
        match = re.match(r'(\d+(?:\.\d+)?)\s*(mg|g|ug|µg|oz|ml|drops?|capsules?|lines?|glass|glasses|hits?|tabs?|blotters?|tablets?|pills?)', raw_dose, re.IGNORECASE)
        
        final_val = raw_dose # Default fallback
        
        if match:
            try:
                val = float(match.group(1))
                unit = match.group(2).lower()
                
                # Unit Normalization
                if unit == 'g': 
                    val *= 1000
                    unit = 'mg'
                elif unit in ['ug', 'µg']: 
                    val /= 1000
                    unit = 'mg'
                elif 'tab' in unit or 'pill' in unit:
                    unit = 'tablets'
                elif 'hit' in unit:
                    unit = 'hits'
                elif 'capsule' in unit:
                    unit = 'capsules'
                elif 'drop' in unit:
                    unit = 'drops'
                elif 'oz' in unit: # Liquid oz or dry weight?
                    # Generally assume fluid oz for unknown liquids, 
                    # but if it's mushrooms... 1 oz = 28g = 28000mg
                    # Ambiguous without context. Keep as oz?
                    pass 
                
                # Format: "10.0 mg"
                # Strip trailing .0 if integer
                if val.is_integer():
                    final_val = f"{int(val)} {unit}"
                else:
                    final_val = f"{val:.2f} {unit}"
            except:
                pass
                
        normalized.append(final_val)
            
    # Count frequency
    dist = defaultdict(int)
    for d in normalized:
        dist[d] += 1
        
    # Sort keys for readability (numeric sort)
    def sort_key(s):
        try:
            return float(s.split()[0])
        except:
            return 999999
            
    sorted_dist = sorted(dist.items(), key=lambda x: sort_key(x[0]))
    
    return {k: v for k, v in sorted_dist}

def main():
    # Setup
    base_dir = os.path.dirname(current_dir) # tools_2.0
    config_path = os.path.join(base_dir, "config.yaml")
    
    print(f"--- TripSit Extractor 2.0 ---")
    print(f"Config: {config_path}")
    
    config = ConfigManager(config_path)
    data_mgr = DataManager(config, base_dir)
    scraper = ErowidScraper(config, data_mgr)
    parser = ReportParser()
    
    # 1. Load Scope
    drugs_list, drugs_lookup = data_mgr.load_drugs_list()
    erowid_links = data_mgr.load_erowid_links()
    
    target_scope = config.get('scraping', 'target_substances')
    print(f"Target Scope: {target_scope}")
    
    # Filter Links
    target_links = {}
    if target_scope == "MATCH_DRUGS_JSON":
        for k, v in erowid_links.items():
            if normalize(k) in drugs_lookup or k in drugs_list:
                target_links[k] = v
    elif isinstance(target_scope, list):
        target_scope_norm = [t.lower() for t in target_scope]
        for k, v in erowid_links.items():
            if k.lower() in target_scope_norm:
                target_links[k] = v
    else: # ALL
        target_links = erowid_links
        
    print(f"Targeting {len(target_links)} substances.")
    
    # 2. Get Categories
    category_urls = set()
    VALID_CATEGORIES = {
    "General", "First Times", "Combinations", "Retrospective / Summary",
    "Preparation / Recipes", "Difficult Experiences", "Bad Trips",
    "Health Problems", "Train Wrecks & Trip Disasters", "Addiction & Habituation",
    "Glowing Experiences", "Mystical Experiences"
    }
    for sub, cats in target_links.items():
        for cat, url in cats.items():
            if cat in VALID_CATEGORIES:
                category_urls.add(url)
                
    # 3. Get Report URLs (Cached or Scraped)
    report_urls = scraper.scrape_all_report_urls(list(category_urls))
    print(f"Total Reports Available: {len(report_urls)}")
    
    # 4. Filter Progress
    progress = data_mgr.load_progress()
    to_scrape = [u for u in report_urls if progress.get(u) != "done"]
    print(f"Remaining to scrape: {len(to_scrape)}")
    
    # 5. Process
    max_workers = config.get('scraping', 'max_workers', 4)
    cnt = 0
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(scraper.fetch_report_html, url): url for url in to_scrape}
        
        for future in as_completed(futures):
            url = futures[future]
            try:
                html = future.result()
                if html:
                    # Parse
                    result = parser.parse(html, url)
                    
                    # Save
                    rid = get_report_id(url)
                    data_mgr.save_temp_report(rid, result)
                    data_mgr.update_progress(url, "done")
                    
                    # Log missing if needed
                    if not result['has_doses']:
                        unknown_behav = config.get('parsing', 'unknown_behavior')
                        if unknown_behav == 'log':
                            data_mgr.save_missing_dose_log({
                                "url": url,
                                "substance_guess": "Unknown", # Could infer from category
                                "reason": "No doses found in parser"
                            })
                else:
                    data_mgr.update_progress(url, "failed_fetch")
            except Exception as e:
                print(f"Error on {url}: {e}")
                data_mgr.update_progress(url, "failed_error")
                
            cnt += 1
            if cnt % 20 == 0:
                print(f"Processed {cnt}/{len(to_scrape)}...")
                
    # 6. Merge & Output
    print("Merging results...")
    all_reports = data_mgr.merge_temp_files()
    
    # Group by substance -> method -> doses
    grouped = defaultdict(lambda: defaultdict(list))
    metadata_grouped = defaultdict(list)

    for r in all_reports:
        doses = r.get('doses', [])
        
        # Attempt to link metadata to a substance (using the first dose's substance)
        # This is imperfect for reports with multiple substances, but sufficient for now
        current_substance = None
        if doses:
            current_substance = doses[0].get('substance')

        if current_substance and r.get('metadata'):
             metadata_grouped[current_substance].append(r['metadata'])

        for d in doses:
            sub = d.get('substance')
            meth = d.get('method')
            if sub and meth and d.get('dose'):
                grouped[sub][meth].append(d)
                
    # Analyze / Format
    final_output = {}
    for sub, methods in grouped.items():
        sub_out = {}
        for meth, dose_objs in methods.items():
            dist = build_distribution(dose_objs)
            if dist:
                sub_out[meth] = dist
        
        # Add metadata (e.g. body weights)
        weights = []
        if sub in metadata_grouped:
            for m in metadata_grouped[sub]:
                if 'body_weight' in m:
                    weights.append(m['body_weight'])
        
        if sub_out or weights:
            entry = {}
            if sub_out: entry["dose_distribution"] = sub_out
            if weights: entry["body_weights"] = weights
            final_output[sub] = entry
            
    data_mgr.save_final_output(final_output)
    print("Done.")

if __name__ == "__main__":
    main()
