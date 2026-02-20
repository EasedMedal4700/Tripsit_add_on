
# Tools 2.0

This directory contains the Python-based toolbelt for scraping and processing data for the tripsit-add-on project.

## Scripts

### `extract_doses_2.0.py`
The main scraping tool.
- **Purpose**: Crawls Erowid experience reports to find dosage information for substances.
- **Process**:
    1. Reads known drugs from `drugs.json` and Erowid links from `data/substances_erowid_links.json`.
    2. Fetches category pages (General, First Times, etc.) to report URLs.
    3. Multithreaded scraping of individual report pages.
    4. Extracts dose, unit, method (ROA), and substance name using Regex.
    5. Analyzes the distribution of doses to determine Common, Strong, etc. ranges.
- **Output**: `data/extracted_doses_TIMESTAMP.json`.
- **Usage**: 
  ```bash
  # Activate virtual environment (if not already active)
  .venv\Scripts\Activate.ps1  # On Windows PowerShell
  # or
  source .venv/bin/activate  # On Linux/Mac

  # Run the script
  python tools_2.0/tools/extract_doses_2.0.py
  ```

### `extract_doses.py`
Legacy/Reference implementation. Single-threaded.
- **Usage**: 
  ```bash
  python tools_2.0/tools/extract_doses.py
  ```

### `test_regex.py` (Optional)
Used for debugging the regex patterns against sample text.
- **Usage**: 
  ```bash
  python tools_2.0/tools/test_regex.py
  ```

### `wiki_scraper.py` (Located in `../tools/`)
Wikipedia Infobox Scraper for Chemical and Clinical Data.
- **Purpose**: Extracts comprehensive drug information from Wikipedia infoboxes, including chemical properties, clinical data, pharmacokinetics, and legal status.
- **Process**:
    1. Loads substance names from `drugs.json`.
    2. Batches requests to Wikipedia API (50 titles per request) to fetch wikitext.
    3. Parses infobox templates using mwparserfromhell.
    4. Extracts fields like IUPAC name, SMILES, formula, CAS number, PubChem ID, drug class, routes of administration, bioavailability, metabolism, onset/duration, half-life, excretion, and legal status by country.
    5. Constructs chemical formulas from element counts if not directly available.
- **Output**: `tools/wiki_scraped_data.json` - JSON array of enriched substance data.
- **Usage**: 
  ```bash
  # Activate virtual environment
  .venv\Scripts\Activate.ps1  # On Windows PowerShell

  # Run the script
  python tools/wiki_scraper.py
  ```
- **Rate Limiting**: 1 second delay between batches to avoid IP blocking.
- **Dependencies**: requests, mwparserfromhell.

## Data

- `data/substances_erowid_links.json`: Mapping of substance names to Erowid category URLs.
- `data/extracted_doses_*.json`: Output of the scraping process.
- `../tools/wiki_scraped_data.json`: Wikipedia-sourced chemical and clinical data for substances.

