"""
Unified Player Extractor - all embed players used by Hindi dub anime sites.

Architecture: Each function takes an embed URL and returns {'streams': [...]} 
where each stream is {'player': str, 'url': str, 'name': str, 'languages': []}

Players covered:
  ✅ Bato/AnVod (direct m3u8)  ✅ Pahe/UwuCDN (direct m3u8)  
  ✅ ZephyrFlick (POST /player) ✅ GDMirrorBot (POST → base64 → sub-hosts)
  ✅ VidMoly (regex m3u8)      ✅ StreamRuby (POST /dl → unpack)
  ✅ DoodStream (pass_md5)      ✅ StreamTape (token + get_video)
  ✅ StreamP2P (AES-CBC API)    ✅ RPMStream/UPNShare (AES-CBC API)
  ✅ StreamHG (AES-CBC API)     ✅ VidRocks (packed JS sources)
  ✅ Vidsrc.xyz/wtf (XOR+RC4)   ✅ TurboVid (sources block)
  ✅ PirateXPlay (index11.php)  ✅ HSAStream (AES-CBC decrypt)
  ⚠️ Abyss (needs Playwright)   ⚠️ FlixCloud (JWT + CF)
"""
import re, json, base64, hashlib, secrets, os, requests, struct
from urllib.parse import urlparse
from bs4 import BeautifulSoup

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36'
TIMEOUT = 15

# ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎
# GLOBAL DISPATCHER
# ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎

PLAYER_MAP = {
    'gdmirrorbot.nl': 'gdmirrorbot', 'pro.iqsmartgames.com': 'gdmirrorbot',
    'vidmoly.org': 'vidmoly', 'vidmoly.net': 'vidmoly', 'vidmoly.biz': 'vidmoly',
    'streamruby.com': 'streamruby',
    'dood.li': 'doodstream', 'dood.to': 'doodstream', 'dood.ws': 'doodstream',
    'streamtape.site': 'streamtape', 'streamtape.com': 'streamtape',
    'p2pplay.pro': 'streamp2p', '.strp': 'streamp2p',
    'rpmstream.live': 'rpmstream', 'rpmstream.com': 'rpmstream',
    'rpmhub.site': 'rpmstream',
    'upns.live': 'upnshare', 'cloudy.upns': 'upnshare',
    'uns.bio': 'upnshare',
    'turbovidhls.com': 'turbovid', 'emturbovid.com': 'turbovid',
    'player.abyssplayer.com': 'abyss', 'play.abyssplayer.com': 'abyss',
    'flixcloud.cc': 'flixcloud',
    'megacloud.animanga.fun': 'megacloud', 'upcloud.animanga.fun': 'megacloud',
    'megacloud': 'megacloud', 'mewstream': 'megacloud',
    'play.zephyrix.top': 'zephyrflick', 'play.zephyrflick.top': 'zephyrflick',
    'as-cdn21.top': 'zephyrflick', 'as-cdn22.top': 'zephyrflick', 'as-cdn23.top': 'zephyrflick',
    'vidsrc.xyz': 'vidsrc', 'vidsrc.wtf': 'vidsrc', 'vidsrc.me': 'vidsrc',
    'moviesapi.club': 'moviesapi',
    'player.videasy.net': 'videasy',
    'playmogo.com': 'playmogo',
    'hanerix.com': 'streamhg', 'streamhg': 'streamhg',
    'smoothpre': 'streamhg', 'vidhide': 'streamhg',
    'filemoon': 'filemoon', 'bysetayico': 'filemoon',
    'af0': 'direct_m3u8', 'anvod': 'direct_m3u8',
    'vault-0': 'direct_m3u8', 'uwucdn': 'direct_m3u8',
    'cloud.desidubanime.me': 'cloud', '.upns': 'upnshare',
    'piratexplay.cc': 'piratexplay',
    'hsastream.com': 'hsastream',
}

def classify_url(url: str) -> str:
    """Auto-detect which player an embed URL belongs to"""
    url_lower = url.lower()
    for domain, player in PLAYER_MAP.items():
        if domain in url_lower:
            return player
    if '.m3u8' in url_lower: return 'direct_m3u8'
    return 'generic_embed'

def resolve_stream(stream_data: dict) -> list:
    """Universal stream resolver: classify -> extract -> return Stremio-format streams (ONLY direct URLs)"""
    player = stream_data.get('player', '')
    url = stream_data.get('url', '')
    name = stream_data.get('name', '')

    if not player and url:
        player = classify_url(url)
    if not url:
        return []

    extractor = EXTRACTORS.get(player)
    if not extractor:
        return []  # Unknown player - skip, don't return externalUrl

    try:
        result = extractor(url)
        return _flatten(result, name)
    except Exception as e:
        print(f'[extractor] {player} failed: {e}')
        return []


def _stremio_fmt(video_url=None, name='', external=None, subtitles=None):
    s = {'title': f'[{name}]', 'name': name, 'behaviorHints': {'notWebReady': True}}
    if video_url:
        s['url'] = video_url
    if external:
        s['externalUrl'] = external
    if subtitles:
        s['subtitles'] = subtitles
    return s

def _flatten(result, parent_name, max_streams=20):
    """Flatten extracted streams - ONLY return direct video URLs, no externalUrl"""
    streams = []
    for s in result.get('streams', [])[:max_streams]:
        if s.get('url'):
            streams.append(_stremio_fmt(s['url'], f"{parent_name}/{s.get('name','Stream')}",
                                        subtitles=s.get('subtitles')))
    return streams


# ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎
# DIRECT M3U8 (NO EXTRACTION NEEDED)
# ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎
def extract_direct_m3u8(url):
    return {'streams': [{'player': 'direct_m3u8', 'url': url, 'name': 'Direct'}]}

# ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎
# GDMIRRORBOT — POST → base64 decode mresult → construct sub-host URLs
# ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎
def extract_gdmirrorbot(url):
    sid = url.rstrip('/').split('/')[-1] if '/embed/' in url else url.split('#')[-1].split('?')[0]
    referer = f'https://gdmirrorbot.nl/embed/{sid}'

    resp = requests.post('https://pro.iqsmartgames.com/embedhelper2.php', headers={
        'User-Agent': UA, 'Content-Type': 'application/x-www-form-urlencoded',
        'Origin': 'https://gdmirrorbot.nl', 'Referer': referer,
    }, data={'sid': sid, 'UserFavSite': '', 'currentDomain': '[]'}, timeout=TIMEOUT)
    data = resp.json()

    if data.get('domain_blocked'):
        return {'streams': []}

    sources = data.get('sources', {})
    mresult_raw = data.get('mresult', '{}')
    mresult = json.loads(base64.b64decode(mresult_raw)) if isinstance(mresult_raw, str) else {}
    streams = []

    if isinstance(sources, list):
        sources = {s.get('key', str(i)): s for i, s in enumerate(sources) if isinstance(s, dict)}

    for key, cfg in sources.items():
        skey = mresult.get(key)
        if not skey: continue
        sub_url = cfg['siteUrl'] + skey + (cfg.get('embed_suffix') or '')
        player_type = classify_url(sub_url)

        # Try recursive extraction for known sub-hosts
        sub_extractor = EXTRACTORS.get(player_type)
        if sub_extractor and sub_extractor != extract_gdmirrorbot:
            try:
                result = sub_extractor(sub_url)
                for s in result.get('streams', []):
                    s['name'] = f"GDM/{cfg.get('friendlyName', key)}/{s.get('name','')}"
                    streams.append(s)
                continue
            except: pass

        streams.append({
            'player': player_type,
            'url': sub_url,
            'name': f"GDM/{cfg.get('friendlyName', key)}",
        })

    return {'streams': streams}

# ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎
# VIDMOLY — direct regex from JW Player inline config
# ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎
def extract_vidmoly(url):
    resp = requests.get(url, headers={'User-Agent': UA, 'Referer': url}, timeout=TIMEOUT)
    html = resp.text
    m3u8 = re.search(r"file:\s*'([^']*\.m3u8[^']*)'", html)
    if m3u8:
        return {'streams': [{'player': 'direct_m3u8', 'url': m3u8.group(1), 'name': 'VMoly'}]}
    file_match = re.search(r'file:\s*["\']([^"\']+)["\']', html)
    if file_match:
        return {'streams': [{'player': 'direct_m3u8', 'url': file_match.group(1), 'name': 'VMoly'}]}
    return {'streams': []}

# ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎
# FILEMOON — fetch page → unpack PACKER → file: m3u8
# ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎
def extract_filemoon(url):
    """Filemoon (classic hosts): fetch embed page, unpack PACKER, regex m3u8"""
    try:
        from app.players.streamruby import _unpack_packed
    except ImportError:
        try:
            from streamruby import _unpack_packed
        except ImportError:
            return {'streams': []}
    try:
        resp = requests.get(url, headers={'User-Agent': UA, 'Referer': url}, timeout=TIMEOUT)
        decoded = resp.text
        for sc in re.findall(r'<script[^>]*>(.*?)</script>', resp.text, re.S):
            if 'eval(function(p,a,c,k' in sc:
                decoded = _unpack_packed(sc)
                break
        m = re.search(r'file:\s*["\']([^"\']*?m3u8[^"\']*)["\']', decoded)
        if m:
            return {'streams': [{'player': 'direct_m3u8', 'url': m.group(1), 'name': 'Filemoon'}]}
        m2 = re.search(r'sources:\s*\[\s*\{\s*file:\s*["\']([^"\']+)["\']', decoded)
        if m2:
            return {'streams': [{'player': 'direct_m3u8', 'url': m2.group(1), 'name': 'Filemoon'}]}
    except Exception as e:
        print(f'[filemoon] error: {e}')
    return {'streams': []}

# ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎
# STREAMRUBY — POST /dl → unpack JS → regex m3u8
# ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎
def extract_streamruby(url):
    match = re.search(r'/e/(\w+)', url)
    if not match: return {'streams': []}
    fid = match.group(1)

    resp = requests.post('https://streamruby.com/dl', headers={
        'User-Agent': UA, 'Content-Type': 'application/x-www-form-urlencoded',
        'Referer': url,
    }, data={'op': 'embed', 'file_code': fid, 'auto': '1', 'referer': ''}, timeout=TIMEOUT)
    html = resp.text

    # Unpack PACKER JS
    packer = re.search(r"\}\('(.*?)',(\d+),(\d+),'([^']+)'\.split\('\|'\)", html)
    if packer:
        ps, radix, count, keys_str = packer.groups()
        keys = keys_str.split('|')
        try:
            html = re.sub(r'\b\w+\b', lambda w: keys[int(w.group(), int(radix))] if w.group().isalnum() and int(w.group(), int(radix)) < len(keys) else w.group(), ps)
        except: pass

    m3u8 = re.search(r'file:\s*"(https?://[^"]*\.m3u8[^"]*)"', html)
    if m3u8:
        return {'streams': [{'player': 'direct_m3u8', 'url': m3u8.group(1), 'name': 'StreamRuby'}]}

    sources = re.search(r'sources:\s*\[(.*?)\]', html, re.DOTALL)
    if sources:
        fm = re.search(r'file:\s*"([^"]+)"', sources.group(1))
        if fm:
            return {'streams': [{'player': 'direct_m3u8', 'url': fm.group(1), 'name': 'StreamRuby'}]}
    return {'streams': []}

# ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎
# DOODSTREAM — pass_md5 + download endpoint
# ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎
def extract_doodstream(url):
    resp = requests.get(url, headers={'User-Agent': UA}, timeout=TIMEOUT)
    html = resp.text
    base = '/'.join(url.split('/')[:3])

    # /download/ path
    dl = re.search(r"\$\.get\('(/download/[^']+)'", html)
    if dl:
        dr = requests.get(base + dl.group(1), headers={'Referer': url}, timeout=TIMEOUT)
        return {'streams': [{'player': 'direct_m3u8', 'url': dr.url, 'name': 'Dood'}]}

    # pass_md5 pattern
    pm = re.search(r"pass_md5[=:]\s*['\"]([^'\"]+)", html)
    if pm:
        pr = requests.get(f'{base}/pass_md5/{pm.group(1)}', headers={'Referer': url}, timeout=TIMEOUT)
        fm = re.search(r'(https?://[^\s\'\"<>]+\.(?:mp4|m3u8)[^\s\'\"<>]*)', pr.text)
        if fm:
            return {'streams': [{'player': 'direct_m3u8', 'url': fm.group(1), 'name': 'Dood'}]}

    # Direct file
    fm = re.search(r'file:\s*"([^"]+)"', html)
    if fm:
        return {'streams': [{'player': 'direct_m3u8', 'url': fm.group(1), 'name': 'Dood'}]}
    return {'streams': []}

# ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎
# STREAMTAPE — token + get_video endpoint
# ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎
def extract_streamtape(url):
    match = re.search(r'/e/([a-zA-Z0-9]+)', url)
    if not match: return {'streams': []}
    vid = match.group(1)
    base = '/'.join(url.split('/')[:3])

    resp = requests.get(f'{base}/e/{vid}', headers={'User-Agent': UA}, timeout=TIMEOUT)
    html = resp.text

    robotlink = re.search(r"robotlink\s*=\s*['\"]([^'\"]+)['\"]", html)
    token = re.search(r"token\s*=\s*['\"]([^'\"]+)['\"]", html)

    if robotlink and token:
        dl_url = robotlink.group(1) + '&token=' + token.group(1)
        return {'streams': [{'player': 'direct_m3u8', 'url': dl_url, 'name': 'StreamTape'}]}

    # Try /get_video POST
    try:
        cookies = resp.cookies.get_dict()
        dr = requests.post(f'{base}/get_video', data={'id': vid, 'stream': '1'},
                          headers={'User-Agent': UA, 'Referer': f'{base}/e/{vid}',
                                   'X-Requested-With': 'XMLHttpRequest'},
                          cookies=cookies, timeout=TIMEOUT)
        data = dr.json()
        if data.get('url'):
            return {'streams': [{'player': 'direct_m3u8', 'url': data['url'], 'name': 'StreamTape'}]}
    except: pass

    return {'streams': []}

# ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎
# TURBOVID — sources block
# ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎
def extract_turbovid(url):
    resp = requests.get(url, headers={'User-Agent': UA}, timeout=TIMEOUT)
    html = resp.text
    sources = re.search(r'sources:\s*\[(.*?)\]', html, re.DOTALL)
    if sources:
        fm = re.search(r'file:\s*["\']([^"\']+)["\']', sources.group(1))
        if fm: return {'streams': [{'player': 'direct_m3u8', 'url': fm.group(1), 'name': 'TurboVid'}]}
    # Base64 atob
    b64 = re.search(r"atob\(['\"]([^'\"]+)['\"]\s*\)", html)
    if b64:
        try:
            return {'streams': [{'player': 'direct_m3u8', 'url': base64.b64decode(b64.group(1)).decode(), 'name': 'TurboVid'}]}
        except: pass
    # API source
    idm = re.search(r'embed-([a-zA-Z0-9]+)', url)
    if idm:
        base = '/'.join(url.split('/')[:3])
        ar = requests.post(f'{base}/api/source/{idm.group(1)}', json={},
                          headers={'User-Agent': UA, 'Referer': url}, timeout=TIMEOUT)
        try:
            data = ar.json()
            for item in data.get('data', [data]):
                if item.get('file'):
                    return {'streams': [{'player': 'direct_m3u8', 'url': item['file'], 'name': 'TurboVid'}]}
        except: pass
    return {'streams': []}

# ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎
# STREAMP2P / RPMSHARE / UPNSHARE / STREAMHG (Vite+React+Vidstack AES-CBC)
# ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎

def _extract_p2p_family(url, api_host=None):
    """Shared extractor for RPMShare/UPNShare/StreamP2P/StreamHG (same Vite+React+Vidstack framework)"""
    parsed = urlparse(url)
    host = api_host or parsed.hostname
    video_id = parsed.fragment or url.split('#')[-1]
    if not video_id:
        return {'streams': []}

    s = requests.Session()
    s.headers.update({'User-Agent': UA, 'Accept': '*/*', 'Origin': f'https://{host}', 'Referer': url})

    results = []
    for ep in [f'/api/v1/video?id={video_id}&w=1920&h=1080&r={host}',
               f'/api/v1/player?t={video_id}',
               f'/api/v1/info?id={video_id}&w=1920&h=1080&r={host}']:
        try:
            r = s.get(f'https://{host}{ep}', timeout=TIMEOUT)
            if r.status_code != 200: continue
            try:
                data = r.json()
                stream = _extract_video_from_json(data)
                if stream:
                    results.append({'player': 'direct_m3u8', 'url': stream, 'name': host.split('.')[0]})
                    break
            except:
                # Try AES-CBC decryption
                try:
                    dec = _decrypt_aes_cbc(r.text, host)
                    stream = None
                    try:
                        data = json.loads(dec)
                        stream = _extract_video_from_json(data)
                    except Exception:
                        # First AES block may use an unknown IV (JSON head garbage);
                        # regex the stream URLs from the intact decrypted tail
                        # (same approach as extract_hsastream).
                        clean = dec.replace('\\/', '/')
                        for key in ('source', 'cfNative'):
                            mm = re.search(rf'"{key}"\s*:\s*"(https?://[^"]+)"', clean)
                            if mm and not (key == 'cfNative' and mm.group(1).endswith('.txt')):
                                stream = mm.group(1)
                                break
                    if stream:
                        results.append({'player': 'direct_m3u8', 'url': stream, 'name': host.split('.')[0]})
                        break
                except: pass
        except: pass

    return {'streams': results}

def _extract_video_from_json(data):
    for key in ['hls', 'cfStream', 'ggStream', 'ttStream', 'httpStream', 'source', 'cfNative',
                'url', 'file', 'src', 'videoSource']:
        val = data.get(key)
        if isinstance(val, dict): val = val.get('url') or val.get('src') or val.get('file')
        if isinstance(val, str) and val.startswith('http'):
            return val
    for key in ['streams', 'sources', 'video']:
        nested = data.get(key)
        if isinstance(nested, list) and nested:
            return nested[0].get('url') or nested[0].get('file') or nested[0].get('src')
        if isinstance(nested, dict):
            val = nested.get('url') or nested.get('file') or nested.get('src')
            if val and val.startswith('http'): return val
    return None

def _decrypt_aes_cbc(hex_data, host):
    """AES-128-CBC decrypt for P2P family players (key + fixed IVs, full
    payload is ciphertext — verified against live rpmhub responses)."""
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
    key = b'kiemtienmua911ca'
    raw = bytes.fromhex(re.sub(r'[^0-9a-fA-F]', '', hex_data.strip()))
    last_err = None
    for iv in (b'1234567890oiuytr', b'0123456789abcdef'):
        try:
            return unpad(AES.new(key, AES.MODE_CBC, iv).decrypt(raw), AES.block_size).decode()
        except Exception as e:
            last_err = e
    raise last_err or ValueError('AES decrypt failed')

def extract_streamp2p(url):
    return _extract_p2p_family(url)

def extract_rpmstream(url):
    return _extract_p2p_family(url)

def extract_upnshare(url):
    return _extract_p2p_family(url)

def extract_streamhg(url):
    """StreamHG: hanerix/smoothpre/vidhide serve a JW-PACKER page (no API) —
    decode it via the streamruby extractor first, fall back to the P2P API."""
    try:
        from app.players.streamruby import get_video_from_streamruby_player
    except ImportError:
        try:
            from streamruby import get_video_from_streamruby_player
        except ImportError:
            return _extract_p2p_family(url)
    try:
        vu, _, _ = get_video_from_streamruby_player(url)
        if vu and vu.startswith('http'):
            return {'streams': [{'player': 'direct_m3u8', 'url': vu, 'name': 'StreamHG'}]}
    except Exception:
        pass
    return _extract_p2p_family(url)

# ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎
# VIDSRC (XOR+RC4+B64 deobfuscation)
# ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎
def extract_vidsrc(url):
    """Extract from vidsrc.xyz/vidsrc.wtf embed. URL: /embed/movie/{id} or /embed/tv/{id}/{s}/{e}"""
    try:
        resp = requests.get(url, headers={'User-Agent': UA, 'Referer': url}, timeout=TIMEOUT)
        html = resp.text

        # Try JSON data-page
        page_match = re.search(r'data-page=["\']([^"\']+)["\']', html)
        if page_match:
            data = json.loads(page_match.group(1))
            file_url = data.get('file') or data.get('url')
            if file_url: return {'streams': [{'player': 'direct_m3u8', 'url': file_url, 'name': 'VidSrc'}]}

        # Try iframe → proversif pattern
        iframe = re.search(r'iframe.*?src=["\']([^"\']+)["\']', html)
        if iframe:
            iframe_url = iframe.group(1)
            if not iframe_url.startswith('http'):
                iframe_url = 'https:' + iframe_url if iframe_url.startswith('//') else 'https://' + iframe_url

            r2 = requests.get(iframe_url, headers={'User-Agent': UA, 'Referer': url}, timeout=TIMEOUT)
            data_i = re.search(r'data-i=["\'](\d+)["\']', r2.text)
            data_h = re.search(r'data-h=["\']([^"\']+)["\']', r2.text)
            if data_i and data_h:
                srcrcp = _deobfstr(data_h.group(1), data_i.group(1))
                if not srcrcp.startswith('http'):
                    srcrcp = 'https:' + srcrcp if srcrcp.startswith('//') else f'https://{srcrcp}'

                r3 = requests.get(srcrcp, headers={'User-Agent': UA, 'Referer': iframe_url}, timeout=TIMEOUT)
                file_match = re.search(r'Playerjs.*?file:\s*"#9([^"]*)"', r3.text)
                if file_match:
                    encoded = re.sub(r'/@#@\S+?=?=', '', file_match.group(1))
                    try:
                        video_url = base64.b64decode(encoded).decode()
                        return {'streams': [{'player': 'direct_m3u8', 'url': video_url, 'name': 'VidSrc'}]}
                    except: pass
    except: pass
    return {'streams': []}

def _deobfstr(hash_str, index_str):
    result = ''
    for i in range(0, len(hash_str), 2):
        j = hash_str[i:i+2]
        result += chr(int(j, 16) ^ ord(index_str[(i//2) % len(index_str)]))
    return result

# ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎
# VIDROCKS (Ridoo-based packed JS)
# ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎
def extract_vidrocks(url):
    resp = requests.get(url, headers={'User-Agent': UA}, timeout=TIMEOUT)
    html = resp.text

    # Sources block
    src = re.search(r'sources:\s*\[(.*?)\]', html, re.DOTALL)
    if src:
        files = re.findall(r'file:\s*["\']([^"\']+)["\']', src.group(1))
        streams = [{'player': 'direct_m3u8', 'url': f, 'name': f'VidRocks Q{len(streams)+1}'} for f in files]
        if streams: return {'streams': streams}

    # Direct m3u8/mp4
    for pattern in [r'(https?://[^\s\"\'<>]+\.m3u8[^\s\"\'<>]*)', r'(https?://[^\s\"\'<>]+\.mp4[^\s\"\'<>]*)']:
        matches = re.findall(pattern, html)
        if matches: return {'streams': [{'player': 'direct_m3u8', 'url': matches[0], 'name': 'VidRocks'}]}

    return {'streams': []}

# ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎
# ZEPHYRFLICK — POST /player/index.php?data={id}&do=getVideo
# ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎
ZEPHYR_BASE = os.getenv('ZEPHYR_PLAYER_BASE', 'https://play.zephyrix.top').rstrip('/')

def extract_zephyrflick(url):
    match = re.search(r'/video/([a-f0-9]+)', url)
    if not match:
        return {'streams': []}
    video_id = match.group(1)

    # Use the actual host from the URL (handles zephyrix.top, zephyrflick.top, as-cdn domains)
    parsed = urlparse(url)
    player_base = f'{parsed.scheme}://{parsed.hostname}'

    for base in [player_base, ZEPHYR_BASE]:
        try:
            resp = requests.post(f'{base}/player/index.php',
                                params={'data': video_id, 'do': 'getVideo'},
                                headers={'User-Agent': UA, 'X-Requested-With': 'XMLHttpRequest', 'Referer': url},
                                timeout=30)
            resp.raise_for_status()
            data = resp.json()
            video_url = data.get('videoSource')
            if video_url:
                subtitles = []
                try:
                    pr = requests.get(url, headers={'User-Agent': UA}, timeout=TIMEOUT)
                    s_match = re.search(r'var playerjsSubtitle = "([^"]+)"', pr.text)
                    if s_match:
                        for line in s_match.group(1).split('\n'):
                            sl = re.match(r'\[([^\]]+)\](.+)', line.strip())
                            if sl:
                                lang_code = 'eng' if 'english' in sl.group(1).lower() else sl.group(1).lower()[:3]
                                subtitles.append({'id': f'{video_id}_{lang_code}', 'url': sl.group(2), 'lang': lang_code})
                except: pass
                return {'streams': [{'player': 'direct_m3u8', 'url': video_url, 'name': 'Zephyr',
                                    'subtitles': subtitles}]}
        except Exception as e:
            print(f'[zephyr] {base}: {e}')
    return {'streams': []}

# ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎
# MOVIESAPI, VIDEASY, PLAYMOGO, ABYSS, FLIXCLOUD (stubs/embeds)
# ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎

def extract_moviesapi(url):
    """MoviesAPI.club - try to fetch actual video URL from API"""
    try:
        # MoviesAPI usually proxies to other players. Try to extract.
        resp = requests.get(url, headers={'User-Agent': UA}, timeout=TIMEOUT)
        html = resp.text
        # Look for redirect or embedded player
        m3u8 = re.search(r'(https?://[^\s\"\'<>]+\.m3u8[^\s\"\'<>]*)', html)
        if m3u8:
            return {'streams': [{'player': 'direct_m3u8', 'url': m3u8.group(1), 'name': 'MoviesAPI'}]}
        # Try iframe
        iframe = re.search(r'iframe[^>]*src=["\']([^"\']+)["\']', html)
        if iframe:
            sub_player = classify_url(iframe.group(1))
            sub_ex = EXTRACTORS.get(sub_player)
            if sub_ex and sub_ex != extract_moviesapi:
                try:
                    result = sub_ex(iframe.group(1))
                    return result
                except: pass
    except: pass
    return {'streams': []}


def extract_videasy(url):
    """Videasy - try Next.js API extraction"""
    try:
        resp = requests.get(url, headers={'User-Agent': UA}, timeout=TIMEOUT)
        html = resp.text
        # Next.js __NEXT_DATA__ extraction
        nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html)
        if nd:
            data = json.loads(nd.group(1))
            props = data.get('props', {}).get('pageProps', {})
            for key in ['sources', 'streams', 'video', 'file', 'url']:
                val = props.get(key)
                if isinstance(val, list) and val:
                    v = val[0].get('url') or val[0].get('file') or val[0]
                    if isinstance(v, str) and 'http' in v:
                        return {'streams': [{'player': 'direct_m3u8', 'url': v, 'name': 'Videasy'}]}
                if isinstance(val, str) and 'http' in val:
                    return {'streams': [{'player': 'direct_m3u8', 'url': val, 'name': 'Videasy'}]}
        # Generic extraction
        m3u8 = re.findall(r'(https?://[^\s\"\'<>]+\.m3u8[^\s\"\'<>]*)', html)
        mp4 = re.findall(r'(https?://[^\s\"\'<>]+\.mp4[^\s\"\'<>]*)', html)
        for v in m3u8 + mp4:
            return {'streams': [{'player': 'direct_m3u8', 'url': v, 'name': 'Videasy'}]}
    except: pass
    return {'streams': []}


def extract_playmogo(url):
    """PlayMogo - try extraction from embed page"""
    try:
        resp = requests.get(url, headers={'User-Agent': UA}, timeout=TIMEOUT)
        html = resp.text
        # Sources block
        src = re.search(r'sources:\s*\[(.*?)\]', html, re.DOTALL)
        if src:
            fm = re.search(r'file:\s*["\']([^"\']+)["\']', src.group(1))
            if fm: return {'streams': [{'player': 'direct_m3u8', 'url': fm.group(1), 'name': 'PlayMogo'}]}
        # Direct m3u8
        m3u8 = re.search(r'(https?://[^\s\"\'<>]+\.m3u8[^\s\"\'<>]*)', html)
        if m3u8: return {'streams': [{'player': 'direct_m3u8', 'url': m3u8.group(1), 'name': 'PlayMogo'}]}
    except: pass
    return {'streams': []}

def extract_abyss(url):
    """Abyss Player - try extraction via iframe/resolve. Falls back to empty if encrypted."""
    try:
        resp = requests.get(url, headers={'User-Agent': UA}, timeout=TIMEOUT)
        html = resp.text
        # Try to find m3u8/mp4 in the page
        m3u8 = re.search(r'(https?://[^\s\"\'<>]+\.m3u8[^\s\"\'<>]*)', html)
        if m3u8: return {'streams': [{'player': 'direct_m3u8', 'url': m3u8.group(1), 'name': 'Abyss'}]}
        # Check for base64 encoded config
        datas = re.search(r'const datas = "([^"]+)"', html)
        if datas:
            try:
                config = json.loads(base64.b64decode(datas.group(1)))
                # Check if media is already in the config
                if isinstance(config.get('media'), str) and 'http' in config['media']:
                    return {'streams': [{'player': 'direct_m3u8', 'url': config['media'], 'name': 'Abyss'}]}
            except: pass
        # Try iframe redirect
        iframe = re.search(r'iframe[^>]*src=["\']([^"\']+)["\']', html)
        if iframe:
            sub_player = classify_url(iframe.group(1))
            sub_ex = EXTRACTORS.get(sub_player)
            if sub_ex and sub_ex != extract_abyss:
                try: return sub_ex(iframe.group(1))
                except: pass
    except: pass
    return {'streams': []}


def extract_flixcloud(url):
    """FlixCloud - try cloudscraper extraction. Falls back to empty."""
    try:
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(url)
        hash_id = parsed.path.split('/e/')[-1] if '/e/' in parsed.path else None
        v = parse_qs(parsed.query).get('v', ['1'])[0] if parsed.query else '1'
        if not hash_id: return {'streams': []}
        # Try the API endpoint
        api = f'https://flixcloud.cc/api/m3u8/{hash_id}'
        resp = requests.get(api, headers={'User-Agent': UA, 'Referer': url}, timeout=TIMEOUT)
        if resp.status_code == 200:
            try:
                data = resp.json()
                m3u8_url = data.get('url') or data.get('file') or data.get('src')
                if m3u8_url: return {'streams': [{'player': 'direct_m3u8', 'url': m3u8_url, 'name': 'FlixCloud'}]}
            except: pass
        # Try alternate API with v param
        api2 = f'https://flixcloud.cc/player/{hash_id}?v={v}'
        resp2 = requests.get(api2, headers={'User-Agent': UA, 'Referer': url}, timeout=TIMEOUT)
        m3u8 = re.search(r'(https?://[^\s\"\'<>]+\.m3u8[^\s\"\'<>]*)', resp2.text)
        if m3u8: return {'streams': [{'player': 'direct_m3u8', 'url': m3u8.group(1), 'name': 'FlixCloud'}]}
    except: pass
    return {'streams': []}


# ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎
# MEGACLOUD / MEWSTREAM — proxy endpoint → m3u8 from cdn.mewstream.buzz
# ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎
def extract_megacloud(url):
    """MegaCloud/MewStream - used by aniflix.us. Proxy endpoint returns m3u8."""
    try:
        resp = requests.get(url, headers={'User-Agent': UA, 'Referer': url}, timeout=TIMEOUT)
        html = resp.text

        # Try to find m3u8 directly in page
        m3u8 = re.search(r'(https?://cdn\.mewstream\.buzz[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html)
        if m3u8:
            return {'streams': [{'player': 'direct_m3u8', 'url': m3u8.group(1), 'name': 'MegaCloud'}]}

        # Try ArtPlayer config
        art_config = re.search(r'art\s*=\s*new\s+Artplayer\s*\(\s*(\{.*?\})\s*\)', html, re.DOTALL)
        if art_config:
            config_text = art_config.group(1)
            url_match = re.search(r'url\s*:\s*["\']([^"\']+)["\']', config_text)
            if url_match:
                video_url = url_match.group(1)
                if 'mewstream' in video_url or '.m3u8' in video_url:
                    return {'streams': [{'player': 'direct_m3u8', 'url': video_url, 'name': 'MegaCloud'}]}

        # Try to find proxy URL pattern: /proxy?url={cdn_url}&headers={json}
        proxy_match = re.search(r'/proxy\?url=([^&"\']+)', html)
        if proxy_match:
            from urllib.parse import unquote
            cdn_url = unquote(proxy_match.group(1))
            if 'mewstream' in cdn_url or '.m3u8' in cdn_url:
                return {'streams': [{'player': 'direct_m3u8', 'url': cdn_url, 'name': 'MegaCloud'}]}

        # Generic m3u8 extraction
        m3u8_any = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html)
        if m3u8_any:
            return {'streams': [{'player': 'direct_m3u8', 'url': m3u8_any.group(1), 'name': 'MegaCloud'}]}

        # Try iframe redirect
        iframe = re.search(r'iframe[^>]*src=["\']([^"\']+)["\']', html)
        if iframe:
            sub_player = classify_url(iframe.group(1))
            sub_ex = EXTRACTORS.get(sub_player)
            if sub_ex and sub_ex != extract_megacloud:
                try:
                    return sub_ex(iframe.group(1))
                except: pass
    except Exception as e:
        print(f'[megacloud] error: {e}')
    return {'streams': []}


def extract_cloud_desidub(url):
    """CLOUD player (cloud.desidubanime.me) - follow redirect chain to get direct URL"""
    try:
        resp = requests.get(url, headers={'User-Agent': UA}, timeout=TIMEOUT, allow_redirects=True)
        html = resp.text
        # Look for redirect patterns
        redirect_url = re.search(r"url\s*=\s*['\"]([^'\"]+)['\"]", html)
        if redirect_url:
            r2 = requests.get(redirect_url.group(1), headers={'User-Agent': UA}, timeout=TIMEOUT, allow_redirects=True)
            m3u8 = re.search(r'(https?://[^\s\"\'<>]+\.m3u8[^\s\"\'<>]*)', r2.text)
            if m3u8: return {'streams': [{'player': 'direct_m3u8', 'url': m3u8.group(1), 'name': 'CLOUD'}]}
            return {'streams': [{'player': 'direct_m3u8', 'url': r2.url, 'name': 'CLOUD'}]}
        # Direct m3u8 in page
        m3u8 = re.search(r'(https?://[^\s\"\'<>]+\.m3u8[^\s\"\'<>]*)', html)
        if m3u8: return {'streams': [{'player': 'direct_m3u8', 'url': m3u8.group(1), 'name': 'CLOUD'}]}
    except: pass
    return {'streams': []}


def extract_piratexplay(url):
    """PirateXPlay - /public/player/index11.php?id={id} pattern"""
    try:
        parsed = urlparse(url)
        vid_id = None
        if 'id=' in url:
            vid_id = parsed.query.split('id=')[-1].split('&')[0]
        elif '/e/' in url:
            vid_id = url.split('/e/')[-1].split('?')[0].split('#')[0]
        if not vid_id:
            return {'streams': []}

        resp = requests.get(url, headers={'User-Agent': UA, 'Referer': url}, timeout=TIMEOUT)
        html = resp.text

        # Direct m3u8 in page
        m3u8 = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html)
        if m3u8:
            return {'streams': [{'player': 'direct_m3u8', 'url': m3u8.group(1), 'name': 'PirateX'}]}

        # Sources block
        src = re.search(r'sources:\s*\[(.*?)\]', html, re.DOTALL)
        if src:
            fm = re.search(r'file:\s*["\']([^"\']+)["\']', src.group(1))
            if fm:
                return {'streams': [{'player': 'direct_m3u8', 'url': fm.group(1), 'name': 'PirateX'}]}

        # file: or src: patterns
        for pattern in [r'file\s*[=:]\s*["\']([^"\']+)["\']', r'src\s*[=:]\s*["\']([^"\']+\.m3u8[^"\']*)["\']']:
            match = re.search(pattern, html)
            if match and 'http' in match.group(1):
                return {'streams': [{'player': 'direct_m3u8', 'url': match.group(1), 'name': 'PirateX'}]}

        # Try /public/player/ API with id
        base = f'{parsed.scheme}://{parsed.hostname}'
        api_url = f'{base}/public/player/index11.php?id={vid_id}'
        if api_url != url:
            r2 = requests.get(api_url, headers={'User-Agent': UA, 'Referer': url}, timeout=TIMEOUT)
            m3u8_2 = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', r2.text)
            if m3u8_2:
                return {'streams': [{'player': 'direct_m3u8', 'url': m3u8_2.group(1), 'name': 'PirateX'}]}

        # Iframe redirect
        iframe = re.search(r'iframe[^>]*src=["\']([^"\']+)["\']', html)
        if iframe:
            sub_player = classify_url(iframe.group(1))
            sub_ex = EXTRACTORS.get(sub_player)
            if sub_ex and sub_ex != extract_piratexplay:
                try:
                    return sub_ex(iframe.group(1))
                except:
                    pass
    except Exception as e:
        print(f'[piratexplay] error: {e}')
    return {'streams': []}


# ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎
# HSASTREAM — AES-128-CBC decrypt API responses → m3u8 streams
# ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎
HSASTREAM_KEY = b'kiemtienmua911ca'

def _hsastream_derive_iv(video_id):
    """Derive 16-byte AES IV from video_id using hsastream's algorithm"""
    o = "https:"
    d = o + "//"
    T = len(o) * len(d)
    C = ""
    for Z in range(1, 10):
        C += chr(Z + T)
    H = 3 * (ord(video_id[0]) if video_id else 0)
    le = 111 + len(o)
    L = le + 4
    X = ord(o[1])
    te = X - 2
    C += chr(T) + chr(111) + chr(H) + chr(le) + chr(L) + chr(X) + chr(te)
    return C.encode('utf-8')[:16]

def _hsastream_decrypt(hex_data, video_id):
    """AES-128-CBC decrypt hsastream API response, return full text"""
    from Crypto.Cipher import AES
    iv = _hsastream_derive_iv(video_id)
    cleaned = re.sub(r'[^0-9a-fA-F]', '', hex_data)
    cipher = AES.new(HSASTREAM_KEY, AES.MODE_CBC, iv)
    decrypted = cipher.decrypt(bytes.fromhex(cleaned))
    return decrypted.decode('utf-8', errors='ignore')

def extract_hsastream(url):
    """HSAStream - AES-128-CBC encrypted API → m3u8 streams"""
    try:
        # Extract video_id from URL (format: https://hsastream.com/#VIDEO_ID or /e/VIDEO_ID)
        video_id = None
        if '#' in url:
            video_id = url.split('#')[-1].split('?')[0]
        elif '/e/' in url:
            video_id = url.split('/e/')[-1].split('?')[0].split('/')[0]
        elif 'id=' in url:
            from urllib.parse import parse_qs
            parsed_q = urlparse(url)
            video_id = parse_qs(parsed_q.query).get('id', [None])[0]
        if not video_id:
            return {'streams': []}

        referer = url
        parsed_url = urlparse(url)
        if parsed_url.hostname:
            referer = f'{parsed_url.scheme}://{parsed_url.hostname}/'

        # Fetch encrypted video data
        resp = requests.get(
            f'https://hsastream.com/api/v1/video?id={video_id}&w=360&h=800&r={parsed_url.hostname or "animevilla.org"}',
            headers={'User-Agent': UA, 'Referer': referer},
            timeout=TIMEOUT
        )
        if resp.status_code != 200 or not resp.text.strip():
            return {'streams': []}

        # Decrypt - the response has escaped JSON with \/ for /
        decrypted = _hsastream_decrypt(resp.text.strip(), video_id)
        # Unescape JSON string escapes
        decrypted_clean = decrypted.replace('\\/', '/')

        streams = []
        for key, name in [('source', 'Google'), ('cfNative', 'Cloudflare'), ('cf', 'CF')]:
            match = re.search(rf'"{key}"\s*:\s*"(https?://[^"]+)"', decrypted_clean)
            if match:
                url = match.group(1)
                if key == 'cf' and url.endswith('.txt'):
                    continue
                streams.append({'player': 'direct_m3u8', 'url': url, 'name': f'HSA/{name}'})

        hls_match = re.search(r'"hlsVideoTiktok"\s*:\s*"([^"]+)"', decrypted_clean)
        if hls_match:
            url = hls_match.group(1)
            if url.startswith('/'):
                url = f'https://hsastream.com{url}'
            if url.startswith('http'):
                streams.append({'player': 'direct_m3u8', 'url': url, 'name': 'HSA/TikTok'})

        return {'streams': streams}
    except Exception as e:
        print(f'[hsastream] error: {e}')
        return {'streams': []}


# ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎
# GENERIC EMBED — try to extract m3u8 from any embed page
# ∎∎∎∎∎∎∎∎ ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎
def extract_generic_embed(url):
    """Last resort: fetch embed page and look for m3u8/mp4 URLs"""
    try:
        resp = requests.get(url, headers={
            'User-Agent': UA,
            'Referer': url,
            'Accept': 'text/html,application/xhtml+xml',
        }, timeout=TIMEOUT)
        html = resp.text

        m3u8s = re.findall(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html)
        if m3u8s:
            return {'streams': [{'player': 'direct_m3u8', 'url': m3u8s[0], 'name': 'Generic/Direct'}]}

        mp4s = re.findall(r'(https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*)', html)
        if mp4s:
            return {'streams': [{'player': 'direct_m3u8', 'url': mp4s[0], 'name': 'Generic/Direct'}]}

        iframe = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', html)
        if iframe:
            iframe_url = iframe.group(1)
            if iframe_url.startswith('//'):
                iframe_url = 'https:' + iframe_url
            player = classify_url(iframe_url)
            extractor = EXTRACTORS.get(player)
            if extractor and extractor != extract_generic_embed:
                return extractor(iframe_url)

    except Exception as e:
        print(f'[generic_embed] error: {e}')
    return {'streams': []}


# ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎
# REGISTRY
# ∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎∎

EXTRACTORS = {
    'direct_m3u8': extract_direct_m3u8,
    'generic_embed': extract_generic_embed,
    'gdmirrorbot': extract_gdmirrorbot,
    'vidmoly': extract_vidmoly,
    'filemoon': extract_filemoon,
    'streamruby': extract_streamruby,
    'doodstream': extract_doodstream,
    'streamtape': extract_streamtape,
    'turbovid': extract_turbovid,
    'streamp2p': extract_streamp2p,
    'rpmstream': extract_rpmstream,
    'rpmshare': extract_rpmstream,
    'upnshare': extract_upnshare,
    'streamhg': extract_streamhg,
    'vidsrc': extract_vidsrc,
    'vidrocks': extract_vidrocks,
    'zephyrflick': extract_zephyrflick,
    'moviesapi': extract_moviesapi,
    'videasy': extract_videasy,
    'playmogo': extract_playmogo,
    'abyss': extract_abyss,
    'flixcloud': extract_flixcloud,
    'megacloud': extract_megacloud,
    'cloud': extract_cloud_desidub,
    'piratexplay': extract_piratexplay,
    'hsastream': extract_hsastream,
}

PLAYER_NAMES = {
    'gdmirrorbot': 'GD MirrorBot', 'vidmoly': 'VidMoly', 'filemoon': 'Filemoon', 'streamruby': 'StreamRuby',
    'doodstream': 'DoodStream', 'streamtape': 'StreamTape', 'turbovid': 'TurboVid',
    'streamp2p': 'StreamP2P', 'rpmstream': 'RPMShare', 'upnshare': 'UPNShare',
    'streamhg': 'StreamHG', 'vidsrc': 'VidSrc', 'vidrocks': 'VidRocks',
    'zephyrflick': 'ZephyrFlick', 'moviesapi': 'MoviesAPI', 'videasy': 'Videasy',
    'playmogo': 'PlayMogo', 'abyss': 'Abyss Player', 'flixcloud': 'FlixCloud',
    'megacloud': 'MegaCloud', 'direct_m3u8': 'Direct Stream',
    'piratexplay': 'PirateXPlay', 'hsastream': 'HSAStream',
}
