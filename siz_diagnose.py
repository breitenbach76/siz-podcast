#!/usr/bin/env python3
"""
SiZ Producer Diagnose
=====================
Zeigt die letzten 30 Zeilen der Episoden ohne gefundene Produzenten.
"""

import re
from pathlib import Path

TRANSCRIPT_DIR = Path.home() / "Documents/siz-scripts/transcripts/siz_transkripte"

# Episoden ohne Fund (ab Episode 9)
MISSING = [9, 11, 12, 15, 16, 17, 18, 19, 20, 21, 23, 24, 25, 28, 29, 30, 31, 32, 33, 34, 35, 36, 38, 39, 41, 42, 44, 46, 49, 51, 52, 53, 59, 60, 63, 65, 66, 68, 69]

def main():
    # Nur erste 5 fehlende Episoden anzeigen
    check_episodes = MISSING[:5]
    
    print("=" * 70)
    print("DIAGNOSE: Letzte 30 Zeilen der fehlenden Episoden")
    print("=" * 70)
    
    for ep_num in check_episodes:
        # Datei finden
        pattern = "*[Ss][Ii][Zz]*{}*".format(ep_num)
        files = list(TRANSCRIPT_DIR.glob("*[Ss][Ii][Zz]_{}.*".format(ep_num)))
        files += list(TRANSCRIPT_DIR.glob("*[Ss][Ii][Zz]_{:02d}.*".format(ep_num)))
        
        if not files:
            print("\nEpisode {}: DATEI NICHT GEFUNDEN".format(ep_num))
            continue
        
        filepath = files[0]
        print("\n" + "=" * 70)
        print("EPISODE {}: {}".format(ep_num, filepath.name))
        print("=" * 70)
        
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Letzte 30 Zeilen
        last_lines = lines[-30:]
        for i, line in enumerate(last_lines):
            line_num = len(lines) - 30 + i + 1
            print("{:4d}: {}".format(line_num, line.rstrip()))
    
    print("\n" + "=" * 70)
    print("Zeige Episoden: {}".format(check_episodes))
    print("Weitere fehlende: {}".format(MISSING[5:]))
    print("=" * 70)

if __name__ == "__main__":
    main()
