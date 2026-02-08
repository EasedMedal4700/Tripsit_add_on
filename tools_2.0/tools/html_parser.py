import re
from bs4 import BeautifulSoup

class ReportParser:
    def __init__(self):
        # Updated regex to include glass, lines, etc.
        self.dose_pattern = re.compile(
            r'(\d+(?:\.\d+)?)\s*' # Amount
            r'(mg|g|ug|µg|ml|oz|drops?|capsules?|lines?|glass|glasses|hits?|tabs?|blotters?)\s*' # Unit
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
        text = soup.get_text()
        
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
        
        return meta

    def _extract_doses(self, soup, metadata):
        doses = []
        
        dose_table = soup.find('table', class_='dosechart')
        if dose_table:
            rows = dose_table.find_all('tr')
            for row in rows:
                cols = row.find_all('td')
                col_text = [c.get_text(strip=True) for c in cols]
                if not col_text or "Amount" in col_text[0]: continue
                
                doses.extend(self._parse_dose_row(col_text))

        if not doses:
             report_div = soup.find('div', class_='report-text') or soup.find('div', id='report')
             text = report_div.get_text() if report_div else soup.get_text()
             doses = self._extract_doses_from_text(text)
             
        return doses

    def _parse_dose_row(self, cols):
        methods = {'oral', 'orally', 'insufflated', 'smoked', 'im', 'iv', 'rectal', 'sublingual', 'buccal', 'inhaled'}
        
        amount_idx = -1
        method_idx = -1
        subst_idx = -1
        
        for i, txt in enumerate(cols):
            l = txt.lower()
            if l in methods:
                 method_idx = i
            elif any(u in l for u in ['mg', 'g', 'ml', 'drops', 'lines', 'glass', 'tab']) and re.search(r'\d', l):
                 amount_idx = i
            elif len(l) > 2 and i > 0 and amount_idx != i and method_idx != i:
                 if 'repeat' not in l and 'page' not in l:
                     subst_idx = i
        
        results = []
        if amount_idx != -1 and method_idx != -1 and subst_idx != -1:
            dose = cols[amount_idx]
            method = cols[method_idx]
            subst = cols[subst_idx]
            
            if subst_idx + 1 < len(cols):
                form = cols[subst_idx+1]
                subst += f" ({form})"
                
            results.append({
                "substance": self._clean_substance(subst),
                "dose": dose,
                "method": method
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
                'method': method.lower()
            })
        return results
        
    def _clean_substance(self, sub_name):
        clean = re.sub(r'\s+', ' ', sub_name.strip())
        clean = re.sub(r'[^\w\s,\(\)-]', '', clean)
        return clean
