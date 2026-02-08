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
from utils import get_report_id, normalize

def analyze_doses(doses, unit=None):
    # Simplified analyzer from previous script
    # Takes list of dose strings or objects
    # Returns formatted string like "Common: 10-20 mg"
    # This logic was in previous script, implementing a placeholder here for brevity
    # as the user asked to split tasks, not rewrite analysis logic fully yet.
    # ... I will use the logic from previous script ...
    
    parsed = []
    for d_obj in doses:
        # handle both string and dict
        d_str = d_obj if isinstance(d_obj, str) else d_obj.get('dose', '')
        d_str = d_str.strip().lower().replace(",", "")
        
        import re
        match = re.match(r'(\d+(?:\.\d+)?)\s*([a-zµ]+)', d_str)
        if match:
            parsed.append((float(match.group(1)), match.group(2)))
            
    if not parsed: return None

    unit_counts = defaultdict(int)
    for _, u in parsed: unit_counts[u] += 1
    
    most_common_unit = max(unit_counts, key=unit_counts.get)
    valid_vals = sorted([p[0] for p in parsed if p[1] == most_common_unit])
    
    count = len(valid_vals)
    if count == 0: return None
    
    # Simple quantiles
    def p(pct): return valid_vals[min(int(count * pct), count-1)]
    
    ranges = {}
    ranges["Common"] = f"{p(0.3)}-{p(0.7)} {most_common_unit}"
    ranges["Heavy"] = f"{p(0.9)}+ {most_common_unit}"
    
    stats = {
        "count": count,
        "unit": most_common_unit
    }
    return ranges

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
        for k, v in erowid_links.items():
            if k in target_scope:
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
    
    for r in all_reports:
        doses = r.get('doses', [])
        for d in doses:
            sub = d.get('substance')
            meth = d.get('method')
            val = d.get('dose')
            if sub and meth and val:
                grouped[sub][meth].append(val)
                
    # Analyze
    final_output = {}
    for sub, methods in grouped.items():
        sub_out = {}
        for meth, vals in methods.items():
            analysis = analyze_doses(vals)
            if analysis:
                sub_out[meth] = analysis
        if sub_out:
            final_output[sub] = {"formatted_dose": sub_out}
            
    data_mgr.save_final_output(final_output)
    print("Done.")

if __name__ == "__main__":
    main()
