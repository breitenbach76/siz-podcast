#!/usr/bin/env python3
import base64
from pathlib import Path

try:
    import requests
except ImportError:
    print("pip3 install requests")
    exit(1)

SITE_URL = "https://schweigenistzustimmung.de"

def load_credentials():
    env_file = Path(__file__).parent / ".env"
    if not env_file.exists():
        print("❌ .env Datei nicht gefunden!")
        exit(1)
    credentials = {}
    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                credentials[key.strip()] = value.strip()
    return credentials.get("WP_USER"), credentials.get("WP_APP_PASSWORD")

def test_api():
    print("Test 1: REST API erreichbar?")
    try:
        r = requests.get(f"{SITE_URL}/wp-json/wp/v2/posts?per_page=1", timeout=10)
        print(f"   {'✅' if r.status_code == 200 else '❌'} Status: {r.status_code}")
    except Exception as e:
        print(f"   ❌ Fehler: {e}")

def test_auth(user, pw):
    print("\nTest 2: Authentifizierung?")
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    headers = {"Authorization": f"Basic {token}"}
    try:
        r = requests.get(f"{SITE_URL}/wp-json/wp/v2/users/me", headers=headers, timeout=10)
        if r.status_code == 200:
            print(f"   ✅ Eingeloggt als: {r.json().get('name')}")
        else:
            print(f"   ❌ Status: {r.status_code}")
    except Exception as e:
        print(f"   ❌ Fehler: {e}")

def test_podlove(user, pw):
    print("\nTest 3: Podlove API?")
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    headers = {"Authorization": f"Basic {token}"}
    try:
        r = requests.get(f"{SITE_URL}/wp-json/podlove/v2/episodes", headers=headers, timeout=10)
        if r.status_code == 200:
            print(f"   ✅ {len(r.json().get('results', []))} Episoden gefunden")
        else:
            print(f"   ❌ Status: {r.status_code}")
    except Exception as e:
        print(f"   ❌ Fehler: {e}")

if __name__ == "__main__":
    print("=" * 40)
    print("SiZ WordPress Verbindungstest")
    print("=" * 40 + "\n")
    user, pw = load_credentials()
    print(f"User: {user}\n")
    test_api()
    test_auth(user, pw)
    test_podlove(user, pw)
    print("\n" + "=" * 40)
