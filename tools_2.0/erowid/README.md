
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
- **Usage**: python tools/extract_doses_2.0.py

### `extract_doses.py`
Legacy/Reference implementation. Single-threaded.

### `test_regex.py` (Optional)
Used for debugging the regex patterns against sample text.

## Data

- `data/substances_erowid_links.json`: Mapping of substance names to Erowid category URLs.
- `data/extracted_doses_*.json`: Output of the scraping process.
