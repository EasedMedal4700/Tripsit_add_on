import requests
import time
import random
from bs4 import BeautifulSoup
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

class ErowidScraper:
    def __init__(self, config_manager, data_manager):
        self.config = config_manager
        self.data_mngr = data_manager
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self.config.get('scraping', 'user_agent')
        })
        
        self.sleep_range = (
            self.config.get('scraping', 'sleep_min', 1.0),
            self.config.get('scraping', 'sleep_max', 2.0)
        )
        self.blocked = False

    def get_report_urls(self, category_url):
        if self.blocked: return []
        
        try:
            time.sleep(random.uniform(*self.sleep_range))
            resp = self.session.get(category_url, timeout=20)
            
            if resp.status_code == 403 or "Blocked" in resp.text[:500]:
                print(f"BLOCKED at {category_url}")
                self.blocked = True
                return []
                
            soup = BeautifulSoup(resp.text, 'html.parser')
            urls = []
            for a in soup.find_all('a', href=re.compile(r'exp\.php\?ID=\d+')):
                href = a['href']
                
                # FIX: Detailed URL construction to avoid double slashes
                if href.startswith('http'):
                    full_url = href
                elif href.startswith('/'):
                    full_url = f"https://www.erowid.org{href}"
                else:
                    full_url = f"https://www.erowid.org/experiences/{href}"
                
                if full_url not in urls:
                    urls.append(full_url)
            return urls
        except Exception as e:
            # print(f"Error fetching category: {e}")
            return []

    def fetch_report_html(self, report_url):
        if self.blocked: return None
        
        try:
            time.sleep(random.uniform(*self.sleep_range))
            resp = self.session.get(report_url, timeout=20)
            
            if resp.status_code == 403:
                print(f"BLOCKED at {report_url}")
                self.blocked = True
                return None
                
            return resp.text
        except Exception:
            return None

    def scrape_all_report_urls(self, category_urls):
        cache_file = self.config.get('scraping', 'cache_file')
        use_cache = self.config.get('scraping', 'use_url_cache')
        
        # Check cache
        if use_cache:
            cached = self.data_mngr.load_json_absolute(cache_file)
            if cached:
                print(f"Loaded {len(cached)} report URLs from cache.")
                return cached
        
        # Crawl
        print(f"Crawling {len(category_urls)} categories (Cache disabled or empty)...")
        all_urls = set()
        max_workers = self.config.get('scraping', 'max_workers', 4)
        max_per_cat = self.config.get('scraping', 'max_reports_per_category', 500)
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.get_report_urls, url): url for url in category_urls}
            
            cnt = 0
            for future in as_completed(futures):
                res = future.result()
                if self.blocked:
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
                
                if res:
                    for u in res[:max_per_cat]:
                        all_urls.add(u)
                
                cnt += 1
                if cnt % 50 == 0:
                   print(f"Scanned {cnt}/{len(category_urls)} categories...")
                   self.data_mngr.save_json_absolute(cache_file, list(all_urls))

        url_list = list(all_urls)
        # Save cache
        if not self.blocked:
             self.data_mngr.save_json_absolute(cache_file, url_list)
             print(f"Saved {len(url_list)} URLs to cache.")
             
        return url_list
