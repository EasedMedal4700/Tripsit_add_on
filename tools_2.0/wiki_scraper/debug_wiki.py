import requests
import mwparserfromhell
import re

WIKI_API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "TripSit-Debug/1.0"

def fetch_wikitext(title):
    params = {
        "action": "query",
        "format": "json",
        "formatversion": "2",
        "prop": "revisions",
        "titles": title,
        "rvprop": "content",
        "rvslots": "main",
    }
    r = requests.get(WIKI_API, params=params, headers={"User-Agent": USER_AGENT})
    data = r.json()
    return data['query']['pages'][0]['revisions'][0]['slots']['main']['content']

def normalize_value(value):
    value = re.sub(r"<ref[^>]*>.*?</ref>", "", value, flags=re.DOTALL)
    value = re.sub(r"<ref[^/]*/\s*>", "", value)
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value

def debug_infobox(title):
    text = fetch_wikitext(title)
    wikicode = mwparserfromhell.parse(text)
    for tpl in wikicode.filter_templates():
        name = str(tpl.name).strip().lower()
        if "infobox" in name or "drugbox" in name or "chembox" in name:
            print(f"--- Found Template: {name} ---")
            for p in tpl.params:
                print(f"{p.name.strip()} = {p.value.strip()}")

if __name__ == "__main__":
    debug_infobox("1cP-LSD")
