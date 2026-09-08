"""
TurboVid HLS provider - standalone player wrapper.
"""
import requests

class TurboVidHLSProvider:
    NAME = 'turbovidhls'

    def search_anime(self, query):
        return []

    def get_home_catalog(self):
        return []

    def get_anime_details(self, slug):
        return None

    def get_episodes(self, slug):
        return []

    def get_episode_streams(self, slug, season=1, episode=1):
        return {'streams': []}
