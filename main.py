import requests
from typing import List, Dict, Set
from colorama import Fore, init
import sys
import time
import os

init(autoreset=True)

class MangaDexSync:
    def __init__(self):
        self.anilist_api = 'https://graphql.anilist.co'
        self.mangadex_token_url = 'https://auth.mangadex.org/realms/mangadex/protocol/openid-connect/token'
        self.mangadex_base_url = 'https://api.mangadex.org'
        self.username = os.getenv('MANGADEX_USERNAME')
        self.password = os.getenv('MANGADEX_PASSWORD')
        self.mangadex_client_id = os.getenv('MANGADEX_CLIENT_ID')
        self.mangadex_client_secret = os.getenv('MANGADEX_CLIENT_SECRET')
        self.access_token = None
        self.refresh_token = None
        self.mangadex_manga_cache: Dict[str, str] = {}

    def _request(self, method: str, url: str, params: dict = None, data: dict = None, json: dict = None) -> requests.Response:
        if not self.access_token and not self.authenticate():
            raise Exception(Fore.RED + "Authentication failed")

        headers = {'Authorization': f'Bearer {self.access_token}'}
        response = requests.request(method, url, params=params, data=data, json=json, headers=headers)

        if response.status_code == 401 and self.refresh_access_token():
            headers['Authorization'] = f'Bearer {self.access_token}'
            response = requests.request(method, url, params=params, data=data, json=json, headers=headers)

        return response

    def get_current_mangadex_list(self) -> Set[str]:
        manga_ids = set()
        limit = 100
        offset = 0
        
        while True:
            response = self._request('GET', f'{self.mangadex_base_url}/user/follows/manga', 
                                  params={'limit': limit, 'offset': offset})
            
            if not response or response.status_code != 200:
                break
                
            data = response.json().get('data', [])
            if not data:
                break
                
            for manga in data:
                manga_id = manga.get('id')
                titles = manga.get('attributes', {}).get('title', {})
                if manga_id and titles:
                    manga_ids.add(manga_id)
                    for title in titles.values():
                        if title:
                            self.mangadex_manga_cache[title.lower()] = manga_id
                            
            offset += limit
            if len(data) < limit:
                break
                
        print(Fore.BLUE + f"Found {len(manga_ids)} manga in your MangaDex list")
        return manga_ids

    def authenticate(self) -> bool:
        creds = {
            "grant_type": "password",
            "username": self.username,
            "password": self.password,
            "client_id": self.mangadex_client_id,
            "client_secret": self.mangadex_client_secret
        }

        try:
            response = requests.post(self.mangadex_token_url, data=creds)
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data["access_token"]
                self.refresh_token = token_data.get("refresh_token")
                print(Fore.GREEN + "Authentication successful!")
                return True
            print(Fore.RED + f"Authentication failed: {response.text}")
            return False
        except Exception as e:
            print(Fore.RED + f"Authentication error: {e}")
            return False

    def refresh_access_token(self) -> bool:
        if not self.refresh_token:
            return False

        refresh_data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.mangadex_client_id,
            "client_secret": self.mangadex_client_secret
        }

        try:
            response = requests.post(self.mangadex_token_url, data=refresh_data)
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data["access_token"]
                self.refresh_token = token_data.get("refresh_token")
                return True
            return False
        except Exception:
            return False

    def find_mangadex_manga(self, anilist_titles: dict) -> str:
        for title in anilist_titles.values():
            if title and title.lower() in self.mangadex_manga_cache:
                return self.mangadex_manga_cache[title.lower()]

        titles_to_try = [
            anilist_titles.get('english'),
            anilist_titles.get('romaji'),
            anilist_titles.get('native')
        ]
        titles_to_try = [t for t in titles_to_try if t]

        search_strategies = [
            lambda title: title,
            lambda title: title.lower(),
            lambda title: title.replace(':', ''),
            lambda title: title.split(':')[0].strip()
        ]

        for title in titles_to_try:
            for strategy in search_strategies:
                modified_title = strategy(title)
                params = {'title': modified_title, 'limit': 5}
                response = self._request('GET', f'{self.mangadex_base_url}/manga', params=params)
                
                if response and response.status_code == 200:
                    results = response.json().get('data', [])
                    if results:
                        manga_id = results[0]['id']
                        for t in titles_to_try:
                            if t:
                                self.mangadex_manga_cache[t.lower()] = manga_id
                        return manga_id
                
                time.sleep(0.5)
        
        return None

    def get_anilist_manga_list(self, username: str) -> List[dict]:
        query = '''
        query ($username: String) {
            MediaListCollection(userName: $username, type: MANGA) {
                lists {
                    entries {
                        media {
                            title { romaji english native }
                            id
                        }
                        status
                        progress
                    }
                }
            }
        }
        '''
        variables = {'username': username}
        response = requests.post(self.anilist_api, json={'query': query, 'variables': variables})

        if response.status_code == 200:
            data = response.json()
            return [entry for list_group in data['data']['MediaListCollection']['lists'] for entry in list_group['entries']]
        return []

    def update_mangadex_reading_status(self, manga_id: str, status: str) -> bool:
        status_mapping = {
            'CURRENT': 'reading', 'COMPLETED': 'completed', 'PAUSED': 'on_hold', 
            'DROPPED': 'dropped', 'PLANNING': 'plan_to_read'
        }
        
        follow_response = self._request('POST', f'{self.mangadex_base_url}/manga/{manga_id}/follow')
        if follow_response and follow_response.status_code == 200:
            payload = {'status': status_mapping.get(status, 'reading')}
            status_response = self._request('POST', f'{self.mangadex_base_url}/manga/{manga_id}/status', json=payload)
            return status_response and status_response.status_code == 200
        return False

    def sync_manga_list(self, anilist_username: str):
        print(Fore.YELLOW + "Fetching your current MangaDex list...")
        current_mangadex_ids = self.get_current_mangadex_list()
        
        print(Fore.YELLOW + "Fetching your AniList manga...")
        anilist_manga = self.get_anilist_manga_list(anilist_username)
        if not anilist_manga:
            print(Fore.RED + "No AniList manga to sync")
            return

        total_manga = len(anilist_manga)
        synced_manga = 0
        skipped_manga = 0
        failed_manga = []

        for index, manga in enumerate(anilist_manga, 1):
            titles = manga['media']['title']
            primary_title = titles.get('english') or titles.get('romaji') or titles.get('native')
            print(Fore.YELLOW + f"Processing manga {index}/{total_manga}: {primary_title}")
            
            try:
                mangadex_id = self.find_mangadex_manga(titles)
                if not mangadex_id:
                    print(Fore.RED + f"Could not find manga on MangaDex: {primary_title}")
                    if titles.get('romaji'):
                        print(Fore.RED + f"(Romaji title tried: {titles['romaji']})")
                    failed_manga.append(primary_title)
                    continue

                if mangadex_id in current_mangadex_ids:
                    print(Fore.BLUE + f"Skipping already followed manga: {primary_title}")
                    skipped_manga += 1
                    continue

                if self.update_mangadex_reading_status(mangadex_id, manga['status']):
                    synced_manga += 1
                    print(Fore.GREEN + f"Synced: {primary_title}")
                else:
                    failed_manga.append(primary_title)
                    
                time.sleep(0.5)
                
            except Exception as e:
                print(Fore.RED + f"Error processing {primary_title}: {e}")
                failed_manga.append(primary_title)

        failed_count = len(failed_manga)
        print(Fore.YELLOW + f"\n--- Synchronization complete ---")
        print(Fore.GREEN + f"Successfully synced: {synced_manga}/{total_manga}")
        print(Fore.BLUE + f"Already in list (skipped): {skipped_manga}")
        print(Fore.RED + f"Failed to sync: {failed_count}")
        if failed_manga:
            print(Fore.RED + "\nManga that failed to sync:")
            for manga in failed_manga:
                print(Fore.RED + f"- {manga}")

def main():
    print(Fore.YELLOW + "--- MangaDex Sync ---")
    try:
        syncer = MangaDexSync()
        if not all([syncer.username, syncer.password, syncer.mangadex_client_id, syncer.mangadex_client_secret]):
            print(Fore.RED + "Error: Required environment variables are missing")
            sys.exit(1)
        anilist_username = os.getenv('ANILIST_USERNAME')
        if not anilist_username:
            print(Fore.RED + "Error: ANILIST_USERNAME environment variable is missing")
            sys.exit(1)
        syncer.sync_manga_list(anilist_username)
    except Exception as e:
        print(Fore.RED + f"An error occurred: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()
