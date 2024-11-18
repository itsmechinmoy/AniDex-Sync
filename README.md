# AniDex Sync
A tool for synchronizing manga reading lists between AniList and MangaDex via GitHub Actions.

## Overview
This project automatically synchronizes your manga reading list from AniList to MangaDex. It uses Python with `requests` for API interactions, and concurrent processing for efficiency and supports multiple title-matching strategies.

## Features
- Authenticates with MangaDex using provided credentials
- Fetches complete manga list from AniList
- Automatically adds and updates manga reading status on MangaDex
- Supports concurrent processing for faster synchronization
- Handles multiple title variations for precise manga matching

## Setup
1. **Create a Repository from Template**
   Click the "Use this template" button on the GitHub repository page to create a new repository from this template.

2. **Add Repository Secrets**
   Go to your repository settings on GitHub:
   - Navigate to `Settings` > `Secrets and variables` > `Actions`.
   - Add the following secrets:
     - `MANGADEX_USERNAME`: Your MangaDex username
     - `MANGADEX_PASSWORD`: Your MangaDex password
     - `MANGADEX_CLIENT_ID`: MangaDex OAuth client ID
     - `MANGADEX_CLIENT_SECRET`: MangaDex OAuth client secret
     - `ANILIST_USERNAME`: Your AniList username

3. **Run the GitHub Action**
   Go to the `Actions` tab of your repository:
   - Find the "MangaDex Sync" workflow.
   - Click "Run workflow" to start the synchronization process.

## Need Help with Authentication?
To get MangaDex client ID and secret:
1. Go to https://mangadex.org/settings
2. Navigate to `Client` section
3. Click `New Client`
4. Create a client 
5. Copy the generated client ID and secret
