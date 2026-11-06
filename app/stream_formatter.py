"""Rich stream labelling and AIOStreams-compatible metadata.

AIOStreams derives its ``{stream.*}`` formatter variables from:

* ``behaviorHints.filename``  -> resolution, quality, encode, audio tags,
  languages, release group, container, title/season/episode (parsed with a
  scene-release parser),
* ``behaviorHints.videoSize`` -> ``{stream.size}``,
* ``behaviorHints.indexer``   -> ``{stream.indexer}``,
* country-flag emojis in ``description``/``name`` -> ``{stream.languages}``.

Upstream providers mostly hand us a bare HLS URL, so this module probes the
playlist/file to recover the real resolution, bitrate, duration, codec and
audio languages, then emits a scene-style filename plus a rich label so both
Nuvio's stream list and AIOStreams' formatter have every value available.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

import requests
from cachetools import TTLCache

_probe_cache = TTLCache(maxsize=3000, ttl=1800)

# ---------------------------------------------------------------- languages

LANGUAGE_FLAGS = {
    'Hindi': '\U0001F1EE\U0001F1F3',
    'Japanese': '\U0001F1EF\U0001F1F5',
    'English': '\U0001F1EC\U0001F1E7',
    # India has one flag for all its languages.
    'Tamil': '\U0001F1EE\U0001F1F3',
    'Telugu': '\U0001F1EE\U0001F1F3',
    'Bengali': '\U0001F1E7\U0001F1E9',
    'Malayalam': '\U0001F1EE\U0001F1F3',
    'Kannada': '\U0001F1EE\U0001F1F3',
    'Marathi': '\U0001F1EE\U0001F1F3',
    'Punjabi': '\U0001F1EE\U0001F1F3',
    'Korean': '\U0001F1F0\U0001F1F7',
    'Chinese': '\U0001F1E8\U0001F1F3',
    'Spanish': '\U0001F1EA\U0001F1F8',
    'French': '\U0001F1EB\U0001F1F7',
    'German': '\U0001F1E9\U0001F1EA',
    'Italian': '\U0001F1EE\U0001F1F9',
    'Russian': '\U0001F1F7\U0001F1FA',
    'Arabic': '\U0001F1F8\U0001F1E6',
    'Portuguese': '\U0001F1F5\U0001F1F9',
    'Turkish': '\U0001F1F9\U0001F1F7',
    'Indonesian': '\U0001F1EE\U0001F1E9',
    'Thai': '\U0001F1F9\U0001F1ED',
    'Vietnamese': '\U0001F1FB\U0001F1F3',
    'Multi Audio': '\U0001F310',
}

_NATIVE_LANGUAGE_NAMES = {
    'हिन्दी': 'Hindi', 'हिंदी': 'Hindi',
    '日本語': 'Japanese', '英語': 'English',
    'தமிழ்': 'Tamil', 'తెలుగు': 'Telugu',
    'বাংলা': 'Bengali', 'മലയാളം': 'Malayalam',
    'ಕನ್ನಡ': 'Kannada', 'मराठी': 'Marathi',
    'ਪੰਜਾਬੀ': 'Punjabi', '한국어': 'Korean',
    '中文': 'Chinese', 'Español': 'Spanish',
    'Français': 'French', 'Deutsch': 'German',
}

_LANG_CODES = {
    'hi': 'Hindi', 'hin': 'Hindi',
    'ja': 'Japanese', 'jpn': 'Japanese', 'jap': 'Japanese',
    'en': 'English', 'eng': 'English',
    'ta': 'Tamil', 'tam': 'Tamil',
    'te': 'Telugu', 'tel': 'Telugu',
    'bn': 'Bengali', 'ben': 'Bengali',
    'ml': 'Malayalam', 'mal': 'Malayalam',
    'kn': 'Kannada', 'kan': 'Kannada',
    'mr': 'Marathi', 'mar': 'Marathi',
    'pa': 'Punjabi', 'pan': 'Punjabi',
    'ko': 'Korean', 'kor': 'Korean',
    'zh': 'Chinese', 'chi': 'Chinese',
    'es': 'Spanish', 'spa': 'Spanish',
    'fr': 'French', 'fra': 'French', 'fre': 'French',
    'de': 'German', 'deu': 'German', 'ger': 'German',
    'it': 'Italian', 'ita': 'Italian',
    'ru': 'Russian', 'rus': 'Russian',
    'ar': 'Arabic', 'ara': 'Arabic',
    'pt': 'Portuguese', 'por': 'Portuguese',
    'tr': 'Turkish', 'tur': 'Turkish',
    'id': 'Indonesian', 'ind': 'Indonesian',
    'th': 'Thai', 'tha': 'Thai',
    'vi': 'Vietnamese', 'vie': 'Vietnamese',
}

# What each provider ships by default (from the manifest's own descriptions).
PROVIDER_LANGUAGES = {
    'multimovies': ('Hindi',),
    'nxsha': ('Hindi',),
    'watchanimeworld': ('Hindi', 'Japanese'),
    'toonstream': ('Hindi', 'English'),
    'piratexplay': ('Multi Audio',),
    'screenscape': ('Hindi', 'English'),
}


def _language_name(value):
    if isinstance(value, dict):
        value = value.get('name') or value.get('label') or value.get('language') or ''
    text = str(value or '').strip()
    if not text:
        return ''
    if text in _NATIVE_LANGUAGE_NAMES:
        return _NATIVE_LANGUAGE_NAMES[text]
    key = text.lower()
    if key in _LANG_CODES:
        return _LANG_CODES[key]
    for name in LANGUAGE_FLAGS:
        if key == name.lower():
            return name
    return text.title() if len(text) <= 20 else ''


def infer_languages(sd, provider, media_meta):
    """Combine explicit provider languages, playlist audio tracks and hints."""
    found = []

    def add(name):
        if name and name not in found:
            found.append(name)

    for item in sd.get('languages') or []:
        if isinstance(item, (list, tuple)):
            for sub in item:
                add(_language_name(sub))
        else:
            # "Hindi, English" is common in provider JSON.
            for part in str(item).replace('/', ',').split(','):
                add(_language_name(part))

    for item in (media_meta or {}).get('languages') or []:
        add(_language_name(item))

    haystack = ' '.join(str(x or '') for x in (
        sd.get('name'), sd.get('label'), sd.get('title'),
    ))
    for name in LANGUAGE_FLAGS:
        if name == 'Multi Audio':
            continue
        if re.search(rf'(?<![a-z]){re.escape(name)}(?![a-z])', haystack, re.I):
            add(name)

    if not found:
        found = list(PROVIDER_LANGUAGES.get(provider, ()))

    return found[:4]


def subtitle_languages(subtitles):
    names = []
    for sub in subtitles or []:
        code = str((sub or {}).get('lang') or '')
        name = _LANG_CODES.get(code.lower()[:3]) or _LANG_CODES.get(code.lower()[:2])
        if name and name not in names:
            names.append(name)
    return names


# ------------------------------------------------------------------- probing

_ATTR_RE = re.compile(r'([A-Z0-9-]+)=("[^"]*"|[^,]*)')


def _attrs(line):
    out = {}
    _, _, rest = line.partition(':')
    for key, value in _ATTR_RE.findall(rest):
        out[key] = value.strip('"').strip()
    return out


def _resolution_to_quality(resolution):
    if not resolution:
        return ''
    m = re.search(r'(\d+)\s*x\s*(\d+)', resolution)
    if m:
        width, height = int(m.group(1)), int(m.group(2))
        # Portrait/vertical playlists: the smaller dimension is the "quality".
        height = min(width, height) if width and height else max(width, height)
        for known in (2160, 1440, 1080, 720, 576, 480, 360, 240):
            if abs(height - known) <= 24:
                return '4K' if known == 2160 else f'{known}p'
        return f'{height}p'
    m = re.search(r'(\d{3,4})p?', resolution)
    return f'{m.group(1)}p' if m else ''


def _codec_info(codecs):
    codecs = (codecs or '').lower()
    encode = ''
    audio = ''
    if 'avc1' in codecs or 'h264' in codecs:
        encode = 'H.264'
    elif 'hvc1' in codecs or 'hev1' in codecs or 'h265' in codecs:
        encode = 'H.265'
    elif 'av01' in codecs:
        encode = 'AV1'
    elif 'vp9' in codecs:
        encode = 'VP9'
    if 'mp4a' in codecs or 'aac' in codecs:
        audio = 'AAC'
    elif 'ec-3' in codecs or 'ac-3' in codecs:
        audio = 'DD+'
    elif 'opus' in codecs:
        audio = 'OPUS'
    elif 'flac' in codecs:
        audio = 'FLAC'
    return encode, audio


def _played_seconds(playlist):
    total = 0.0
    for line in playlist.splitlines():
        if line.startswith('#EXTINF:'):
            try:
                total += float(line.split(':', 1)[1].split(',', 1)[0])
            except ValueError:
                pass
    return total


def _bitrate_kbps(playlist):
    values = []
    for line in playlist.splitlines():
        if line.startswith('#EXT-X-BITRATE:'):
            try:
                values.append(float(line.split(':', 1)[1]))
            except ValueError:
                pass
    return (sum(values) / len(values) * 1000) if values else 0


def _merge_meta(master, media, meta):
    """Fill ``meta`` from a master playlist and (optionally) its variant."""
    variants = []
    pending = None
    for line in master.splitlines():
        line = line.strip()
        if line.startswith('#EXT-X-STREAM-INF:'):
            pending = _attrs(line)
        elif line.startswith('#EXT-X-I-FRAME-STREAM-INF:'):
            continue
        elif pending and line and not line.startswith('#'):
            variants.append(pending)
            pending = None
        elif line.startswith('#EXT-X-RESOLUTION:'):
            meta.setdefault('quality', _resolution_to_quality(line.split(':', 1)[1]))

    # Audio renditions (NAME/LANGUAGE) are the most reliable language source.
    languages = []
    for line in master.splitlines():
        if line.startswith('#EXT-X-MEDIA:') and 'TYPE=AUDIO' in line:
            attrs = _attrs(line)
            for key in ('LANGUAGE', 'NAME'):
                value = attrs.get(key, '')
                name = _LANG_CODES.get(value.lower()[:3]) or _LANG_CODES.get(value.lower()[:2])
                if not name and key == 'NAME':
                    name = _language_name(value)
                if name and name not in languages:
                    languages.append(name)
    if languages:
        meta['languages'] = languages

    if variants:
        best = max(variants, key=lambda v: int(v.get('BANDWIDTH') or 0))
        quality = _resolution_to_quality(best.get('RESOLUTION'))
        if quality:
            meta['quality'] = quality
        bandwidth = int(best.get('BANDWIDTH') or 0)
        if bandwidth:
            meta['bitrate'] = bandwidth
        encode, audio = _codec_info(best.get('CODECS'))
        if encode:
            meta['encode'] = encode
        if audio:
            meta['audio'] = audio
        framerate = best.get('FRAME-RATE')
        if framerate:
            meta['framerate'] = framerate

    if media:
        duration = _played_seconds(media)
        if duration:
            meta['duration'] = duration
        if not meta.get('bitrate'):
            meta['bitrate'] = _bitrate_kbps(media)

    bitrate = meta.get('bitrate') or 0
    duration = meta.get('duration') or 0
    if bitrate and duration and not meta.get('size'):
        meta['size'] = int(duration * bitrate / 8)


def _playlist_from_text(text):
    """True when the body is an HLS playlist rather than an HTML error page."""
    return '#EXTM3U' in text[:4096]


def probe_playlist(url, headers):
    """Inspect an HLS playlist and return quality/size/language metadata."""
    key = 'hls:' + url
    if key in _probe_cache:
        return dict(_probe_cache[key])
    meta = {}
    try:
        r = requests.get(url, headers=headers, timeout=8, verify=False)
        if r.status_code == 200 and _playlist_from_text(r.text):
            master = r.text
            media = master
            first = next((l.strip() for l in master.splitlines()
                          if l.strip() and not l.startswith('#')), None)
            if '#EXT-X-STREAM-INF' in master and first:
                variant_url = first if first.startswith('http') else url.rsplit('/', 1)[0] + '/' + first
                try:
                    rv = requests.get(variant_url, headers=headers, timeout=8, verify=False)
                    if rv.status_code == 200:
                        media = rv.text
                except Exception:
                    pass
            _merge_meta(master, media, meta)
    except Exception:
        pass
    _probe_cache[key] = dict(meta)
    return meta


def probe_direct(url, headers):
    """Return ``{'size': bytes, 'container': ext}`` for a direct media file."""
    key = 'file:' + url
    if key in _probe_cache:
        return dict(_probe_cache[key])
    path = urlparse(url).path.lower()
    ext = path.rsplit('.', 1)[-1] if '.' in path.rsplit('/', 1)[-1] else ''
    meta = {}
    if ext in ('mp4', 'mkv', 'webm', 'ts', 'm4s', 'avi', 'mov'):
        meta['container'] = ext
    try:
        h = {k: v for k, v in (headers or {}).items() if k.lower() != 'range'}
        r = requests.head(url, headers=h, timeout=6, verify=False, allow_redirects=True)
        length = r.headers.get('Content-Length')
        ctype = (r.headers.get('Content-Type') or '').lower()
        if r.status_code >= 400 or not (length or '').isdigit():
            h['Range'] = 'bytes=0-0'
            r = requests.get(url, headers=h, timeout=8, verify=False, stream=True)
            content_range = r.headers.get('Content-Range') or ''
            total = content_range.rsplit('/', 1)[-1]
            if total.isdigit():
                length = total
            r.close()
        if (length or '').isdigit() and int(length) > 0:
            meta['size'] = int(length)
        if not meta.get('container'):
            if 'mp4' in ctype:
                meta['container'] = 'mp4'
            elif 'mpegurl' in ctype:
                meta['container'] = 'm3u8'
    except Exception:
        pass
    _probe_cache[key] = dict(meta)
    return meta


# ------------------------------------------------------------------ labelling

_QUALITY_ORDER = ('4K', '2160p', '1440p', '1080p', '720p', '576p', '480p', '360p', '240p')


def _fmt_size(size):
    try:
        size = int(size)
    except (TypeError, ValueError):
        return ''
    if size <= 0:
        return ''
    units = ('B', 'KB', 'MB', 'GB', 'TB')
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f'{value:.0f} {unit}' if unit == 'B' else f'{value:.1f} {unit}'
        value /= 1024
    return ''


def _dot(text, limit=70):
    text = re.sub(r'[^0-9A-Za-z]+', '.', str(text or ''))
    text = re.sub(r'\.{2,}', '.', text).strip('.')
    return text[:limit]


def build_filename(title, content_type, season, episode, meta, languages, source_url=''):
    parts = []
    if title:
        parts.append(_dot(title))
    if content_type != 'movie' and season and episode:
        parts.append(f'S{int(season):02d}E{int(episode):02d}')
    quality = meta.get('quality') or 'Auto'
    parts.append(_dot(quality))
    parts.append(_dot(meta.get('quality_tag') or 'WEB-DL'))
    for lang in languages:
        if lang != 'Multi Audio':
            parts.append(_dot(lang))
    if meta.get('audio'):
        parts.append(_dot(meta['audio']))
    if meta.get('encode'):
        parts.append(_dot(meta['encode']))
    if meta.get('bitrate'):
        parts.append(f'{round(int(meta["bitrate"]) / 1000)}kbps')

    path = urlparse(source_url).path.lower()
    ext = path.rsplit('.', 1)[-1] if '.' in path.rsplit('/', 1)[-1] else ''
    if ext not in ('m3u8', 'mp4', 'mkv', 'webm', 'ts', 'm4s', 'avi', 'mov'):
        ext = 'm3u8' if meta.get('is_hls') else (meta.get('container') or 'mp4')

    return '.'.join(p for p in parts if p) + f'-AniBox.{ext}'


def _language_line(languages):
    labelled = []
    for lang in languages:
        flag = LANGUAGE_FLAGS.get(lang)
        labelled.append(f'{flag} {lang}' if flag else lang)
    return ' · '.join(labelled)


def format_stream(*, style, plain_title, provider_display, player_label,
                  quality, meta, languages, subtitles, title, content_type,
                  season, episode, source_url):
    """Return label/description/behaviorHints additions for one stream."""
    quality_tag = meta.get('quality_tag') or 'WEB-DL'
    encode = meta.get('encode') or ''
    audio = meta.get('audio') or ''
    bitrate = meta.get('bitrate') or 0
    size_text = _fmt_size(meta.get('size'))

    filename = build_filename(title, content_type, season, episode, meta,
                              languages, source_url)

    hints = {
        'notWebReady': False,
        'filename': filename,
        'indexer': provider_display,
    }
    if meta.get('size'):
        hints['videoSize'] = int(meta['size'])

    subs = subtitle_languages(subtitles)

    if style == 'plain':
        return {
            'name': plain_title,
            'title': plain_title,
            'behaviorHints': hints,
        }

    if style == 'compact':
        name = f'{provider_display} · {quality or "Auto"}'
        title_text = f'{player_label} · {quality or "Auto"}'
        return {
            'name': name,
            'title': title_text,
            'behaviorHints': hints,
        }

    name = f'AniBox · {quality or "Auto"}'
    lines = [
        f'\U0001F3AC {provider_display}',
        f'\U0001F4E1 {player_label}',
    ]
    video_bits = [b for b in (quality or 'Auto', quality_tag, encode) if b]
    lines.append('\U0001F4FA ' + ' · '.join(video_bits))
    if languages:
        lines.append('\U0001F3A7 ' + _language_line(languages))
    if audio or bitrate:
        audio_bits = []
        if audio:
            audio_bits.append(audio)
        if bitrate:
            audio_bits.append(f'{round(bitrate / 1000)} kbps')
        lines.append('\U0001F39B\uFE0F ' + ' · '.join(audio_bits))
    if size_text:
        lines.append(f'\U0001F4BE {size_text}')
    if subs:
        lines.append('\U0001F4AC Subs: ' + ', '.join(subs))
    if style == 'aiostreams':
        lines.append(f'\U0001F4E6 {filename}')
        lines.append('\U0001F3F7\uFE0F AniBox')

    description = '\n'.join(lines)
    return {
        'name': name,
        'title': description,
        'description': description,
        'behaviorHints': hints,
    }
