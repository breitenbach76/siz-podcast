#!/usr/bin/env python3
"""
SiZ YouTube Description Generator v3.0
======================================
Generiert SEO-optimierte YouTube-Beschreibungen für den Podcast
"Schweigen ist Zustimmung" basierend auf WordPress/Podlove-Daten.

NEU in v3.0:
- Extrahiert Episodennummer aus Audio-Dateinamen (SiZ_XX.mp3)
- Nutzt die bereits in WordPress gespeicherten Kapitelmarken
- Parsed das eingebettete Podlove-JSON korrekt

Verwendung:
    python3 siz-youtube-generator.py --refresh-cache
    python3 siz-youtube-generator.py --episode 42
    python3 siz-youtube-generator.py --generate

Autor: Claude (für Patrick Breitenbach)
Stand: 2025-12-25
"""

import json
import os
import re
import sys
import argparse
import html
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List
from collections import Counter

# ============================================================
# KONFIGURATION
# ============================================================

class Config:
    WORDPRESS_API_URL = "https://schweigenistzustimmung.de/wp-json/wp/v2/episodes"
    CACHE_FILE = "siz-wordpress-cache.json"
    CACHE_MAX_AGE_HOURS = 24
    OUTPUT_DIR = "./youtube-descriptions"
    
    # Transkripte
    DEFAULT_TRANSCRIPTS_DIR = "./transcripts"
    
    # KI-Kapitelgenerierung
    AI_MODEL = "claude-sonnet-4-20250514"
    MAX_CHAPTERS = 10
    MIN_CHAPTER_MINUTES = 5


# ============================================================
# WORDPRESS PARSER (NEU!)
# ============================================================

def decode_unicode_escapes(s: str) -> str:
    """Dekodiert \\uXXXX Sequenzen zu echten Unicode-Zeichen."""
    def replace_unicode(match):
        return chr(int(match.group(1), 16))
    return re.sub(r'\\u([0-9a-fA-F]{4})', replace_unicode, s)


class PodloveDataExtractor:
    """Extrahiert strukturierte Daten aus dem Podlove-Player-JSON im WordPress-Content."""
    
    @staticmethod
    def extract_from_content(content: str) -> Optional[Dict]:
        """Extrahiert das Podlove-JSON aus dem WordPress-Content."""
        if not content:
            return None
        
        # Das JSON ist in podlovePlayerCache.add([...]) eingebettet
        # Pattern: "data":{...} innerhalb des ersten Array-Elements
        
        # Finde den JSON-Block
        match = re.search(r'"data"\s*:\s*(\{[^}]+?"version"\s*:\s*5[^}]*\})', content)
        if not match:
            # Alternativ: Suche nach dem kompletten data-Block
            match = re.search(r'"data"\s*:\s*(\{.+?"audio"\s*:\s*\[.+?\]\})', content, re.DOTALL)
        
        if not match:
            return None
        
        try:
            # Versuche das JSON zu parsen
            json_str = match.group(1)
            # Repariere escaped quotes
            json_str = json_str.replace('\\"', '"').replace('\\/', '/')
            return json.loads(json_str)
        except json.JSONDecodeError:
            # Fallback: Extrahiere einzelne Felder mit Regex
            return PodloveDataExtractor._extract_fields_regex(content)
    
    @staticmethod
    def _extract_fields_regex(content: str) -> Dict:
        """Fallback: Extrahiert einzelne Felder mit Regex."""
        result = {}
        
        # Episodennummer aus Audio-URL
        audio_match = re.search(r'SiZ[_-](\d+)\.mp3', content)
        if audio_match:
            result['episode_nr'] = int(audio_match.group(1))
        
        # Titel
        title_match = re.search(r'"title"\s*:\s*"([^"]+)"', content)
        if title_match:
            result['title'] = html.unescape(title_match.group(1))
        
        # Kapitelmarken
        chapters = []
        chapter_pattern = r'"start"\s*:\s*"([^"]+)"\s*,\s*"title"\s*:\s*"([^"]+)"'
        for match in re.finditer(chapter_pattern, content):
            chapters.append({
                'start': match.group(1),
                'title': html.unescape(match.group(2))
            })
        if chapters:
            result['chapters'] = chapters
        
        # Duration
        duration_match = re.search(r'"duration"\s*:\s*"([^"]+)"', content)
        if duration_match:
            result['duration'] = duration_match.group(1)
        
        return result
    
    @staticmethod
    def extract_episode_number(content: str) -> Optional[int]:
        """Extrahiert die Episodennummer aus dem Audio-Dateinamen."""
        # Pattern: SiZ_XX.mp3 oder SiZ-XX.mp3
        match = re.search(r'SiZ[_-](\d+)\.mp3', content, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None
    
    @staticmethod
    def extract_chapters(content: str) -> List[Dict]:
        """Extrahiert Kapitelmarken aus dem Content."""
        chapters = []
        
        # Pattern für Kapitel im Podlove-JSON
        chapter_pattern = r'"start"\s*:\s*"(\d{2}:\d{2}:\d{2}(?:\.\d+)?)"[^}]*"title"\s*:\s*"([^"]+)"'
        
        for match in re.finditer(chapter_pattern, content):
            start_time = match.group(1)
            title = match.group(2)
            
            # Dekodiere Unicode-Escapes (\u00e4 → ä) und HTML-Entities
            title = decode_unicode_escapes(title)
            title = html.unescape(title)
            
            # Konvertiere zu YouTube-Format (M:SS oder H:MM:SS)
            youtube_ts = PodloveDataExtractor._convert_timestamp(start_time)
            
            chapters.append({
                'timestamp': youtube_ts,
                'title': title
            })
        
        return chapters
    
    @staticmethod
    def _convert_timestamp(podlove_ts: str) -> str:
        """Konvertiert Podlove-Timestamp (HH:MM:SS.mmm) zu YouTube-Format."""
        # Parse HH:MM:SS.mmm
        match = re.match(r'(\d{2}):(\d{2}):(\d{2})', podlove_ts)
        if not match:
            return "0:00"
        
        hours, minutes, seconds = map(int, match.groups())
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes}:{seconds:02d}"
    
    @staticmethod
    def extract_teaser(content: str) -> str:
        """Extrahiert den Teaser-Text aus dem Content."""
        # Der Teaser beginnt nach dem Player-Script und vor "Themen"
        
        # Entferne den JavaScript-Teil
        text = re.sub(r'document\.addEventListener.*?\}\);', '', content, flags=re.DOTALL)
        
        # Entferne CSS
        text = re.sub(r'\.podlove-web-player[^}]+\}', '', text)
        
        # Bereinige HTML
        text = re.sub(r'<[^>]+>', ' ', text)
        text = html.unescape(text)
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Entferne führende JavaScript-Reste (});, whitespace, etc.)
        text = re.sub(r'^[\s\}\)\;\.]+', '', text)
        
        # Dekodiere Unicode-Escapes
        text = decode_unicode_escapes(text)
        
        # Schneide bei "Themen" oder "Erwähnte Personen" ab
        for marker in ['Themen ', 'Erwähnte Personen', 'Weiterführende Quellen', 'Unterstützen & Folgen']:
            if marker in text:
                text = text[:text.index(marker)].strip()
                break
        
        # Kürze auf sinnvolle Länge (max. 1500 Zeichen)
        if len(text) > 1500:
            # Finde letzten Satzpunkt vor 1500
            cut_point = text[:1500].rfind('.')
            if cut_point > 500:
                text = text[:cut_point + 1]
            else:
                text = text[:1500] + '...'
        
        return text


# ============================================================
# WORDPRESS CACHE
# ============================================================

class WordPressCache:
    """Verwaltet den lokalen Cache der WordPress-Episoden."""
    
    def __init__(self, cache_file: str = None):
        self.cache_file = cache_file or Config.CACHE_FILE
        self.episodes = {}
        self._load_cache()
    
    def _load_cache(self):
        """Lädt den Cache aus der Datei."""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.episodes = data.get('episodes', {})
                    self.cached_at = data.get('cached_at', '')
                    
                    if self.cached_at:
                        cached_time = datetime.fromisoformat(self.cached_at)
                        age_hours = (datetime.now() - cached_time).total_seconds() / 3600
                        status = "⚠️  VERALTET" if age_hours > Config.CACHE_MAX_AGE_HOURS else "✅"
                        print(f"{status} Cache geladen: {len(self.episodes)} Episoden ({age_hours:.1f}h alt)")
            except Exception as e:
                print(f"❌ Cache-Ladefehler: {e}")
                self.episodes = {}
    
    def refresh(self) -> bool:
        """Lädt alle Episoden von WordPress und aktualisiert den Cache."""
        try:
            import requests
        except ImportError:
            print("❌ 'requests' nicht installiert. Bitte: pip3 install requests")
            return False
        
        print("📥 Lade Episoden von WordPress...")
        all_episodes = []
        page = 1
        per_page = 100
        
        while True:
            url = f"{Config.WORDPRESS_API_URL}?per_page={per_page}&page={page}"
            print(f"   Seite {page}...")
            
            try:
                response = requests.get(url, timeout=30)
                if response.status_code != 200:
                    print(f"❌ API-Fehler: {response.status_code}")
                    break
                
                episodes = response.json()
                if not episodes:
                    break
                
                all_episodes.extend(episodes)
                
                if len(episodes) < per_page:
                    break
                page += 1
            except Exception as e:
                print(f"❌ Fehler: {e}")
                break
        
        print(f"✅ {len(all_episodes)} Episoden von API geladen")
        
        # Verarbeite Episoden
        self.episodes = {}
        skipped = 0
        
        for ep in all_episodes:
            raw_content = ep.get('content', {}).get('rendered', '')
            
            # Extrahiere Episodennummer aus Audio-Dateinamen
            episode_nr = PodloveDataExtractor.extract_episode_number(raw_content)
            
            if episode_nr is None:
                skipped += 1
                continue
            
            # Extrahiere Kapitelmarken
            chapters = PodloveDataExtractor.extract_chapters(raw_content)
            
            # Extrahiere Teaser
            teaser = PodloveDataExtractor.extract_teaser(raw_content)
            
            # Bereinige Titel
            title = html.unescape(ep.get('title', {}).get('rendered', f'Episode {episode_nr}'))
            title = decode_unicode_escapes(title)
            
            self.episodes[str(episode_nr)] = {
                'wp_post_id': ep.get('id'),
                'episode_nr': episode_nr,
                'title': title,
                'teaser': teaser,
                'chapters': chapters,
                'link': ep.get('link', ''),
                'date': ep.get('date', ''),
                'slug': ep.get('slug', ''),
            }
        
        print(f"✅ {len(self.episodes)} Episoden verarbeitet ({skipped} übersprungen)")
        
        # Cache speichern
        cache_data = {
            'cached_at': datetime.now().isoformat(),
            'episode_count': len(self.episodes),
            'episodes': self.episodes
        }
        
        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        
        print(f"💾 Cache gespeichert: {self.cache_file}")
        return True
    
    def get_episode(self, episode_nr: int) -> Optional[Dict]:
        """Holt eine Episode anhand der Nummer."""
        return self.episodes.get(str(episode_nr))
    
    def get_all_episode_numbers(self) -> List[int]:
        """Gibt alle verfügbaren Episodennummern zurück."""
        return sorted([int(k) for k in self.episodes.keys()])


# ============================================================
# CHAPTER GENERATOR (KI + Fallback)
# ============================================================

class ChapterGenerator:
    """Generiert Kapitelmarken aus SRT-Transkripten."""
    
    def __init__(self, transcripts_dir: str = None, api_key: str = None):
        self.transcripts_dir = transcripts_dir or Config.DEFAULT_TRANSCRIPTS_DIR
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
    
    def generate_for_episode(self, episode_nr: int, title: str = "") -> List[Dict]:
        """Generiert Kapitelmarken für eine Episode."""
        # Finde SRT-Datei
        srt_path = self._find_srt_file(episode_nr)
        if not srt_path:
            print(f"      ⚠️  Kein Transkript für Episode {episode_nr}")
            return [{'timestamp': '0:00', 'title': 'Start'}]
        
        # Lade Transkript
        transcript = self._load_transcript(srt_path)
        if not transcript:
            return [{'timestamp': '0:00', 'title': 'Start'}]
        
        # KI-Generierung wenn API-Key vorhanden
        if self.api_key:
            chapters = self._generate_ai_chapters(transcript, title, episode_nr)
            if chapters:
                return chapters
        
        # Fallback: Regelbasiert
        return self._generate_rule_based_chapters(transcript)
    
    def _find_srt_file(self, episode_nr: int) -> Optional[str]:
        """Findet die SRT-Datei für eine Episode."""
        patterns = [
            f"SiZ_{episode_nr:02d}.srt",
            f"SiZ_{episode_nr}.srt",
            f"siz_{episode_nr:02d}.srt",
        ]
        for pattern in patterns:
            path = os.path.join(self.transcripts_dir, pattern)
            if os.path.exists(path):
                return path
        return None
    
    def _load_transcript(self, srt_path: str) -> List[Dict]:
        """Lädt und parst eine SRT-Datei."""
        try:
            with open(srt_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            print(f"      ❌ Fehler beim Laden: {e}")
            return []
        
        # Parse SRT
        pattern = r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n((?:.*\n)*?(?=\n\d+\n|\Z))'
        
        subtitles = []
        for match in re.finditer(pattern, content):
            start_ts = match.group(2)
            text = match.group(4).strip()
            
            # Parse timestamp to seconds
            h, m, s = start_ts.replace(',', '.').split(':')
            seconds = int(h) * 3600 + int(m) * 60 + float(s)
            
            subtitles.append({
                'seconds': seconds,
                'text': text
            })
        
        return subtitles
    
    def _generate_ai_chapters(self, transcript: List[Dict], title: str, episode_nr: int) -> List[Dict]:
        """Generiert Kapitelmarken mit Claude API."""
        try:
            import anthropic
        except ImportError:
            print("      ⚠️  anthropic nicht installiert, nutze Fallback")
            return []
        
        # Erstelle komprimierten Transkript-Text mit Zeitmarken
        # Alle 2 Minuten einen Marker setzen
        text_with_markers = []
        last_marker = -120
        
        for sub in transcript:
            if sub['seconds'] - last_marker >= 120:  # Alle 2 Minuten
                minutes = int(sub['seconds'] // 60)
                text_with_markers.append(f"\n[{minutes} min]\n")
                last_marker = sub['seconds']
            text_with_markers.append(sub['text'])
        
        full_text = ' '.join(text_with_markers)
        
        # Kürze auf ~12.000 Zeichen für API
        if len(full_text) > 12000:
            # Gleichmäßig samplen
            chunk_size = len(full_text) // 6
            samples = []
            for i in range(0, len(full_text), chunk_size):
                samples.append(full_text[i:i+2000])
            full_text = '\n[...]\n'.join(samples)
        
        prompt = f"""Analysiere dieses Podcast-Transkript und erstelle 6-10 YouTube-Kapitelmarken.

Podcast: "Schweigen ist Zustimmung" - Kritischer Politik-Podcast
Episode {episode_nr}: {title}

Transkript (mit Zeitmarkern in Minuten):
{full_text}

REGELN:
1. Erstes Kapitel MUSS "0:00 Intro" sein
2. Kapitel mindestens 5 Minuten auseinander
3. Kapitelname: Max. 45 Zeichen, deutsch, prägnant
4. Thematisch sinnvolle Abschnitte (Themenwechsel, neue Aspekte)
5. Format: M:SS oder H:MM:SS (bei >60 Min)
6. Nutze die [X min] Marker zur Orientierung

AUSGABE NUR in diesem Format, keine Erklärung:
0:00 Intro
5:30 Kapitelname
12:45 Nächstes Kapitel
..."""

        client = anthropic.Anthropic(api_key=self.api_key)
        
        try:
            response = client.messages.create(
                model=Config.AI_MODEL,
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Parse Antwort
            chapters = []
            for line in response.content[0].text.strip().split('\n'):
                line = line.strip()
                if not line:
                    continue
                match = re.match(r'^(\d+:\d{2}(?::\d{2})?)\s+(.+)$', line)
                if match:
                    chapters.append({
                        'timestamp': match.group(1),
                        'title': match.group(2).strip()[:50]
                    })
            
            if chapters:
                print(f"      ✨ {len(chapters)} KI-Kapitel generiert")
                return chapters
            
        except Exception as e:
            print(f"      ⚠️  Claude API Fehler: {e}")
        
        return []
    
    def _generate_rule_based_chapters(self, transcript: List[Dict]) -> List[Dict]:
        """Regelbasierte Kapitelgenerierung als Fallback."""
        if not transcript:
            return [{'timestamp': '0:00', 'title': 'Start'}]
        
        total_seconds = transcript[-1]['seconds']
        total_minutes = total_seconds / 60
        
        # Berechne Kapitelanzahl (alle 10-15 Minuten)
        num_chapters = min(Config.MAX_CHAPTERS, max(4, int(total_minutes / 12)))
        interval = total_seconds / num_chapters
        
        chapters = [{'timestamp': '0:00', 'title': 'Intro'}]
        
        for i in range(1, num_chapters):
            target_time = i * interval
            
            # Finde nächsten Satzanfang
            for sub in transcript:
                if sub['seconds'] >= target_time:
                    # Prüfe auf Satzanfang
                    text = sub['text'].strip()
                    if text and len(text) > 10:
                        # Extrahiere erste Wörter als Titel
                        words = text.split()[:6]
                        title = ' '.join(words)
                        if len(title) > 40:
                            title = title[:37] + '...'
                        
                        # Formatiere Timestamp
                        mins = int(sub['seconds'] // 60)
                        secs = int(sub['seconds'] % 60)
                        if mins >= 60:
                            hours = mins // 60
                            mins = mins % 60
                            ts = f"{hours}:{mins:02d}:{secs:02d}"
                        else:
                            ts = f"{mins}:{secs:02d}"
                        
                        chapters.append({
                            'timestamp': ts,
                            'title': title
                        })
                        break
        
        return chapters


# ============================================================
# KEYWORD EXTRACTOR (mit KI-Option)
# ============================================================

class KeywordExtractor:
    """Extrahiert relevante Keywords/Hashtags aus Text."""
    
    STOPWORDS = {
        'der', 'die', 'das', 'und', 'ist', 'in', 'zu', 'den', 'mit', 'von',
        'für', 'auf', 'nicht', 'sich', 'auch', 'es', 'ein', 'eine', 'einer',
        'als', 'an', 'dem', 'des', 'so', 'wie', 'aber', 'oder', 'wenn', 'noch',
        'werden', 'wird', 'wurde', 'hat', 'haben', 'sein', 'sind', 'war', 'waren',
        'dass', 'kann', 'können', 'soll', 'muss', 'will', 'wir', 'ihr', 'sie',
        'ich', 'du', 'er', 'uns', 'man', 'diese', 'nach', 'bei', 'über', 'unter',
        'vor', 'durch', 'gegen', 'ohne', 'um', 'aus', 'bis', 'seit', 'dann',
        'also', 'denn', 'weil', 'sehr', 'mehr', 'viel', 'nur', 'schon', 'immer',
        'wieder', 'hier', 'jetzt', 'heute', 'mal', 'ganz', 'ja', 'nein', 'doch',
        'patrick', 'jens', 'episode', 'folge', 'podcast', 'prozent', 'menschen',
        'dabei', 'gibt', 'gibt', 'müssen', 'können', 'werden', 'während', 'sowie'
    }
    
    BASE_HASHTAGS = ['#Politik', '#Podcast']
    
    TOPIC_HASHTAGS = {
        'trump': ['#Trump', '#USA', '#MAGA'],
        'maga': ['#MAGA', '#USA'],
        'afd': ['#AfD', '#Rechtsextremismus'],
        'cdu': ['#CDU'],
        'merz': ['#Merz', '#CDU'],
        'klima': ['#Klimakrise', '#Umwelt'],
        'cop': ['#COP30', '#Klimakonferenz', '#Klimakrise'],
        'ukraine': ['#Ukraine', '#Krieg'],
        'gaza': ['#Gaza', '#Israel', '#Nahost'],
        'israel': ['#Israel', '#Nahost'],
        'kapitalismus': ['#Kapitalismus', '#Wirtschaft'],
        'neoliberal': ['#Neoliberalismus'],
        'migration': ['#Migration'],
        'medien': ['#Medien', '#Journalismus'],
        'demokratie': ['#Demokratie'],
        'faschismus': ['#Faschismus'],
        'rechtsextrem': ['#Rechtsextremismus'],
        'sudan': ['#Sudan', '#Afrika'],
        'venezuela': ['#Venezuela'],
        'epstein': ['#Epstein'],
        'bildung': ['#Bildung'],
        'wohnen': ['#Wohnungskrise'],
        'arbeit': ['#Arbeit', '#Gewerkschaft'],
    }
    
    @staticmethod
    def extract_hashtags(text: str, title: str = "", max_hashtags: int = 7) -> List[str]:
        """Extrahiert relevante Hashtags aus Text und Titel (Fallback-Methode)."""
        hashtags = list(KeywordExtractor.BASE_HASHTAGS)
        combined_text = f"{title} {text}".lower()
        
        # Themen-basierte Hashtags
        for keyword, tags in KeywordExtractor.TOPIC_HASHTAGS.items():
            if keyword in combined_text:
                for tag in tags:
                    if tag not in hashtags and len(hashtags) < max_hashtags:
                        hashtags.append(tag)
        
        # Frequenz-basierte Keywords als Fallback
        if len(hashtags) < max_hashtags:
            words = re.findall(r'\b[a-zäöüß]{5,}\b', combined_text)
            word_freq = Counter(words)
            for word in KeywordExtractor.STOPWORDS:
                word_freq.pop(word, None)
            
            for word, count in word_freq.most_common(5):
                if count >= 3 and len(hashtags) < max_hashtags:
                    tag = f"#{word.capitalize()}"
                    if tag not in hashtags:
                        hashtags.append(tag)
        
        return hashtags[:max_hashtags]
    
    @staticmethod
    def generate_ai_hashtags(title: str, teaser: str, api_key: str, max_hashtags: int = 8) -> List[str]:
        """Generiert KI-optimierte YouTube-Hashtags."""
        try:
            import anthropic
        except ImportError:
            return KeywordExtractor.extract_hashtags(teaser, title, max_hashtags)
        
        teaser_short = teaser[:1000] if len(teaser) > 1000 else teaser
        
        prompt = f"""Generiere {max_hashtags} YouTube-Hashtags für diese deutsche Politik-Podcast-Episode.

TITEL: {title}
BESCHREIBUNG: {teaser_short}

ANFORDERUNGEN:
1. Exakt {max_hashtags} Hashtags
2. Mix aus: 2-3 breite Reichweite (#Politik #Deutschland #Podcast) + 4-5 themenspezifisch
3. Deutsche UND englische Hashtags erlaubt (was auf YouTube besser rankt)
4. Trending/aktuelle Begriffe bevorzugen
5. Format: #Hashtag (mit Großbuchstabe am Anfang jedes Worts)

YOUTUBE-SEO-TIPPS einarbeiten:
- Breite Tags für Reichweite: #Politik #Germany #Podcast #News
- Spezifische für Relevanz: #Klimakrise #AfD #Bundestagswahl etc.
- Emotionale: #Wahrheit #Aufklärung #Analyse

AUSGABE: Nur die Hashtags, durch Leerzeichen getrennt, keine Erklärung."""

        client = anthropic.Anthropic(api_key=api_key)
        
        try:
            response = client.messages.create(
                model=Config.AI_MODEL,
                max_tokens=100,
                messages=[{"role": "user", "content": prompt}]
            )
            
            result = response.content[0].text.strip()
            
            # Parse Hashtags
            hashtags = re.findall(r'#\w+', result)
            
            if hashtags and len(hashtags) >= 3:
                return hashtags[:max_hashtags]
            
        except Exception as e:
            pass  # Fallback nutzen
        
        return KeywordExtractor.extract_hashtags(teaser, title, max_hashtags)


# ============================================================
# YOUTUBE DESCRIPTION GENERATOR
# ============================================================

class YouTubeDescriptionGenerator:
    """Generiert optimierte YouTube-Beschreibungen."""
    
    TEMPLATE = """🎙️ {seo_hook}

{teaser}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📌 KAPITEL
{timestamps}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔔 Kanal abonnieren: https://www.youtube.com/@SchweiST
🎧 Alle Plattformen: https://schweigenistzustimmung.de

💬 Discord-Community: https://discord.gg/YJ3AWjPA8X
☕ Unterstützen (Steady): https://steadyhq.com/de/schweigenistzustimmung

📱 Social Media:
• TikTok: https://www.tiktok.com/@schweigenistzustimmung
• Instagram: https://www.instagram.com/schweigenistzustimmung/
• Bluesky: https://bsky.app/profile/schwist.bsky.social

💸 Direkt unterstützen:
• PayPal: patrick@soziopod.de
• IBAN: DE69 4306 0967 1210 9626 00

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{hashtags}

#SchweigenIstZustimmung"""

    def __init__(self, cache: WordPressCache, transcripts_dir: str = None, api_key: str = None):
        self.cache = cache
        self.api_key = api_key
        self.chapter_generator = ChapterGenerator(transcripts_dir, api_key)
    
    def generate(self, episode_nr: int) -> Optional[str]:
        """Generiert YouTube-Beschreibung für eine Episode."""
        episode = self.cache.get_episode(episode_nr)
        
        if not episode:
            print(f"   ⚠️  Episode {episode_nr} nicht im Cache")
            return None
        
        title = episode.get('title', f'Episode {episode_nr}')
        teaser = episode.get('teaser', '')
        wp_chapters = episode.get('chapters', [])
        
        # Fallback-Teaser
        if not teaser or len(teaser) < 50:
            teaser = f"Episode {episode_nr}: {title} – Der wöchentlich andere Blick auf Politik und Kultur mit Patrick und Jens."
        
        # SEO-Hook + Hashtags: KI-generiert (kombinierter Call) oder Fallback
        if self.api_key:
            seo_hook, hashtags = self._generate_ai_seo_content(title, teaser, episode_nr)
        else:
            seo_hook = self._create_seo_hook_fallback(title, teaser)
            hashtags = KeywordExtractor.extract_hashtags(teaser, title)
        
        # Kapitelmarken: WordPress → KI → Fallback
        if wp_chapters and len(wp_chapters) > 1:
            chapters = wp_chapters
            print(f"      📖 {len(chapters)} WordPress-Kapitel")
        else:
            print(f"      🤖 Generiere Kapitel...")
            chapters = self.chapter_generator.generate_for_episode(episode_nr, title)
        
        # Stelle sicher, dass erstes Kapitel bei 0:00 ist (YouTube-Requirement!)
        if chapters and chapters[0]['timestamp'] != '0:00':
            chapters.insert(0, {'timestamp': '0:00', 'title': 'Intro'})
        
        # Timestamps formatieren
        timestamps_text = '\n'.join([f"{c['timestamp']} {c['title']}" for c in chapters])
        
        # Hashtags formatieren
        hashtags_text = ' '.join(hashtags)
        
        return self.TEMPLATE.format(
            seo_hook=seo_hook,
            teaser=teaser,
            timestamps=timestamps_text,
            hashtags=hashtags_text
        )
    
    def _generate_ai_seo_content(self, title: str, teaser: str, episode_nr: int) -> tuple:
        """Generiert SEO-Hook UND Hashtags in einem API-Call (spart Kosten)."""
        try:
            import anthropic
        except ImportError:
            return self._create_seo_hook_fallback(title, teaser), KeywordExtractor.extract_hashtags(teaser, title)
        
        teaser_short = teaser[:1500] if len(teaser) > 1500 else teaser
        
        prompt = f"""Du bist ein YouTube-SEO-Experte. Erstelle für diese deutsche Politik-Podcast-Episode:

EPISODE: {title}
BESCHREIBUNG: {teaser_short}

AUFGABE 1 - SEO-HOOK (erste Zeile der YouTube-Beschreibung):
- EXAKT 140-155 Zeichen
- Beginne mit ZAHL, FRAGE oder PROVOKATION
- YouTube-SEO-Keywords einbauen
- Neugier wecken, zum Klicken animieren
- Deutsch, prägnant, emotional

AUFGABE 2 - HASHTAGS (für YouTube-Algorithmus):
- Exakt 8 Hashtags
- Mix: 3 breite (#Politik #Deutschland #Podcast) + 5 themenspezifische
- Deutsche UND internationale Tags erlaubt
- Trending-Begriffe bevorzugen

FORMAT DER ANTWORT (exakt so, keine Erklärung):
HOOK: [Dein SEO-Hook hier]
TAGS: #Tag1 #Tag2 #Tag3 #Tag4 #Tag5 #Tag6 #Tag7 #Tag8"""

        client = anthropic.Anthropic(api_key=self.api_key)
        
        try:
            response = client.messages.create(
                model=Config.AI_MODEL,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}]
            )
            
            result = response.content[0].text.strip()
            
            # Parse Hook
            hook_match = re.search(r'HOOK:\s*(.+?)(?:\n|$)', result)
            hook = hook_match.group(1).strip().strip('"\'') if hook_match else None
            
            # Parse Hashtags
            tags_match = re.search(r'TAGS:\s*(.+?)(?:\n|$)', result)
            if tags_match:
                hashtags = re.findall(r'#\w+', tags_match.group(1))
            else:
                hashtags = re.findall(r'#\w+', result)
            
            # Validierung
            if hook and 100 < len(hook) < 180 and hashtags and len(hashtags) >= 5:
                print(f"      ✨ KI-SEO: Hook ({len(hook)} Z.) + {len(hashtags)} Hashtags")
                return hook, hashtags[:8]
            else:
                print(f"      ⚠️  KI-Antwort ungültig, nutze Fallback")
                
        except Exception as e:
            print(f"      ⚠️  SEO API Fehler: {e}")
        
        # Fallback
        return self._create_seo_hook_fallback(title, teaser), KeywordExtractor.extract_hashtags(teaser, title)
    
    def _create_seo_hook_fallback(self, title: str, teaser: str) -> str:
        """Fallback: Erstellt einen einfachen SEO-Hook ohne KI."""
        # Erster Satz des Teasers
        first_sentence = teaser.split('.')[0] if teaser else ""
        hook = f"{title} – {first_sentence}"
        
        # Kürze auf max. 160 Zeichen, aber am Wortende
        if len(hook) > 160:
            cut_pos = hook[:157].rfind(' ')
            if cut_pos > 100:
                hook = hook[:cut_pos] + "..."
            else:
                hook = hook[:157] + "..."
        
        return hook


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='SiZ YouTube Description Generator v3.0',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  python3 siz-youtube-generator.py --refresh-cache
  python3 siz-youtube-generator.py --episode 42
  python3 siz-youtube-generator.py --generate
  python3 siz-youtube-generator.py --list
        """
    )
    
    parser.add_argument('--refresh-cache', action='store_true',
                        help='WordPress-Cache aktualisieren')
    parser.add_argument('--episode', type=int,
                        help='Einzelne Episode generieren')
    parser.add_argument('--generate', action='store_true',
                        help='Alle Episoden generieren')
    parser.add_argument('--list', action='store_true',
                        help='Alle verfügbaren Episoden auflisten')
    parser.add_argument('--debug', type=int,
                        help='Debug-Infos für eine Episode anzeigen')
    parser.add_argument('--output-dir', type=str, default=Config.OUTPUT_DIR,
                        help=f'Ausgabe-Verzeichnis (default: {Config.OUTPUT_DIR})')
    parser.add_argument('--cache-file', type=str, default=Config.CACHE_FILE,
                        help=f'Cache-Datei (default: {Config.CACHE_FILE})')
    parser.add_argument('--transcripts-dir', type=str, default=Config.DEFAULT_TRANSCRIPTS_DIR,
                        help=f'Transkript-Verzeichnis (default: {Config.DEFAULT_TRANSCRIPTS_DIR})')
    parser.add_argument('--no-ai', action='store_true',
                        help='Keine KI-Generierung für fehlende Kapitel')
    
    args = parser.parse_args()
    
    # Cache initialisieren
    cache = WordPressCache(args.cache_file)
    
    # Cache aktualisieren
    if args.refresh_cache:
        cache.refresh()
        # Lade Cache neu
        cache = WordPressCache(args.cache_file)
        if not args.episode and not args.generate and not args.list:
            return
    
    # Episoden auflisten
    if args.list:
        episodes = cache.get_all_episode_numbers()
        print(f"\n📋 {len(episodes)} Episoden im Cache:")
        for nr in episodes:
            ep = cache.get_episode(nr)
            chapters_count = len(ep.get('chapters', []))
            teaser_len = len(ep.get('teaser', ''))
            print(f"   {nr:3d}: {ep.get('title', '?')[:50]}... ({chapters_count} Kapitel, {teaser_len} Zeichen Teaser)")
        return
    
    # Debug-Modus
    if args.debug is not None:
        ep = cache.get_episode(args.debug)
        if not ep:
            print(f"❌ Episode {args.debug} nicht im Cache")
            return
        print(f"\n🔍 DEBUG Episode {args.debug}:")
        print(f"   Titel: {ep.get('title', '?')}")
        print(f"   WP Post-ID: {ep.get('wp_post_id', '?')}")
        print(f"   Link: {ep.get('link', '?')}")
        print(f"   Kapitelmarken: {len(ep.get('chapters', []))}")
        for ch in ep.get('chapters', []):
            print(f"      {ch['timestamp']} {ch['title']}")
        print(f"   Teaser ({len(ep.get('teaser', ''))} Zeichen):")
        teaser = ep.get('teaser', '')[:500]
        print(f"      {teaser}...")
        return
    
    # Generator initialisieren
    api_key = None if args.no_ai else os.getenv('ANTHROPIC_API_KEY')
    if not args.no_ai and not api_key:
        print("ℹ️  ANTHROPIC_API_KEY nicht gesetzt. Nutze --no-ai oder setze den Key für KI-Kapitel.")
    
    generator = YouTubeDescriptionGenerator(
        cache, 
        transcripts_dir=args.transcripts_dir,
        api_key=api_key
    )
    
    # Ausgabe-Verzeichnis erstellen
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Einzelne Episode
    if args.episode is not None:
        print(f"\n🎬 Generiere Episode {args.episode}...")
        description = generator.generate(args.episode)
        
        if description:
            output_file = os.path.join(args.output_dir, f"SiZ_{args.episode:02d}_youtube.txt")
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(description)
            
            print(f"\n{'='*60}")
            print(description)
            print(f"{'='*60}")
            print(f"\n✅ Gespeichert: {output_file}")
        else:
            print(f"❌ Konnte Episode {args.episode} nicht generieren")
        return
    
    # Alle Episoden
    if args.generate:
        episode_numbers = cache.get_all_episode_numbers()
        print(f"\n🎬 Generiere {len(episode_numbers)} Episoden...")
        
        success, failed = 0, 0
        
        for ep_nr in episode_numbers:
            print(f"   Episode {ep_nr}...", end=' ')
            description = generator.generate(ep_nr)
            
            if description:
                output_file = os.path.join(args.output_dir, f"SiZ_{ep_nr:02d}_youtube.txt")
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(description)
                print("✅")
                success += 1
            else:
                print("❌")
                failed += 1
        
        print(f"\n📊 Ergebnis: {success} erfolgreich, {failed} fehlgeschlagen")
        print(f"📁 Ausgabe: {args.output_dir}/")
        return
    
    # Keine Aktion gewählt
    parser.print_help()


if __name__ == '__main__':
    main()
