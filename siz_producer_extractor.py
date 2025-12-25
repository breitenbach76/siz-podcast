#!/usr/bin/env python3
"""
SiZ Producer Credits Extractor
==============================
Durchsucht alle Podcast-Transkripte und extrahiert die Hauptproduzenten pro Episode.

Verwendung:
    python3 siz_producer_extractor.py
"""

import re
import json
from pathlib import Path
from collections import defaultdict
from typing import Optional, List

# === KONFIGURATION ===
TRANSCRIPT_DIR = Path.home() / "Documents/siz-scripts/transcripts/siz_transkripte"
OUTPUT_DIR = Path.home() / "Documents/siz-scripts"

def extract_producers_from_text(text):
    # type: (str) -> Optional[List[str]]
    """Extrahiert Produzentennamen aus dem Text."""
    
    patterns = [
        r'(?:wurde\s+)?(?:diesmal\s+)?produziert\s+von\s+([A-Za-zäöüÄÖÜß][A-Za-zäöüÄÖÜß,\s]+?)(?:\.|Vielen|Danke|\n|$)',
        r'Hauptproduzent(?:en|Innen)?[:\s]+(?:sind\s+)?([A-Za-zäöüÄÖÜß][A-Za-zäöüÄÖÜß,\s]+?)(?:\.|Vielen|Danke|\n|$)',
        r'Hauptproduzent.*?(?:Das\s+sind|sind)\s+([A-Za-zäöüÄÖÜß][A-Za-zäöüÄÖÜß,\s]+?)(?:\.|Vielen|Danke|\n|$)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            names_str = match.group(1).strip()
            names_str = re.sub(r'\s+und\s+', ', ', names_str, flags=re.IGNORECASE)
            names = [n.strip() for n in names_str.split(',')]
            
            valid_names = []
            for name in names:
                name = name.strip()
                if len(name) >= 2 and name[0].isupper() and not any(c.isdigit() for c in name):
                    if name.lower() not in ['vielen', 'danke', 'dank', 'für', 'die', 'das', 'und']:
                        valid_names.append(name)
            
            if valid_names:
                return valid_names
    return None


def extract_producers_from_file(filepath):
    # type: (Path) -> Optional[List[str]]
    """Liest eine Transkript-Datei und extrahiert die Produzenten."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        search_portion = content[-len(content)//5:]
        return extract_producers_from_text(search_portion)
    except Exception as e:
        print("  Fehler beim Lesen von {}: {}".format(filepath.name, e))
        return None


def get_episode_number(filename):
    # type: (str) -> Optional[int]
    """Extrahiert die Episodennummer aus dem Dateinamen."""
    match = re.search(r'[Ss][Ii][Zz]_?(\d+)', filename)
    if match:
        return int(match.group(1))
    return None


def main():
    print("=" * 60)
    print("SiZ Producer Credits Extractor")
    print("=" * 60)
    print()
    
    if not TRANSCRIPT_DIR.exists():
        print("Verzeichnis nicht gefunden: {}".format(TRANSCRIPT_DIR))
        return
    
    print("Durchsuche: {}".format(TRANSCRIPT_DIR))
    print()
    
    transcript_files = list(TRANSCRIPT_DIR.glob("*[Ss][Ii][Zz]*.txt"))
    
    if not transcript_files:
        print("Keine Transkript-Dateien gefunden!")
        return
    
    print("{} Transkripte gefunden".format(len(transcript_files)))
    print("-" * 60)
    print()
    
    results = {}
    producer_appearances = defaultdict(list)
    not_found = []
    
    for filepath in sorted(transcript_files, key=lambda p: get_episode_number(p.name) or 0):
        ep_num = get_episode_number(filepath.name)
        if ep_num is None:
            continue
        
        producers = extract_producers_from_file(filepath)
        
        if producers:
            results[ep_num] = producers
            for producer in producers:
                producer_appearances[producer].append(ep_num)
            print("  Episode {:02d}: {}".format(ep_num, ', '.join(producers)))
        else:
            not_found.append(ep_num)
            print("  Episode {:02d}: Keine Produzenten gefunden".format(ep_num))
    
    print()
    print("-" * 60)
    print()
    print("ZUSAMMENFASSUNG")
    print("  Episoden mit Produzenten: {}".format(len(results)))
    print("  Episoden ohne Fund: {}".format(len(not_found)))
    
    if not_found:
        print("  Fehlende Episoden: {}".format(', '.join(map(str, sorted(not_found)))))
    
    print()
    
    if producer_appearances:
        print("PRODUZENTEN-STATISTIK")
        print("-" * 40)
        for producer, episodes in sorted(producer_appearances.items(), key=lambda x: -len(x[1])):
            ep_range = "{}-{}".format(min(episodes), max(episodes)) if len(episodes) > 1 else str(episodes[0])
            print("  {}: {} Episoden ({})".format(producer, len(episodes), ep_range))
        print()
    
    # CSV Export
    csv_path = OUTPUT_DIR / "producer_credits.csv"
    with open(csv_path, 'w', encoding='utf-8') as f:
        f.write("episode,producers\n")
        for ep_num in sorted(results.keys()):
            f.write("{},{}\n".format(ep_num, ';'.join(results[ep_num])))
    print("CSV exportiert: {}".format(csv_path))
    
    # JSON Export
    json_path = OUTPUT_DIR / "producer_credits.json"
    export_data = {
        "episodes": {str(k): v for k, v in results.items()},
        "producer_stats": {k: {"count": len(v), "episodes": v} for k, v in producer_appearances.items()},
        "first_episode_with_producers": min(results.keys()) if results else None,
        "not_found": not_found
    }
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)
    print("JSON exportiert: {}".format(json_path))
    
    print()
    print("Fertig!")


if __name__ == "__main__":
    main()
