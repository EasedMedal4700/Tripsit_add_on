import json
import requests
from bs4 import BeautifulSoup
import re
import os

def get_substances_from_drugs_json(drugs_file=None):
    if drugs_file is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        drugs_file = os.path.join(base_dir, 'drugs.json')
    
    with open(drugs_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return list(data.keys())

def scrape_erowid_links(url='https://www.erowid.org/experiences/exp_substance_list.php'):
    print(f"Fetching Erowid substance list from {url}...")
    response = requests.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')

    substances_links = {}

    # Find all <a> with href containing 'exp_'
    links = soup.find_all('a', href=re.compile(r'exp_'))
    found_links = []
    for a in links:
        found_links.append({'href': a['href'], 'text': a.get_text().strip()})
    
    # Save found links for debugging
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
    os.makedirs(output_dir, exist_ok=True)
    
    with open(os.path.join(output_dir, 'found_links.json'), 'w', encoding='utf-8') as f:
        json.dump(found_links, f, indent=2, ensure_ascii=False)
    
    print(f"Found {len(found_links)} raw links, processing...")

    for item in found_links:
        href = item['href']
        match = re.search(r'exp_(.+)', href)
        if match:
            substance_code = match.group(1).split('_')[0].split('.')[0].split('?')[0]
            substance = substance_code.lower()
            category = item['text']
            
            # List of categories we care about
            valid_categories = [
                'General', 'First Times', 'Combinations', 'Retrospective / Summary',
                'Preparation / Recipes', 'Difficult Experiences', 'Bad Trips',
                'Health Problems', 'Train Wrecks & Trip Disasters', 'Addiction & Habituation',
                'Glowing Experiences', 'Mystical Experiences', 'Health Benefits', 'Families',
                'What Was in That?'
            ]

            if category in valid_categories:
                if substance not in substances_links:
                    substances_links[substance] = {}
                substances_links[substance][category] = 'https://www.erowid.org/experiences/' + href

    # Save scraped data for debugging
    with open(os.path.join(output_dir, 'scraped_erowid.json'), 'w', encoding='utf-8') as f:
        json.dump(substances_links, f, indent=2, ensure_ascii=False)

    return substances_links

def match_substances_to_links(substances, erowid_links):
    matched = {}
    for sub in substances:
        # Try exact match first
        if sub in erowid_links:
            matched[sub] = erowid_links[sub]
        else:
            # Try fuzzy match
            sub_norm = sub.lower().replace('-', '').replace(' ', '').replace(',', '')
            for e_sub, links in erowid_links.items():
                e_sub_norm = e_sub.lower().replace('-', '').replace(' ', '').replace(',', '')
                if sub_norm == e_sub_norm:
                    matched[sub] = links
                    break
    return matched

def main():
    substances = get_substances_from_drugs_json()
    print(f"Found {len(substances)} substances in drugs.json")

    erowid_links = scrape_erowid_links()
    print(f"Scraped links for {len(erowid_links)} substances from Erowid")

    matched = match_substances_to_links(substances, erowid_links)

    # Save to json
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
    os.makedirs(output_dir, exist_ok=True)
    
    output_file = os.path.join(output_dir, 'substances_erowid_links.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(matched, f, indent=2, ensure_ascii=False)

    print(f"Matched {len(matched)} substances. Saved to {output_file}")

    # Example for 2C-B
    if '2c-b' in matched:
        print("Example for 2c-b:")
        for cat, url in matched['2c-b'].items():
            print(f"  {cat}: {url}")

if __name__ == "__main__":
    main()
