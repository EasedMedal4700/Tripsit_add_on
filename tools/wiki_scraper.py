import json
import re
import time
import sys
import os
from typing import Any, Dict, Optional, List

import requests
import mwparserfromhell

# ----------------------------
# Configuration
# ----------------------------

WIKI_API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "TripSit-WikipediaInfoboxFetcher/1.0 (contact: fquaaden@gmail.com)"

# ----------------------------
# Helper Functions
# ----------------------------

def fetch_wikitext_batch(titles: List[str]) -> Dict[str, str]:
    """
    Fetches the latest wikitext for a batch of titles (max 50).
    Returns a dict { normalized_title: wikitext }.
    """
    params = {
        "action": "query",
        "format": "json",
        "formatversion": "2",
        "prop": "revisions",
        "titles": "|".join(titles),
        "rvprop": "content",
        "rvslots": "main",
        "redirects": 1,
        "converttitles": 1, 
    }

    try:
        r = requests.get(WIKI_API, params=params, headers={"User-Agent": USER_AGENT}, timeout=30)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"Error fetching batch: {e}")
        return {}

    query = data.get("query", {})
    pages = query.get("pages", [])
    
    results = {}
    for page in pages:
        if "missing" in page:
            continue
        
        title = page.get("title")
        revisions = page.get("revisions", [])
        if revisions:
            content = revisions[0].get("slots", {}).get("main", {}).get("content", "")
            if content:
                results[title] = content
                
    return results

def normalize_value(value: str) -> str:
    """
    Cleans typical wikitext noise
    """
    # Remove refs
    value = re.sub(r"<ref[^>]*>.*?</ref>", "", value, flags=re.DOTALL)
    value = re.sub(r"<ref[^/]*/\s*>", "", value)
    # Remove HTML tags
    value = re.sub(r"<[^>]+>", "", value)
    # Fix [[Link|Text]] -> Text
    value = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", value)
    # Collapse whitespace
    value = re.sub(r"\s+", " ", value).strip()
    return value

def extract_infobox(wikitext: str) -> Dict[str, str]:
    try:
        wikicode = mwparserfromhell.parse(wikitext)
        for tpl in wikicode.filter_templates(recursive=True):
            name = str(tpl.name).strip().lower()
            # Catch varying infobox names
            if name.startswith("infobox") or "drugbox" in name or "chembox" in name:
                params = {}
                for p in tpl.params:
                    key = str(p.name).strip()
                    val = normalize_value(str(p.value).strip())
                    if key and val:
                        params[key] = val
                return params
    except Exception as e:
        print(f"Error parsing wikitext: {e}")
    return {}

def pick(params: Dict[str, str], *keys: str) -> Optional[str]:
    for k in keys:
        for p_key in params:
            if p_key.lower() == k.lower():
                 return params[p_key]
    return None

def construct_formula(params: Dict[str, str]) -> Optional[str]:
    """
    Constructs chemical formula from individual element counts (C, H, N, O, etc.)
    Standard Hill system: C first, then H, then alphabetical.
    """
    elements = {}
    # Common elements in drugs
    known_elements = [
        "C", "H", "Ag", "Al", "As", "Au", "B", "Ba", "Be", "Bi", "Br", "Ca", "Cd", "Cl", "Co", "Cr", 
        "Cs", "Cu", "F", "Fe", "Ga", "Gd", "Ge", "Hg", "I", "K", "Li", "Mg", "Mn", "Mo", "N", "Na", 
        "Nb", "Ni", "O", "Os", "P", "Pb", "Pd", "Pt", "Rb", "Re", "Ru", "S", "Sb", "Sc", "Se", "Si", 
        "Sn", "Sr", "Tb", "Tc", "Te", "Ti", "Tl", "U", "V", "W", "Y", "Zn", "Zr"
    ]
    
    for el in known_elements:
        # Check for exact key match "C", "H" etc.
        val = params.get(el)
        if val and val.isdigit():
             elements[el] = int(val)
    
    if not elements:
        return None
        
    formula_parts = []
    
    # Hill system: C first
    if "C" in elements:
        formula_parts.append(f"C{elements['C']}")
        del elements["C"]
        
    # H second
    if "H" in elements:
        formula_parts.append(f"H{elements['H']}")
        del elements["H"]
        
    # Rest alphabetical
    for el in sorted(elements.keys()):
        count = elements[el]
        if count == 1:
            formula_parts.append(el)
        else:
            formula_parts.append(f"{el}{count}")
            
    return "".join(formula_parts)

def build_tripsit_payload(title: str, params: Dict[str, str]) -> Dict[str, Any]:
    # Expanded list based on typical chemistry/drug infoboxes
    formula = pick(params, "formula", "chemical_formula", "molecular_formula", "Formula")
    if not formula:
        formula = construct_formula(params)
    
    # Collect all legal_X keys
    legal_data = {}
    for k, v in params.items():
        if k.lower().startswith("legal_") or k.lower().startswith("status_"):
             legal_data[k] = v

    return {
        "source": {
            "provider": "wikipedia",
            "page_title": title,
            "api": "mediawiki_action_api",
        },
        # Identifiers
        "iupac_name": pick(params, "iupac_name", "IUPAC_name", "systematic_name", "SystematicName"),
        "cas_number": pick(params, "cas_number", "CAS_number", "CASNo", "CAS"),
        "pubchem": pick(params, "pubchem", "PubChem", "PubChem CID"),
        "chemspider": pick(params, "chemspider", "ChemSpiderID"),
        "unii": pick(params, "unii", "UNII"),
        "drugbank": pick(params, "drugbank", "DrugBank"),
        "kegg": pick(params, "kegg", "KEGG"),
        "chebi": pick(params, "chebi", "ChEBI"),
        "chembl": pick(params, "chembl", "ChEMBL"),
        "pdb_ligand": pick(params, "pdb_ligand", "PDB ligand"),

        # Properties
        "smiles": pick(params, "smiles", "SMILES", "StdInChI", "prosthetic_groups"),
        "inchi": pick(params, "inchi", "InChI", "stdInChI"),
        "inchikey": pick(params, "inchikey", "InChIKey", "stdInChIKey"),
        "formula": formula,
        "molar_mass": pick(params, "molar_mass", "molecular_weight", "MolarMass"),
        "melting_point": pick(params, "melting_point", "melting_high", "MeltingPt"),
        "boiling_point": pick(params, "boiling_point", "boiling_high", "BoilingPt"),
        "solubility": pick(params, "solubility", "Solubility"),

        # Clinical
        "synonyms": pick(params, "synonyms", "other_names", "Tradename", "Trade names", "Synonyms"),
        "pronunciation": pick(params, "pronunciation", "Pronunciation"),
        "drug_class": pick(params, "drug_class", "class", "Drug class"),
        "routes_of_administration": pick(params, "routes_of_administration", "routes", "Routes of administration"),
        "atc_code": pick(params, "atc_code", "ATC code", "ATC"),
        "pregnancy_category": pick(params, "pregnancy_category", "pregnancy_AU", "pregnancy_US", "Pregnancy category"),
        "dependence_liability": pick(params, "dependence_liability", "dependency_liability", "Dependence liability"),
        "addiction_liability": pick(params, "addiction_liability", "Addiction liability"),

        # Pharmacokinetics
        "bioavailability": pick(params, "bioavailability", "Bioavailability"),
        "protein_binding": pick(params, "protein_binding", "Protein binding", "protein_bound"),
        "metabolism": pick(params, "metabolism", "Metabolism"),
        "metabolites": pick(params, "metabolites", "Metabolites"),
        "onset": pick(params, "onset", "Onset of action", "onset"),
        "duration": pick(params, "duration", "duration_of_action", "Duration of action"),
        "half_life": pick(params, "half_life", "elimination_half-life", "Elimination half-life", "halflife"),
        "excretion": pick(params, "excretion", "Excretion"),
        
        # Legal
        "legal_status": legal_data if legal_data else pick(params, "legal_status", "Legal status", "legal"),
    }

def main():
    # 1. Load drugs.json
    script_dir = os.path.dirname(os.path.abspath(__file__))
    drugs_path = os.path.join(script_dir, '../drugs.json')
    
    print(f"Loading {drugs_path}...")
    try:
        with open(drugs_path, 'r', encoding='utf-8') as f:
            drugs_db = json.load(f)
    except FileNotFoundError:
        print("drugs.json not found.")
        sys.exit(1)

    print(f"Loaded {len(drugs_db)} entries from drugs.json")

    # 2. Prepare test case
    test_target = "LSD" # Changed to LSD to verify rich data
    
    print(f"\n--- Running Test for: {test_target} ---")
    
    batch_result = fetch_wikitext_batch([test_target])
    
    found_any_test = False
    for title, wikitext in batch_result.items():
        print(f"Fetched wikitext for {title} (Length: {len(wikitext)})")
        infobox = extract_infobox(wikitext)
        if infobox:
            payload = build_tripsit_payload(title, infobox)
            print("Extracted Data Sample:")
            print(json.dumps(payload, indent=2))
            if payload.get("smiles") or payload.get("formula"):
                print("SUCCESS: Found SMILES/Formula")
            found_any_test = True
        else:
            print("No infobox data found for test target.")
            print("Sample text start:", wikitext[:200])
    
    if not found_any_test:
        print("Test failed or returned no useful data. Exiting test.")
    
    print("\n--- Starting Full Scrape ---")
    
    # 3. Full run
    target_names = []
    
    # Collect unique names to query
    for key, data in drugs_db.items():
        # Prefer pretty_name if it exists and looks like a valid title
        pname = data.get("pretty_name")
        if pname:
            target_names.append(pname)
        else:
            target_names.append(key)
    
    # Deduplicate
    target_names = sorted(list(set(target_names)))
    
    # Filter out obvious junk if necessary
    target_names = [n for n in target_names if len(n) > 2]

    print(f"Total Unique Targets to scrape: {len(target_names)}")
    
    results_list = []
    batch_size = 50
    
    report_file = os.path.join(script_dir, 'wiki_scraped_data.json')
    
    start_time = time.time()
    
    for i in range(0, len(target_names), batch_size):
        chunk = target_names[i : i + batch_size]
        print(f"Processing batch {i} - {i+len(chunk)} / {len(target_names)}")
        
        batch_data = fetch_wikitext_batch(chunk)
        
        for title, wikitext in batch_data.items():
            infobox = extract_infobox(wikitext)
            if infobox:
                payload = build_tripsit_payload(title, infobox)
                # Keep if it has some data
                # Check key fields
                if any(payload.get(k) for k in ["smiles", "formula", "cas_number", "iupac_name"]):
                    results_list.append(payload)
        
        # Rate limit
        time.sleep(1.0)
    
    end_time = time.time()
    duration = end_time - start_time
    
    print(f"\nScraping complete in {duration:.2f} seconds.")
    print(f"Found data for {len(results_list)} substances.")
    
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(results_list, f, indent=2)
        
    print(f"Report saved to {report_file}")

if __name__ == "__main__":
    main()
