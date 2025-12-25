#!/usr/bin/env python3
"""
SiZ Content Generator
Generiert WordPress-Content aus Transkripten und updated Posts via API
"""

import os
import base64
import json
import re
from pathlib import Path
import markdown

try:
    import requests
except ImportError:
    print("pip3 install requests")
    exit(1)

try:
    import anthropic
except ImportError:
    print("pip3 install anthropic")
    exit(1)

# =============================================================================
# KONFIGURATION
# =============================================================================

SITE_URL = "https://schweigenistzustimmung.de"
TRANSCRIPTS_DIR = Path(__file__).parent / "transcripts" / "siz_transkripte"
OUTPUT_DIR = Path(__file__).parent / "generated"
MODEL = "claude-sonnet-4-20250514"

# Episode-Daten (Podlove IDs)
EPISODES = {
    69: {"podlove_id": 78, "title": "Schöne Bescherung!"},
    68: {"podlove_id": 77, "title": "Fast Fashion in die Hölle"},
    67: {"podlove_id": 76, "title": "Sudan – Die Welt schaut weg"},
    66: {"podlove_id": 75, "title": "COP30"},
    65: {"podlove_id": 74, "title": "Anno 2025"},
    64: {"podlove_id": 73, "title": "Mamdani: Hope reloaded?"},
    63: {"podlove_id": 72, "title": "Venezuela – neue Kriege für Öl?"},
    62: {"podlove_id": 71, "title": "Der vereinigte Potentatenstaat von Amerika"},
    61: {"podlove_id": 70, "title": "Feed the rich, eat the poor"},
    60: {"podlove_id": 68, "title": "Israel-Gaza-Krieg Teil 2"},
    59: {"podlove_id": 66, "title": "Israel-Gaza-Krieg Teil 1"},
    58: {"podlove_id": 65, "title": "Wo sind unsere dritten Orte!?"},
    57: {"podlove_id": 64, "title": "Machtergreifung in 3, 2, 1 …"},
    56: {"podlove_id": 63, "title": "Charlie Kirk Komplex"},
    55: {"podlove_id": 62, "title": "Urlaub für Alle!"},
    54: {"podlove_id": 61, "title": "Epstein – die Klasse der Gesetzlosen"},
    53: {"podlove_id": 60, "title": "Kapitalismus Ketzerei"},
    52: {"podlove_id": 59, "title": "Der Plan für die Machtergreifung?"},
    51: {"podlove_id": 58, "title": "Skandale aus dem Zirkuszelt – Teil 2"},
    50: {"podlove_id": 57, "title": "Skandale aus dem Zirkuszelt – Teil 1"},
    49: {"podlove_id": 55, "title": "Aufsteigender Löwe – strahlende Zukunft?"},
    48: {"podlove_id": 54, "title": "Der ICE-kalte Bürgerkrieg"},
    47: {"podlove_id": 53, "title": "Ja, wir lesen Theorie"},
    46: {"podlove_id": 52, "title": "Entropisches Fiebermessen"},
    45: {"podlove_id": 51, "title": "(Fragile) Erfolge der Arbeiterbewegung"},
    44: {"podlove_id": 50, "title": "Stop singing, start swinging"},
    43: {"podlove_id": 49, "title": "Vibes & Egos"},
    42: {"podlove_id": 48, "title": "Gesichert rechtsextrem!"},
    41: {"podlove_id": 47, "title": "Schützt unsere Milliardäre!"},
    40: {"podlove_id": 46, "title": "Neoliberale Fossilien"},
    39: {"podlove_id": 45, "title": "Im Rückmerzgang"},
    38: {"podlove_id": 44, "title": "Trumpcession"},
    37: {"podlove_id": 43, "title": "Counter Culture"},
    36: {"podlove_id": 42, "title": "Wo, bitte, geht's zur Suppenküche?"},
    35: {"podlove_id": 41, "title": "Pflugscharen zu Schwertern"},
    34: {"podlove_id": 40, "title": "Neues Zeitalter des Krieges"},
    33: {"podlove_id": 39, "title": "Mit Milliardären an die Macht"},
    32: {"podlove_id": 38, "title": "Die Qual nach der Wahl?!"},
    31: {"podlove_id": 37, "title": "2 Gäste und 3 Tops & Flops"},
    30: {"podlove_id": 36, "title": "Wahlkampfthemen, die uns fehlen – Teil 2"},
    29: {"podlove_id": 35, "title": "Wahlkampfthemen, die uns fehlen – Teil 1"},
    28: {"podlove_id": 34, "title": "Alerta, Alerta, Alman-MAGA!"},
    27: {"podlove_id": 33, "title": "Fire walk with me!"},
    26: {"podlove_id": 32, "title": "Können wir 2024 nochmal sehen?"},
    25: {"podlove_id": 31, "title": "Geschenke! Geschenke!"},
    24: {"podlove_id": 30, "title": "BRICS: Der neue Hegemon?!"},
    23: {"podlove_id": 29, "title": "Syrien: Herzen, durchbohrt von einem Pfeil"},
    22: {"podlove_id": 28, "title": "Der große Raubzug"},
    21: {"podlove_id": 27, "title": "Die Ide(e)n des Merz"},
    20: {"podlove_id": 26, "title": "Die MAGA Zeitenwende"},
    19: {"podlove_id": 25, "title": "Zeugen des Kollapses"},
    18: {"podlove_id": 24, "title": "Diese Jugend ohne Zukunft?!"},
    17: {"podlove_id": 23, "title": "Woke Gespenster"},
    16: {"podlove_id": 22, "title": "Der Sturm vor dem Dark MAGA Sturm"},
    15: {"podlove_id": 21, "title": "Realitätsfabrik Mediensystem"},
    14: {"podlove_id": 20, "title": "Ein Platz an der Hölle"},
    13: {"podlove_id": 19, "title": "Populismus essen Denken auf"},
    12: {"podlove_id": 17, "title": "Fossiles Kapital"},
    11: {"podlove_id": 13, "title": "Freiheit von Verantwortung?"},
    10: {"podlove_id": 12, "title": "Hilfe zur Selbsthilfe: Die Zivilgesellschaft"},
    9: {"podlove_id": 11, "title": "Day after Solingen"},
    8: {"podlove_id": 10, "title": "Rechte und menschenfeindliche Codes"},
    7: {"podlove_id": 9, "title": "Unbeschwert Leben im Glutofen"},
    6: {"podlove_id": 2, "title": "Lügenmaschinen, Sozialer Kahlschlag und Straßenmobs"},
    5: {"podlove_id": 3, "title": "Rechtsrutschen wird olympische Disziplin"},
    4: {"podlove_id": 4, "title": "Politik, Pop und Protestsanktionen"},
    3: {"podlove_id": 5, "title": "Trump Fever in Trump Land"},
    2: {"podlove_id": 6, "title": "EM2024: Anstoß und Anstößigkeit"},
    1: {"podlove_id": 7, "title": "Der Ewige Ausländer"},
}

CTA_BLOCK = """
<h2>Unterstützen & Folgen</h2>

<p>💜 <strong>Steady:</strong> <a href="https://steadyhq.com/de/schweigen-ist-zustimmung/about">steadyhq.com/schweigen-ist-zustimmung</a></p>

<p>💸 <strong>Spenden:</strong><br>
PayPal: <a href="https://www.paypal.com/donate/?hosted_button_id=AGMTQPZMH544U">Jetzt spenden</a><br>
IBAN: DE19 2004 1133 0136 5949 00 (Jens Brodersen/SiZ)</p>

<p>⭐ <strong>Bewerten:</strong> <a href="https://podcasts.apple.com/us/podcast/schweigen-ist-zustimmung/id1756064793">Apple Podcasts</a> | <a href="https://open.spotify.com/show/6J08RhjgdpkWmqwh0VJkMP">Spotify</a></p>

<p>💬 <strong>Community:</strong> <a href="https://discord.gg/Z8ynuDBuep">Discord</a></p>

<p>📱 <strong>Social:</strong> <a href="https://bsky.app/profile/schweigenistz.bsky.social">Bluesky</a> | <a href="https://www.instagram.com/siz_podcast">Instagram</a> | <a href="https://www.tiktok.com/@schweigen.ist.zus0">TikTok</a></p>
"""

SYSTEM_PROMPT = """Du bist der Content-Assistent für "Schweigen ist Zustimmung" (SiZ).

PODCAST-PROFIL:
- Politischer Analyse-Podcast, 90-120 Min/Episode
- Hosts: Patrick Breitenbach & Jens Brodersen
- Ton: Kraftvoll-kritisch, progressiv, niemals zynisch

STIL für Episodentext (Drei-Akt-Struktur):
1. Schock-Einstieg (dramatischer Fakt, Zahlen)
2. Vertiefung (Kontext, rhetorische Fragen)
3. Patrick & Jens (was die Hosts machen)

Stilmittel: Doppelpunkt als Pointe, kraftvolle Metaphern, Fragmentsätze, dritte Person für Hosts.
WICHTIG: Nenne die Hosts im Episodentext nur mit Vornamen: "Patrick und Jens", niemals mit vollem Namen."""

USER_PROMPT = """Analysiere dieses Transkript und generiere Content für WordPress.

**EPISODE:** {episode_nr} – {title}

**TRANSKRIPT:**
{transcript}

---

Generiere zwei Sektionen, OHNE Überschriften wie "Episodentext" oder "Shownotes":

1. Zuerst: Ein SEO-optimierter Teaser (150-250 Wörter) im Drei-Akt-Stil. Beginne direkt mit dem Text, keine Überschrift.

2. Dann nach einer Leerzeile mit "---" getrennt: Die Shownotes als HTML:

<h3>Themen</h3>
<ul><li>Thema 1</li>...</ul>

<h3>Erwähnte Personen & Organisationen</h3>
<ul><li><strong><a href="https://de.wikipedia.org/wiki/Name">Name</a>:</strong> kurze Einordnung</li>...</ul>

<h3>Begriffe</h3>
<ul><li><strong>Begriff:</strong> Erklärung</li>...</ul>

<h3>Weiterführende Quellen</h3>
<ul><li><a href="URL">Titel der Quelle</a></li>...</ul>

Verwende echte Wikipedia-URLs für bekannte Personen und Organisationen. Bei weniger bekannten Personen ohne Wikipedia-Eintrag, verlinke auf offizielle Websites falls vorhanden, ansonsten kein Link.
"""

# =============================================================================
# FUNKTIONEN
# =============================================================================

def load_env():
    env_file = Path(__file__).parent / ".env"
    creds = {}
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    k, v = line.strip().split("=", 1)
                    creds[k] = v
    return creds

def get_auth_header(user, pw):
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}

def read_transcript(episode_nr):
    txt_file = TRANSCRIPTS_DIR / f"SiZ_{episode_nr:02d}.txt"
    if not txt_file.exists():
        txt_file = TRANSCRIPTS_DIR / f"SiZ_{episode_nr}.txt"
    if not txt_file.exists():
        return None
    with open(txt_file, "r", encoding="utf-8") as f:
        content = f.read()
    # Kürzen falls zu lang (max 120k Zeichen)
    if len(content) > 120000:
        content = content[:120000] + "\n[...]"
    return content

def generate_content(client, episode_nr, title, transcript):
    prompt = USER_PROMPT.format(
        episode_nr=episode_nr,
        title=title,
        transcript=transcript
    )
    
    import time
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            message = client.messages.create(
                model=MODEL,
                max_tokens=4000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}]
            )
            return message.content[0].text, message.usage
        except anthropic.RateLimitError:
            if attempt < max_retries - 1:
                wait = 60 * (attempt + 1)
                print(f"   ⏳ Rate Limit, warte {wait}s...")
                time.sleep(wait)
            else:
                raise

def get_wp_post_id(headers, podlove_id):
    """Holt die WordPress Post-ID für eine Podlove-Episode"""
    r = requests.get(
        f"{SITE_URL}/wp-json/podlove/v2/episodes/{podlove_id}",
        headers=headers, timeout=10
    )
    if r.status_code == 200:
        return r.json().get("post_id")
    return None

def update_wordpress_post(headers, post_id, content):
    """Updated den WordPress Post"""
    r = requests.post(
f"{SITE_URL}/wp-json/wp/v2/episodes/{post_id}",
        headers=headers,
        json={"content": content},
        timeout=30
    )
    return r.status_code == 200

def show_menu():
    print("\n" + "=" * 50)
    print("SiZ Content Generator")
    print("=" * 50)
    print("\n1. Einzelne Episode verarbeiten")
    print("2. Mehrere Episoden (Bulk)")
    print("3. Nur generieren (ohne WordPress-Update)")
    print("4. Exit")
    return input("\nWahl (1-4): ").strip()

def process_episode(client, headers, episode_nr, update_wp=True, save_local=True):
    if episode_nr not in EPISODES:
        print(f"❌ Episode {episode_nr} nicht gefunden")
        return False
    
    ep = EPISODES[episode_nr]
    print(f"\n{'='*50}")
    print(f"Episode {episode_nr}: {ep['title']}")
    print("=" * 50)
    
    # Transkript laden
    print("📄 Lade Transkript...")
    transcript = read_transcript(episode_nr)
    if not transcript:
        print("❌ Transkript nicht gefunden")
        return False
    print(f"   {len(transcript):,} Zeichen")
    
    # Content generieren
    print("🤖 Generiere Content...")
    content, usage = generate_content(client, episode_nr, ep['title'], transcript)
    print(f"   Tokens: {usage.input_tokens:,} in / {usage.output_tokens:,} out")
    
    # Vorschau-Loop
    while True:
        print("\n" + "="*50)
        print("VORSCHAU:")
        print("="*50)
        print(content)
        print("="*50)
        
        choice = input("\n(j) Übernehmen | (k) Korrektur | (n) Abbrechen: ").strip().lower()
        
        if choice == "j":
            break
        elif choice == "n":
            print("Abgebrochen.")
            return False
        elif choice == "k":
            korrektur = input("Korrekturwunsch: ").strip()
            if korrektur:
                print("🤖 Überarbeite...")
                correction_prompt = f"""Hier ist der bisherige Content:

{content}

---

Korrekturwunsch: {korrektur}

Generiere den gesamten Content neu mit dieser Korrektur. Behalte das Format bei."""
                
                message = client.messages.create(
                    model=MODEL,
                    max_tokens=4000,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": correction_prompt}]
                )
                content = message.content[0].text
                print(f"   Tokens: {message.usage.input_tokens:,} in / {message.usage.output_tokens:,} out")
    
    # Lokal speichern
    if save_local:
        OUTPUT_DIR.mkdir(exist_ok=True)
        out_file = OUTPUT_DIR / f"SiZ_{episode_nr:02d}.md"
        full_content = f"# Episode {episode_nr}: {ep['title']}\n\n{content}\n\n---\n{CTA_BLOCK}"
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(full_content)
        print(f"💾 Gespeichert: {out_file.name}")
    
    # WordPress updaten
    if update_wp:
        print("🌐 Update WordPress...")
        post_id = get_wp_post_id(headers, ep['podlove_id'])
        if post_id:
            wp_content = markdown.markdown(content) + "\n\n" + CTA_BLOCK
            if update_wordpress_post(headers, post_id, wp_content):
                print(f"   ✅ Post {post_id} aktualisiert")
            else:
                print(f"   ❌ Update fehlgeschlagen")
        else:
            print("   ❌ Post-ID nicht gefunden")
    
    return True

# =============================================================================
# MAIN
# =============================================================================

def main():
    creds = load_env()
    
    # API Clients
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("❌ ANTHROPIC_API_KEY nicht gesetzt")
        return
    
    client = anthropic.Anthropic()
    headers = get_auth_header(creds.get("WP_USER", ""), creds.get("WP_APP_PASSWORD", ""))
    
    while True:
        choice = show_menu()
        
        if choice == "1":
            nr = input("Episode-Nummer (1-69): ").strip()
            if nr.isdigit():
                process_episode(client, headers, int(nr))
        
        elif choice == "2":
            range_input = input("Range (z.B. 1-10 oder 5,10,15): ").strip()
            if "-" in range_input:
                start, end = map(int, range_input.split("-"))
                episodes = list(range(start, end + 1))
            else:
                episodes = [int(x.strip()) for x in range_input.split(",")]
            
            confirm = input(f"\n{len(episodes)} Episoden verarbeiten? (j/n): ").strip().lower()
            if confirm == "j":
                for nr in episodes:
                    process_episode(client, headers, nr)
        
        elif choice == "3":
            nr = input("Episode-Nummer: ").strip()
            if nr.isdigit():
                process_episode(client, headers, int(nr), update_wp=False)
        
        elif choice == "4":
            print("Bye!")
            break

if __name__ == "__main__":
    main()
