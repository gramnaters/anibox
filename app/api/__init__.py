# Providers: scraper classes for each anime site
from app.api.multimovies import MultiMoviesProvider
from app.api.watchanimeworld import WatchAnimeWorldAPI
from app.api.toonstream import ToonStreamProvider
from app.api.piratexplay import PirateXPlayProvider

multimovies = MultiMoviesProvider()
watchanimeworld = WatchAnimeWorldAPI()
toonstream = ToonStreamProvider()
piratexplay = PirateXPlayProvider()

ALL_PROVIDERS = {
    'multimovies': multimovies,
    'watchanimeworld': watchanimeworld,
    'toonstream': toonstream,
    'piratexplay': piratexplay,
}
