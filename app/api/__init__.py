# Providers: scraper classes for each anime site
from app.api.multimovies import MultiMoviesProvider
from app.api.nxsha import NxShaProvider
from app.api.watchanimeworld import WatchAnimeWorldAPI

multimovies = MultiMoviesProvider()
nxsha = NxShaProvider()
watchanimeworld = WatchAnimeWorldAPI()

ALL_PROVIDERS = {
    'multimovies': multimovies,
    'nxsha': nxsha,
    'watchanimeworld': watchanimeworld,
}
