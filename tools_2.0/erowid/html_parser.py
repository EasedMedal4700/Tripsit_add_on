import re
from bs4 import BeautifulSoup

class ReportParser:
    def __init__(self):
        # Updated regex to include glass, lines, etc.
        self.dose_pattern = re.compile(
            r'(\d+(?:\.\d+)?)\s*' # Amount
            r'(mg|g|ug|µg|ml|oz|drops?|capsules?|lines?|glass|glasses|hits?|tabs?|blotters?|tablets?)\s*' # Unit
            r'(oral|orally|intranasal|insufflated|smoked|rectal|rectally|subcutaneous|sublingually|sublingual|buccal|buccally|intramuscular|im|iv|intravenous|sc|vaped|vaporized|inhaled)\s*' # Method
            r'([A-Za-z0-9,\-\s\(\)/]+?)(?:\s*\(|$)', # Substance/Form
            re.IGNORECASE
        )

    def parse(self, html, url):
        soup = BeautifulSoup(html, "html.parser")
        
        # 1. Parse Metadata
        metadata = self._extract_metadata(soup)
        
        # 2. Parse Doses
        doses = self._extract_doses(soup, metadata)
        
        return {
            "url": url,
            "metadata": metadata,
            "doses": doses,
            "has_doses": len(doses) > 0
        }

    def _extract_metadata(self, soup):
        meta = {}
        # Experience reports often have a table with class "ts-table" or inside a div
        # Look for the table containing "Exp Year", "Gender", etc.
        text = soup.get_text()
        
        # Regex Scrape for specific fields usually found in the header
        # Exp Year: 2000
        # Gender: Male
        # Age at time of experience: 20
        # Published: ....
        
        year_match = re.search(r'Exp Year:\s*(\d{4})', text)
        if year_match: meta['exp_year'] = year_match.group(1)
        
        id_match = re.search(r'ExpID:\s*(\d+)', text)
        if id_match: meta['exp_id'] = id_match.group(1)
        
        gender_match = re.search(r'Gender:\s*([A-Za-z]+)', text)
        if gender_match: meta['gender'] = gender_match.group(1)
        
        age_match = re.search(r'Age at time of experience:\s*(\d+|Not Given)', text, re.IGNORECASE)
        if age_match: meta['age'] = age_match.group(1)

        pub_match = re.search(r'Published:\s*([^\n\r]+)', text)
        if pub_match: meta['published'] = pub_match.group(1).strip()
        
        weight_match = re.search(r'BODY WEIGHT:\s*(\d+.*?)(?:\n|\r|   )', text)
        if weight_match: meta['body_weight'] = weight_match.group(1).strip()
        
        return meta

    def _extract_doses(self, soup, metadata):
        doses = []
        
        # Strategy 1: Look for "DoseChart" table
        # Erowid often puts this in a table.
        # <table border="1" cellpadding="3" cellspacing="0" bordercolor="#ffffff" class="dosechart">
        dose_table = soup.find('table', class_='dosechart')
        if dose_table:
            rows = dose_table.find_all('tr')
            # Skip header ?? Usually headers are "Time", "Amount", "Method", "Substance"
            # But structure varies.
            for row in rows:
                cols = row.find_all('td')
                # A common row: Time | Amount | Method | Substance | Form
                # Or just Amount | Method | Substance
                col_text = [c.get_text(strip=True).replace('\xa0', ' ') for c in cols]
                # Filter out headers
                if not col_text or "Amount" in col_text[0]: continue
                
                # Heuristic: Find a row with dose-like info
                # "1 glass", "oral", "Datura", "(tea)"
                # "3 lines", "insufflated", "Ketamine"
                
                # We join the row and try to parse/clean it or map fields
                # If we have 4+ columns, it's likely [Time, Amount, Method, Substance, Form] or close
                # Erowid format is tricky. Let's try to map generic text to our schema
                
                # Check for recognized units in columns
                doses.extend(self._parse_dose_row(col_text, metadata))

        # Strategy 2: Regex on the whole text (Backup)
        # If table didn't yield results, or in addition to it? 
        # Usually table is authoritative. If table exists, rely on it.
        
        if not doses:
             report_div = soup.find('div', class_='report-text') or soup.find('div', id='report')
             text = report_div.get_text() if report_div else soup.get_text()
             doses = self._extract_doses_from_text(text)
             
        return doses

    def _parse_dose_row(self, cols, metadata):
        methods = {'oral', 'orally', 'insufflated', 'smoked', 'im', 'iv', 'rectal', 'sublingual', 'buccal', 'inhaled', 'vaped', 'vaporized'}
        
        amount_idx = -1
        method_idx = -1
        subst_idx = -1
        
        # 1. Identify Amount and Method
        for i, txt in enumerate(cols):
            l = txt.lower()
            if l in methods:
                 method_idx = i
            elif any(u in l for u in ['mg', 'g', 'ml', 'drops', 'lines', 'glass', 'tab', 'oz', 'capsu']) and re.search(r'\d', l):
                 amount_idx = i
            # Catch "2 tablets" etc.
            elif any(u in l for u in ['tablets', 'pills']) and re.search(r'\d', l):
                 amount_idx = i

        # 2. Identify Substance (heuristic: not amount, not method, not Time, not Form)
        # Prefer column after method if possible
        candidates = []
        for i, txt in enumerate(cols):
            if i == amount_idx or i == method_idx: continue
            if 'repeat' in txt.lower() or 'page' in txt.lower(): continue
            if txt.strip().startswith('T+'): continue # Time column
            if len(txt) < 2: continue
            
            candidates.append(i)

        if candidates:
            # If we have a method, substance is often right after it
            if method_idx != -1 and (method_idx + 1) in candidates:
                subst_idx = method_idx + 1
            else:
                # Otherwise pick the first candidate that doesn't look like a form (parentheses)
                for c in candidates:
                    if '(' not in cols[c]:
                        subst_idx = c
                        break
                # Fallback to first candidate if all have parens
                if subst_idx == -1: subst_idx = candidates[0]
        
        results = []
        if amount_idx != -1 and (method_idx != -1 or subst_idx != -1):
            dose = cols[amount_idx]
            method = cols[method_idx] if method_idx != -1 else "unknown"
            subst = cols[subst_idx] if subst_idx != -1 else "Unknown"
            
            form = ""
            # Form check (next column?)
            # If subst_idx was found, check if next col is form
            if subst_idx != -1 and subst_idx + 1 < len(cols) and subst_idx + 1 != amount_idx and subst_idx + 1 != method_idx:
                form_val = cols[subst_idx+1]
                # Simple check: form usually has parens or is short text
                if '(' in form_val or len(form_val) < 20: 
                    form = form_val.strip("()")
                
            results.append({
                "substance": self._clean_substance(subst),
                "dose": dose,
                "method": method,
                "form": form
            })
            
        return results

    def _extract_doses_from_text(self, text):
        matches = self.dose_pattern.findall(text)
        results = []
        for match in matches:
            amount, unit, method, sub_name = match
            dose = f"{amount} {unit}"
            results.append({
                'substance': self._clean_substance(sub_name),
                'dose': dose,
                'method': method.lower(),
                'form': ''
            })
        return results
        
    def _clean_substance(self, sub_name):
        clean = sub_name.strip()
        # Loop to remove all parenthesized groups
        while '(' in clean and ')' in clean:
             clean = re.sub(r'\([^\)]*\)', '', clean)
        
        clean = re.sub(r'[^\w\s,-]', '', clean)
        clean = re.sub(r'\s+', ' ', clean)
        return clean.strip()
