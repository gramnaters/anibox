# Providers: scraper classes for each anime site
from app.api.multimovies import MultiMoviesProvider
from app.api.nxsha import NxShaProvider
from app.api.watchanimeworld import WatchAnimeWorldAPI
from app.api.toonstream import ToonStreamProvider
from app.api.piratexplay import PirateXPlayProvider
from app.api.screenscape import ScreenScapeProvider

multimovies = MultiMoviesProvider()
nxsha = NxShaProvider()
watchanimeworld = WatchAnimeWorldAPI()
toonstream = ToonStreamProvider()
piratexplay = PirateXPlayProvider()
screenscape = ScreenScapeProvider()

ALL_PROVIDERS = {
    'multimovies': multimovies,
    'nxsha': nxsha,
    'watchanimeworld': watchanimeworld,
    'toonstream': toonstream,
    'piratexplay': piratexplay,
    'screenscape': screenscape,
}
