import requests
from typing import List
from colorama import Fore, Style, init
import getpass
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

    def _request(self, method: str, url: str, params: dict = None, data: dict = None, json: dict = None) -> requests.Response:
        """Handles requests with authentication and token refresh."""
        if not self.access_token and not self.authenticate():
            raise Exception(Fore.RED + "Authentication failed")

        headers = {'Authorization': f'Bearer {self.access_token}'}
        response = requests.request(method, url, params=params, data=data, json=json, headers=headers)

        if response.status_code == 401:
            if self.refresh_access_token():
                headers['Authorization'] = f'Bearer {self.access_token}'
                response = requests.request(method, url, params=params, data=data, json=json, headers=headers)

        return response

    def authenticate(self) -> bool:
        """Authenticate with MangaDex using password grant."""
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
        """Refresh access token using the refresh token."""
        if not self.refresh_token:
            print(Fore.RED + "No refresh token available.")
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
                print(Fore.GREEN + "Token refresh successful!")
                return True
            print(Fore.RED + f"Token refresh failed: {response.text}")
            return False
        except Exception as e:
            print(Fore.RED + f"Token refresh error: {e}")
            return False

    def get_anilist_manga_list(self, username: str) -> List[dict]:
        """Fetch manga list from AniList."""
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
        print(Fore.RED + "Failed to fetch AniList manga list")
        return []

    def find_mangadex_manga(self, anilist_title: str) -> str:
        """Search MangaDex for manga by title."""
        search_strategies = [
            lambda title: title,
            lambda title: title.lower(),
            lambda title: title.replace(':', ''),
            lambda title: title.split(':')[0].strip()
        ]

        for strategy in search_strategies:
            modified_title = strategy(anilist_title)
            params = {'title': modified_title, 'limit': 5}
            response = self._request('GET', f'{self.mangadex_base_url}/manga', params=params)
            if response and response.status_code == 200:
                results = response.json().get('data', [])
                if results:
                    for manga in results:
                        titles = manga.get('attributes', {}).get('title', {})
                        print(Fore.CYAN + f"Potential match found: {titles}")
                    return results[0]['id']

        print(Fore.RED + f"No MangaDex entry found for: {anilist_title}")
        return None

    def update_mangadex_reading_status(self, manga_id: str, status: str) -> bool:
        """Update reading status for manga on MangaDex."""
        status_mapping = {
            'CURRENT': 'reading', 'COMPLETED': 'completed', 'PAUSED': 'on_hold', 'DROPPED': 'dropped', 'PLANNING': 'plan_to_read'
        }
        
        follow_response = self._request('POST', f'{self.mangadex_base_url}/manga/{manga_id}/follow')
        if follow_response and follow_response.status_code == 200:
            payload = {'status': status_mapping.get(status, 'reading')}
            status_response = self._request('POST', f'{self.mangadex_base_url}/manga/{manga_id}/status', json=payload)
            if status_response and status_response.status_code == 200:
                print(Fore.GREEN + f"Status updated for manga {manga_id}")
                return True
            print(Fore.RED + f"Failed to update status for manga {manga_id}")
        else:
            print(Fore.RED + f"Failed to follow manga {manga_id}")
        return False

    def sync_manga_list(self, anilist_username: str):
        """Sync manga list from AniList to MangaDex."""
        anilist_manga = self.get_anilist_manga_list(anilist_username)
        if not anilist_manga:
            print(Fore.RED + "No AniList manga to sync")
            return

        total_manga = len(anilist_manga)
        synced_manga = 0
        failed_manga = []

        for index, manga in enumerate(anilist_manga, 1):
            title = manga['media']['title'].get('english') or manga['media']['title'].get('romaji') or manga['media']['title'].get('native')
            print(Fore.YELLOW + f"Processing manga {index}/{total_manga}: {title}")
            time.sleep(0.5)

            try:
                mangadex_id = self.find_mangadex_manga(title)
                if mangadex_id:
                    if self.update_mangadex_reading_status(mangadex_id, manga['status']):
                        synced_manga += 1
                        print(Fore.GREEN + f"Synced: {title} - Success")
                    else:
                        failed_manga.append(title)
                else:
                    failed_manga.append(title)

            except Exception as e:
                print(Fore.RED + f"Error processing {title}: {e}")
                failed_manga.append(title)

        # Final summary
        print(Fore.YELLOW + f"\n--- Synchronization complete ---")
        print(Fore.GREEN + f"Successfully synced: {synced_manga}/{total_manga}")
        if failed_manga:
            print(Fore.RED + "\nManga that failed to sync:")
            for manga in failed_manga:
                print(Fore.RED + f"- {manga}")


def main():
    print(Fore.YELLOW + "--- MangaDex Sync ---")

    username = input("Enter your MangaDex username: ").strip()
    password = getpass.getpass("Enter your MangaDex password: ").strip()
    client_id = input("Enter your MangaDex client ID: ").strip()
    client_secret = getpass.getpass("Enter your MangaDex client secret: ").strip()

    if not all([username, password, client_id, client_secret]):
        print(Fore.RED + "Error: All fields are required")
        return

    try:
        syncer = MangaDexSync()
        syncer.username = username
        syncer.password = password
        syncer.mangadex_client_id = client_id
        syncer.mangadex_client_secret = client_secret
        
        anilist_username = input("Enter your AniList username: ").strip()
        if not anilist_username:
            print(Fore.RED + "Error: AniList username is required")
            return
        syncer.sync_manga_list(anilist_username)
    except Exception as e:
        print(Fore.RED + f"An error occurred: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()
