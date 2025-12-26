#!/usr/bin/env python3
"""
SiZ YouTube Description Generator v4.2
======================================
NEU in v4.2:
- --fetch-videos mit intelligentem Title-Matching gegen WordPress-Cache

Verwendung:
    python3 siz-youtube-generator.py --fetch-videos
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
from difflib import SequenceMatcher

# YouTube API imports
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    YOUTUBE_API_AVAILABLE = True
except ImportError:
    YOUTUBE_API_AVAILABLE = False


class Config:
    WORDPRESS_API_URL = "https://schweigenistzustimmung.de/wp-json/wp/v2/episodes"
    CACHE_FILE = "siz-wordpress-cache.json"
    CACHE_MAX_AGE_HOURS = 24
    OUTPUT_DIR = "./youtube-descriptions"
    DEFAULT_TRANSCRIPTS_DIR = "./transcripts"
    AI_MODEL = "claude-sonnet-4-20250514"
    MAX_CHAPTERS = 10
    MIN_CHAPTER_MINUTES = 5
    YOUTUBE_IDS_FILE = "siz-youtube-ids.json"
    CLIENT_SECRETS_FILE = "client_secrets.json"
    YOUTUBE_TOKEN_FILE = "youtube_token.json"
    YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]


def decode_unicode_escapes(s: str) -> str:
    def replace_unicode(match):
        return chr(int(match.group(1), 16))
    return re.sub(r'\\u([0-9a-fA-F]{4})', replace_unicode, s)


class PodloveDataExtractor:
    @staticmethod
    def extract_episode_number(content: str) -> Optional[int]:
        match = re.search(r'SiZ[_-](\d+)\.mp3', content, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None
    
    @staticmethod
    def extract_chapters(content: str) -> List[Dict]:
        chapters = []
        chapter_pattern = r'"start"\s*:\s*"(\d{2}:\d{2}:\d{2}(?:\.\d+)?)"[^}]*"title"\s*:\s*"([^"]+)"'
        for match in re.finditer(chapter_pattern, content):
            start_time = match.group(1)
            title = decode_unicode_escapes(html.unescape(match.group(2)))
            hours, minutes, seconds = map(int, re.match(r'(\d{2}):(\d{2}):(\d{2})', start_time).groups())
            if hours > 0:
                youtube_ts = f"{hours}:{minutes:02d}:{seconds:02d}"
            else:
                youtube_ts = f"{minutes}:{seconds:02d}"
            chapters.append({'timestamp': youtube_ts, 'title': title})
        return chapters
    
    @staticmethod
    def extract_teaser(content: str) -> str:
        text = re.sub(r'document\.addEventListener.*?\}\);', '', content, flags=re.DOTALL)
        text = re.sub(r'\.podlove-web-player[^}]+\}', '', text)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = html.unescape(text)
        text = re.sub(r'\s+', ' ', text).strip()
        text = re.sub(r'^[\s\}\)\;\.]+', '', text)
        text = decode_unicode_escapes(text)
        for marker in ['Themen ', 'Erwähnte Personen', 'Weiterführende Quellen', 'Unterstützen & Folgen']:
            if marker in text:
                text = text[:text.index(marker)].strip()
                break
        if len(text) > 1500:
            cut_point = text[:1500].rfind('.')
            text = text[:cut_point + 1] if cut_point > 500 else text[:1500] + '...'
        return text


class WordPressCache:
    def __init__(self, cache_file: str = None):
        self.cache_file = cache_file or Config.CACHE_FILE
        self.episodes = {}
        self._load_cache()
    
    def _load_cache(self):
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
        try:
            import requests
        except ImportError:
            print("❌ 'requests' nicht installiert")
            return False
        
        print("📥 Lade Episoden von WordPress...")
        all_episodes = []
        page = 1
        
        while True:
            url = f"{Config.WORDPRESS_API_URL}?per_page=100&page={page}"
            print(f"   Seite {page}...")
            try:
                response = requests.get(url, timeout=30)
                if response.status_code != 200:
                    break
                episodes = response.json()
                if not episodes:
                    break
                all_episodes.extend(episodes)
                if len(episodes) < 100:
                    break
                page += 1
            except Exception as e:
                print(f"❌ Fehler: {e}")
                break
        
        print(f"✅ {len(all_episodes)} Episoden von API geladen")
        self.episodes = {}
        
        for ep in all_episodes:
            raw_content = ep.get('content', {}).get('rendered', '')
            episode_nr = PodloveDataExtractor.extract_episode_number(raw_content)
            if episode_nr is None:
                continue
            
            title = html.unescape(ep.get('title', {}).get('rendered', f'Episode {episode_nr}'))
            title = decode_unicode_escapes(title)
            
            self.episodes[str(episode_nr)] = {
                'wp_post_id': ep.get('id'),
                'episode_nr': episode_nr,
                'title': title,
                'teaser': PodloveDataExtractor.extract_teaser(raw_content),
                'chapters': PodloveDataExtractor.extract_chapters(raw_content),
                'link': ep.get('link', ''),
                'date': ep.get('date', ''),
                'slug': ep.get('slug', ''),
            }
        
        print(f"✅ {len(self.episodes)} Episoden verarbeitet")
        
        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump({'cached_at': datetime.now().isoformat(), 'episode_count': len(self.episodes), 'episodes': self.episodes}, f, ensure_ascii=False, indent=2)
        print(f"💾 Cache gespeichert: {self.cache_file}")
        return True
    
    def get_episode(self, episode_nr: int) -> Optional[Dict]:
        return self.episodes.get(str(episode_nr))
    
    def get_all_episode_numbers(self) -> List[int]:
        return sorted([int(k) for k in self.episodes.keys()])
    
    def get_title_to_episode_mapping(self) -> Dict[str, int]:
        """Erstellt ein normalisiertes Titel → Episode-Nr Mapping."""
        mapping = {}
        for ep_nr, ep_data in self.episodes.items():
            title = ep_data.get('title', '')
            normalized = self._normalize_title(title)
            mapping[normalized] = int(ep_nr)
        return mapping
    
    @staticmethod
    def _normalize_title(title: str) -> str:
        t = title.lower()
        t = re.sub(r'[^\w\säöüß]', '', t)
        t = re.sub(r'\s+', ' ', t).strip()
        return t


class ChapterGenerator:
    def __init__(self, transcripts_dir: str = None, api_key: str = None):
        self.transcripts_dir = transcripts_dir or Config.DEFAULT_TRANSCRIPTS_DIR
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
    
    def generate_for_episode(self, episode_nr: int, title: str = "") -> List[Dict]:
        srt_path = self._find_srt_file(episode_nr)
        if not srt_path:
            return [{'timestamp': '0:00', 'title': 'Start'}]
        transcript = self._load_transcript(srt_path)
        if not transcript:
            return [{'timestamp': '0:00', 'title': 'Start'}]
        if self.api_key:
            chapters = self._generate_ai_chapters(transcript, title, episode_nr)
            if chapters:
                return chapters
        return self._generate_rule_based_chapters(transcript)
    
    def _find_srt_file(self, episode_nr: int) -> Optional[str]:
        for pattern in [f"SiZ_{episode_nr:02d}.srt", f"SiZ_{episode_nr}.srt"]:
            path = os.path.join(self.transcripts_dir, pattern)
            if os.path.exists(path):
                return path
        return None
    
    def _load_transcript(self, srt_path: str) -> List[Dict]:
        try:
            with open(srt_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except:
            return []
        pattern = r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n((?:.*\n)*?(?=\n\d+\n|\Z))'
        subtitles = []
        for match in re.finditer(pattern, content):
            h, m, s = match.group(2).replace(',', '.').split(':')
            subtitles.append({'seconds': int(h)*3600 + int(m)*60 + float(s), 'text': match.group(4).strip()})
        return subtitles
    
    def _generate_ai_chapters(self, transcript, title, episode_nr):
        try:
            import anthropic
        except ImportError:
            return []
        text_parts = []
        last_marker = -120
        for sub in transcript:
            if sub['seconds'] - last_marker >= 120:
                text_parts.append(f"\n[{int(sub['seconds']//60)} min]\n")
                last_marker = sub['seconds']
            text_parts.append(sub['text'])
        full_text = ' '.join(text_parts)[:12000]
        
        prompt = f"""Erstelle 6-10 YouTube-Kapitelmarken für diesen Podcast.
Episode {episode_nr}: {title}
Transkript: {full_text}
REGELN: Erstes Kapitel "0:00 Intro", min. 5 Min Abstand, max 45 Zeichen.
AUSGABE NUR: Timestamp Titel (eine pro Zeile)"""
        
        try:
            client = anthropic.Anthropic(api_key=self.api_key)
            response = client.messages.create(model=Config.AI_MODEL, max_tokens=600, messages=[{"role": "user", "content": prompt}])
            chapters = []
            for line in response.content[0].text.strip().split('\n'):
                match = re.match(r'^(\d+:\d{2}(?::\d{2})?)\s+(.+)$', line.strip())
                if match:
                    chapters.append({'timestamp': match.group(1), 'title': match.group(2)[:50]})
            if chapters:
                return chapters
        except:
            pass
        return []
    
    def _generate_rule_based_chapters(self, transcript):
        if not transcript:
            return [{'timestamp': '0:00', 'title': 'Start'}]
        total = transcript[-1]['seconds']
        num = min(10, max(4, int(total/60/12)))
        chapters = [{'timestamp': '0:00', 'title': 'Intro'}]
        for i in range(1, num):
            target = i * total / num
            for sub in transcript:
                if sub['seconds'] >= target and len(sub['text']) > 10:
                    mins, secs = int(sub['seconds']//60), int(sub['seconds']%60)
                    ts = f"{mins//60}:{mins%60:02d}:{secs:02d}" if mins >= 60 else f"{mins}:{secs:02d}"
                    chapters.append({'timestamp': ts, 'title': ' '.join(sub['text'].split()[:6])[:40]})
                    break
        return chapters


class KeywordExtractor:
    STOPWORDS = {'der','die','das','und','ist','in','zu','den','mit','von','für','auf','nicht','sich','auch','es','ein','eine','als','an','dem','so','wie','aber','oder','wenn','noch','werden','wird','hat','haben','sein','sind','war','dass','kann','soll','muss','will','wir','sie','ich','man','nach','bei','über','vor','durch','gegen','um','aus','bis','dann','also','sehr','mehr','viel','nur','schon','immer','wieder','hier','jetzt','heute','mal','ganz','patrick','jens','episode','folge','podcast','menschen'}
    TOPIC_HASHTAGS = {'trump':['#Trump','#USA'],'afd':['#AfD'],'cdu':['#CDU'],'merz':['#Merz'],'klima':['#Klimakrise'],'ukraine':['#Ukraine'],'gaza':['#Gaza'],'israel':['#Israel'],'migration':['#Migration'],'demokratie':['#Demokratie']}
    
    @staticmethod
    def extract_hashtags(text, title="", max_hashtags=7):
        hashtags = ['#Politik', '#Podcast']
        combined = f"{title} {text}".lower()
        for kw, tags in KeywordExtractor.TOPIC_HASHTAGS.items():
            if kw in combined:
                for t in tags:
                    if t not in hashtags and len(hashtags) < max_hashtags:
                        hashtags.append(t)
        return hashtags[:max_hashtags]


class YouTubeDescriptionGenerator:
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

    def __init__(self, cache, transcripts_dir=None, api_key=None):
        self.cache = cache
        self.api_key = api_key
        self.chapter_generator = ChapterGenerator(transcripts_dir, api_key)
    
    def generate(self, episode_nr):
        episode = self.cache.get_episode(episode_nr)
        if not episode:
            return None
        title = episode.get('title', f'Episode {episode_nr}')
        teaser = episode.get('teaser', '') or f"Episode {episode_nr}: {title}"
        wp_chapters = episode.get('chapters', [])
        
        if self.api_key:
            seo_hook, hashtags = self._generate_ai_seo(title, teaser)
        else:
            seo_hook = f"{title} – {teaser.split('.')[0]}"[:160]
            hashtags = KeywordExtractor.extract_hashtags(teaser, title)
        
        chapters = wp_chapters if len(wp_chapters) > 1 else self.chapter_generator.generate_for_episode(episode_nr, title)
        if chapters and chapters[0]['timestamp'] != '0:00':
            chapters.insert(0, {'timestamp': '0:00', 'title': 'Intro'})
        
        return self.TEMPLATE.format(
            seo_hook=seo_hook,
            teaser=teaser,
            timestamps='\n'.join([f"{c['timestamp']} {c['title']}" for c in chapters]),
            hashtags=' '.join(hashtags)
        )
    
    def _generate_ai_seo(self, title, teaser):
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.api_key)
            prompt = f"""YouTube-SEO für Politik-Podcast:
TITEL: {title}
TEXT: {teaser[:1000]}

Erstelle:
HOOK: 140-155 Zeichen, beginnt mit Zahl/Frage, deutsch
TAGS: 8 Hashtags (#Politik #Deutschland + themenspezifisch)

Format:
HOOK: [text]
TAGS: #tag1 #tag2 ..."""
            response = client.messages.create(model=Config.AI_MODEL, max_tokens=200, messages=[{"role":"user","content":prompt}])
            result = response.content[0].text
            hook_match = re.search(r'HOOK:\s*(.+?)(?:\n|$)', result)
            hook = hook_match.group(1).strip().strip('"\'') if hook_match else title[:150]
            hashtags = re.findall(r'#\w+', result)
            return hook, hashtags[:8] if len(hashtags) >= 3 else KeywordExtractor.extract_hashtags(teaser, title)
        except:
            return f"{title} – {teaser.split('.')[0]}"[:160], KeywordExtractor.extract_hashtags(teaser, title)


class YouTubeClient:
    def __init__(self):
        self.service = None
        self.channel_id = None
    
    def authenticate(self):
        if not YOUTUBE_API_AVAILABLE:
            print("❌ pip3 install google-api-python-client google-auth-oauthlib")
            return False
        creds = None
        if os.path.exists(Config.YOUTUBE_TOKEN_FILE):
            try:
                creds = Credentials.from_authorized_user_file(Config.YOUTUBE_TOKEN_FILE, Config.YOUTUBE_SCOPES)
            except:
                pass
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except:
                    creds = None
            if not creds:
                if not os.path.exists(Config.CLIENT_SECRETS_FILE):
                    print(f"❌ {Config.CLIENT_SECRETS_FILE} nicht gefunden!")
                    return False
                print("🔐 OAuth-Flow startet...")
                flow = InstalledAppFlow.from_client_secrets_file(Config.CLIENT_SECRETS_FILE, Config.YOUTUBE_SCOPES)
                creds = flow.run_local_server(port=0)
            with open(Config.YOUTUBE_TOKEN_FILE, 'w') as f:
                f.write(creds.to_json())
        self.service = build('youtube', 'v3', credentials=creds)
        print("✅ YouTube API authentifiziert")
        return True
    
    def get_channel_id(self):
        if not self.service:
            return None
        try:
            response = self.service.channels().list(part='id,snippet', mine=True).execute()
            if response.get('items'):
                self.channel_id = response['items'][0]['id']
                print(f"📺 Kanal: {response['items'][0]['snippet']['title']} ({self.channel_id})")
                return self.channel_id
        except Exception as e:
            print(f"❌ {e}")
        return None
    
    def fetch_all_videos(self):
        if not self.service or not self.channel_id:
            return []
        videos = []
        next_page = None
        print("📥 Lade Videos...")
        try:
            channel_resp = self.service.channels().list(part='contentDetails', id=self.channel_id).execute()
            uploads_id = channel_resp['items'][0]['contentDetails']['relatedPlaylists']['uploads']
            while True:
                resp = self.service.playlistItems().list(part='snippet', playlistId=uploads_id, maxResults=50, pageToken=next_page).execute()
                for item in resp.get('items', []):
                    s = item['snippet']
                    videos.append({'video_id': s['resourceId']['videoId'], 'title': s['title'], 'published_at': s['publishedAt']})
                next_page = resp.get('nextPageToken')
                print(f"   {len(videos)} Videos...")
                if not next_page:
                    break
        except Exception as e:
            print(f"❌ {e}")
        print(f"✅ {len(videos)} Videos gefunden")
        return videos


def title_similarity(a, b):
    """Berechnet Ähnlichkeit zwischen zwei Titeln (0-1)."""
    def norm(t):
        t = t.lower()
        t = re.sub(r'[^\w\säöüß]', '', t)
        return re.sub(r'\s+', ' ', t).strip()
    return SequenceMatcher(None, norm(a), norm(b)).ratio()


def fetch_youtube_videos():
    """Holt Videos und matched gegen WordPress-Cache."""
    client = YouTubeClient()
    if not client.authenticate() or not client.get_channel_id():
        return False
    
    videos = client.fetch_all_videos()
    if not videos:
        return False
    
    # Lade WordPress-Cache für Title-Matching
    cache = WordPressCache()
    title_to_ep = cache.get_title_to_episode_mapping()
    
    mapping = {}
    unmatched = []
    
    print("\n🔍 Matche Videos gegen WordPress-Episoden...")
    
    for video in videos:
        video_id = video['video_id']
        yt_title = video['title']
        
        # 1. Versuche Episodennummer aus Titel
        ep_num = None
        for pattern in [r'#(\d+)', r'Episode\s*(\d+)', r'Folge\s*(\d+)', r'SiZ[_\-]?\s*(\d+)', r'^\s*(\d+)\s*[:\.\-–]']:
            match = re.search(pattern, yt_title, re.IGNORECASE)
            if match:
                ep_num = int(match.group(1))
                if 0 <= ep_num <= 999:
                    break
                ep_num = None
        
        # 2. Wenn keine Nummer, versuche Title-Matching
        if ep_num is None:
            best_score = 0
            best_ep = None
            for wp_title_norm, wp_ep in title_to_ep.items():
                score = title_similarity(yt_title, wp_title_norm)
                if score > best_score:
                    best_score = score
                    best_ep = wp_ep
            
            if best_score >= 0.7:  # 70% Ähnlichkeit
                ep_num = best_ep
                print(f"   ✅ Episode {ep_num}: {video_id} (Title-Match {best_score:.0%})")
            else:
                unmatched.append(video)
                continue
        else:
            print(f"   ✅ Episode {ep_num}: {video_id} (Nummer im Titel)")
        
        if str(ep_num) not in mapping:
            mapping[str(ep_num)] = video_id
    
    print(f"\n📊 {len(mapping)} Episoden zugeordnet, {len(unmatched)} nicht erkannt")
    
    if unmatched:
        print("\n⚠️  Nicht zugeordnete Videos:")
        for v in unmatched[:10]:
            print(f"   • {v['video_id']}: {v['title'][:50]}...")
        if len(unmatched) > 10:
            print(f"   ... und {len(unmatched)-10} weitere")
    
    # Merge mit existierender Datei
    existing = {}
    if os.path.exists(Config.YOUTUBE_IDS_FILE):
        try:
            with open(Config.YOUTUBE_IDS_FILE, 'r') as f:
                existing = {k:v for k,v in json.load(f).items() if not k.startswith('_')}
        except:
            pass
    
    for ep, vid in mapping.items():
        existing[ep] = vid
    
    output = {
        '_info': 'Episode → YouTube Video ID',
        '_updated': datetime.now().isoformat(),
        '_total': len([v for v in existing.values() if v]),
    }
    output.update(dict(sorted(existing.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0)))
    
    with open(Config.YOUTUBE_IDS_FILE, 'w') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n💾 {Config.YOUTUBE_IDS_FILE}: {output['_total']} Episoden mit Video-IDs")
    return True


def main():
    parser = argparse.ArgumentParser(description='SiZ YouTube Generator v4.2')
    parser.add_argument('--refresh-cache', action='store_true', help='WordPress-Cache aktualisieren')
    parser.add_argument('--episode', type=int, help='Einzelne Episode generieren')
    parser.add_argument('--generate', action='store_true', help='Alle Episoden generieren')
    parser.add_argument('--list', action='store_true', help='Episoden auflisten')
    parser.add_argument('--debug', type=int, help='Debug-Infos')
    parser.add_argument('--fetch-videos', action='store_true', help='Video-IDs vom YouTube-Kanal holen')
    parser.add_argument('--output-dir', default=Config.OUTPUT_DIR)
    parser.add_argument('--cache-file', default=Config.CACHE_FILE)
    parser.add_argument('--transcripts-dir', default=Config.DEFAULT_TRANSCRIPTS_DIR)
    parser.add_argument('--no-ai', action='store_true', help='Keine KI')
    args = parser.parse_args()
    
    if args.fetch_videos:
        fetch_youtube_videos()
        return
    
    cache = WordPressCache(args.cache_file)
    
    if args.refresh_cache:
        cache.refresh()
        cache = WordPressCache(args.cache_file)
        if not args.episode and not args.generate and not args.list:
            return
    
    if args.list:
        for nr in cache.get_all_episode_numbers():
            ep = cache.get_episode(nr)
            print(f"   {nr:3d}: {ep.get('title','?')[:50]}...")
        return
    
    if args.debug:
        ep = cache.get_episode(args.debug)
        if ep:
            print(json.dumps(ep, indent=2, ensure_ascii=False)[:2000])
        return
    
    api_key = None if args.no_ai else os.getenv('ANTHROPIC_API_KEY')
    generator = YouTubeDescriptionGenerator(cache, args.transcripts_dir, api_key)
    os.makedirs(args.output_dir, exist_ok=True)
    
    if args.episode:
        desc = generator.generate(args.episode)
        if desc:
            path = os.path.join(args.output_dir, f"SiZ_{args.episode:02d}_youtube.txt")
            with open(path, 'w') as f:
                f.write(desc)
            print(desc)
            print(f"\n✅ {path}")
        return
    
    if args.generate:
        for nr in cache.get_all_episode_numbers():
            desc = generator.generate(nr)
            if desc:
                with open(os.path.join(args.output_dir, f"SiZ_{nr:02d}_youtube.txt"), 'w') as f:
                    f.write(desc)
                print(f"✅ Episode {nr}")
        return
    
    parser.print_help()


if __name__ == '__main__':
    main()
