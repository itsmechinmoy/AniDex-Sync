import requests
from typing import List, Dict, Set
from colorama import Fore, init
import sys
import time
import os
import concurrent.futures

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
                
        print(Fore.BLUE + f"Found {len(manga_ids)} existing manga in your MangaDex list")
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
        initial_count = len(current_mangadex_ids)
        
        print(Fore.YELLOW + "Fetching your AniList manga...")
        anilist_manga = self.get_anilist_manga_list(anilist_username)
        if not anilist_manga:
            print(Fore.RED + "No AniList manga to sync")
            return
    
        total_manga = len(anilist_manga)
        new_additions = [0]
        resynced = [0]
        skipped_manga = [0]
        failed_manga = []
        newly_added_titles = set()
        resynced_titles = set()
    
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = []
    
            for index, manga in enumerate(anilist_manga, 1):
                titles = manga['media']['title']
                primary_title = titles.get('english') or titles.get('romaji') or titles.get('native')
                print(Fore.YELLOW + f"Processing manga {index}/{total_manga}: {primary_title}")
    
                future = executor.submit(
                    self.process_manga, 
                    manga, 
                    primary_title, 
                    current_mangadex_ids, 
                    failed_manga, 
                    new_additions,
                    resynced,
                    skipped_manga,
                    newly_added_titles,
                    resynced_titles
                )
                futures.append(future)
    
            for future in concurrent.futures.as_completed(futures):
                future.result()
    
        failed_count = len(failed_manga)
        print(Fore.YELLOW + f"\n--- Synchronization Summary ---")
        print(Fore.BLUE + f"Initial MangaDex list size: {initial_count}")
        print(Fore.GREEN + f"New entries added: {new_additions[0]}")
        if newly_added_titles:
            print(Fore.GREEN + "Newly added manga:")
            for title in sorted(newly_added_titles):
                print(Fore.GREEN + f"  • {title}")
        print(Fore.CYAN + f"Existing entries re-synced: {resynced[0]}")
        print(Fore.RED + f"Failed to sync: {failed_count}/{total_manga}")
        print(Fore.CYAN + f"Skipped manga: {skipped_manga[0]}/{total_manga}")
        if failed_count:
            print(Fore.RED + "Failed manga:")
            for title in failed_manga:
                print(Fore.RED + f"  • {title}")

    def process_manga(self, manga: dict, primary_title: str, current_mangadex_ids: Set[str], 
                     failed_manga: list, new_additions: list, resynced: list, 
                     skipped_manga: list, newly_added_titles: set, resynced_titles: set):
        manga_id = manga['media']['id']
        status = manga['status']
        
        mangadex_id = self.find_mangadex_manga(manga['media']['title'])
        
        if not mangadex_id:
            print(Fore.RED + f"Could not find MangaDex ID for {primary_title}")
            failed_manga.append(primary_title)
            return
            
        is_new = mangadex_id not in current_mangadex_ids
        
        if self.update_mangadex_reading_status(mangadex_id, status):
            if is_new:
                print(Fore.GREEN + f"Added new manga: {primary_title}")
                new_additions[0] += 1
                newly_added_titles.add(primary_title)
            else:
                print(Fore.CYAN + f"Re-synced existing manga: {primary_title}")
                resynced[0] += 1
                resynced_titles.add(primary_title)
        else:
            failed_manga.append(primary_title)
            print(Fore.RED + f"Failed to update status for {primary_title}")

if __name__ == '__main__':
    anilist_username = os.getenv('ANILIST_USERNAME')
    if not anilist_username:
        print(Fore.RED + "Error: ANILIST_USERNAME environment variable not set")
        sys.exit(1)
    
    manga_sync = MangaDexSync()
    manga_sync.sync_manga_list(anilist_username)
