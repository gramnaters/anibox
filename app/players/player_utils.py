"""
Player utilities - thin wrapper around app.players package.
"""

from app.players import (
    detect_player,
    detect_player_url,
    get_player_handler,
    get_all_players,
    resolve_stream,
    PLAYER_ALIASES,
    PLAYER_DOMAINS,
    PLAYER_NAMES,
    PLAYER_HANDLERS,
    PLAYER_DISPLAY_NAMES,
)

# Re-export for backward compatibility
__all__ = [
    'detect_player',
    'detect_player_url',
    'get_player_handler',
    'get_all_players',
    'resolve_stream',
    'PLAYER_ALIASES',
    'PLAYER_DOMAINS',
    'PLAYER_NAMES',
    'PLAYER_HANDLERS',
    'PLAYER_DISPLAY_NAMES',
]
