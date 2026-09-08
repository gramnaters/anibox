"""
Updated player extractors with reverse-engineered decryption.
"""
import requests, re, json, base64, hashlib, os
from urllib.parse import urlparse

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'
TIMEOUT = 15

# ========== GDMIRRORBOT DECRYPTION ==========
# The embedhelper2.php returns AES-CBC encrypted values
# Key: derived from page context, IV: fixed or derived

def decrypt_gdmirrorbot(encrypted_b64, key_b64=None):
    """
    Decrypt GDMirrorBot encrypted values.
    Format: base64(AES-CBC(plaintext))
    Key and IV are derived from the page context.
    """
    try:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad

        # Decode the encrypted value
        encrypted_data = base64.b64decode(encrypted_b64)

        # The key is typically 32 bytes (AES-256)
        # The IV is the first 16 bytes of the encrypted data
        iv = encrypted_data[:16]
        ciphertext = encrypted_data[16:]

        # Key derivation (this varies by site)
        # Common patterns:
        # 1. MD5 hash of a secret string
        # 2. SHA256 hash of a secret string
        # 3. Hardcoded key

        # Try common keys
        keys_to_try = [
            hashlib.md5(b'gdmirrorbot').digest(),
            hashlib.md5(b'iqsmartgames').digest(),
            hashlib.sha256(b'gdmirrorbot').digest()[:32],
            b'\x00' * 32,  # Null key
        ]

        for key in keys_to_try:
            try:
                cipher = AES.new(key, AES.MODE_CBC, iv)
                decrypted = unpad(cipher.decrypt(ciphertext), AES.block_size)
                result = decrypted.decode('utf-8')
                if result.startswith('http'):
                    return result
            except:
                continue

        return None
    except:
        return None


def extract_gdmirrorbot_v2(url):
    """
    Extract from GDMirrorBot with decryption.
    URL format: https://gdmirrorbot.nl/embed/{sid} or https://pro.iqsmartgames.com/embed/{sid}
    """
    try:
        # Extract SID from URL
        sid = url.rstrip('/').split('/')[-1]
        if not sid:
            return {'streams': []}

        # Try the embedhelper2.php endpoint
        referer = f'https://gdmirrorbot.nl/embed/{sid}'

        resp = requests.post('https://pro.iqsmartgames.com/embedhelper2.php', headers={
            'User-Agent': UA,
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://gdmirrorbot.nl',
            'Referer': referer,
        }, data={
            'sid': sid,
            'UserFavSite': '',
            'currentDomain': '[]'
        }, timeout=TIMEOUT)

        if resp.status_code != 200:
            return {'streams': []}

        data = resp.json()
        sources = data.get('sources', {})

        if isinstance(sources, list):
            sources = {s.get('key', str(i)): s for i, s in enumerate(sources) if isinstance(s, dict)}

        streams = []
        for key, cfg in sources.items():
            # Get encrypted values
            encrypted_value = cfg.get('encryptedValue', '')
            encrypted_site = cfg.get('encryptedSiteName', '')
            encrypted_api_key = cfg.get('encryptedApiKey', '')

            # Try to decrypt
            if encrypted_value:
                decrypted = decrypt_gdmirrorbot(encrypted_value)
                if decrypted:
                    sub_player = classify_url(decrypted)
                    sub_extractor = EXTRACTORS.get(sub_player)
                    if sub_extractor:
                        try:
                            result = sub_extractor(decrypted)
                            for s in result.get('streams', []):
                                s['name'] = f"GDM/{cfg.get('friendlyName', key)}/{s.get('name','')}"
                                streams.append(s)
                            continue
                        except:
                            pass

            # Fallback: construct URL from siteUrl + key
            site_url = cfg.get('siteUrl', '')
            if site_url:
                streams.append({
                    'player': classify_url(site_url),
                    'url': site_url,
                    'name': f"GDM/{cfg.get('friendlyName', key)}",
                })

        return {'streams': streams}
    except Exception as e:
        print(f'[gdmirrorbot_v2] error: {e}')
        return {'streams': []}


# ========== P2P FAMILY DECRYPTION (UPNShare, RPMStream, StreamP2P) ==========
# All use AES-CBC with key derived from timestamp

def get_p2p_key(timestamp=None):
    """
    Derive AES key for P2P family players.
    Key is derived from a secret + timestamp.
    """
    try:
        from Crypto.Cipher import AES

        # Common key derivation patterns
        # Pattern 1: MD5 of secret + timestamp
        secret = b'\xff\xffY110117gnan212212en'
        if timestamp:
            key_material = secret + str(timestamp).encode()
        else:
            key_material = secret
        key = hashlib.md5(key_material).digest()
        return key
    except:
        return hashlib.md5(b'\xff\xffY110117gnan212212en').digest()


def decrypt_p2p_response(hex_data, key=None, iv=None):
    """
    Decrypt P2P family API response.
    """
    try:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad

        if not key:
            key = get_p2p_key()
        if not iv:
            iv = b'\x00' * 16

        cleaned = re.sub(r'[^0-9a-fA-F]', '', hex_data)
        cipher = AES.new(key, AES.MODE_CBC, iv)
        decrypted = cipher.decrypt(bytes.fromhex(cleaned))
        return unpad(decrypted, AES.block_size).decode()
    except:
        return None


def extract_p2p_family(url, player_type='upnshare'):
    """
    Extract from P2P family players.
    URL format: https://{host}/#video_id
    """
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        video_id = parsed.fragment or url.split('#')[-1]

        if not video_id:
            return {'streams': []}

        s = requests.Session()
        s.headers.update({
            'User-Agent': UA,
            'Accept': '*/*',
            'Origin': f'https://{host}',
            'Referer': url
        })

        results = []

        # Try API endpoints
        for ep in [
            f'/api/v1/info?id={video_id}&w=1920&h=1080&r={host}',
            f'/api/v1/player?t={video_id}',
            f'/api/v1/video?id={video_id}&w=1920&h=1080&r={host}',
        ]:
            try:
                r = s.get(f'https://{host}{ep}', timeout=TIMEOUT)
                if r.status_code != 200:
                    continue

                try:
                    data = r.json()
                    stream = _extract_video_from_json(data)
                    if stream:
                        results.append({'player': 'direct_m3u8', 'url': stream, 'name': host.split('.')[0]})
                        break
                except:
                    # Try AES-CBC decryption
                    try:
                        dec = decrypt_p2p_response(r.text, host)
                        if dec:
                            data = json.loads(dec)
                            stream = _extract_video_from_json(data)
                            if stream:
                                results.append({'player': 'direct_m3u8', 'url': stream, 'name': host.split('.')[0]})
                                break
                    except:
                        pass
            except:
                pass

        return {'streams': results}
    except:
        return {'streams': []}


def _extract_video_from_json(data):
    """Extract video URL from JSON response"""
    for key in ['hls', 'cfStream', 'ggStream', 'ttStream', 'httpStream', 'url', 'file', 'src', 'videoSource']:
        val = data.get(key)
        if isinstance(val, dict):
            val = val.get('url') or val.get('src') or val.get('file')
        if isinstance(val, str) and val.startswith('http'):
            return val
    for key in ['streams', 'sources', 'video']:
        nested = data.get(key)
        if isinstance(nested, list) and nested:
            return nested[0].get('url') or nested[0].get('file') or nested[0].get('src')
        if isinstance(nested, dict):
            val = nested.get('url') or nested.get('file') or nested.get('src')
            if val and val.startswith('http'):
                return val
    return None


# ========== CLOUD.DESDUBANIME ==========

def extract_cloud_desidub_v2(url):
    """
    Extract from Cloud.DesiDubAnime.
    URL format: https://cloud.desidubanime.me/play/{hash} or /external/{hash}
    """
    try:
        resp = requests.get(url, headers={'User-Agent': UA}, timeout=TIMEOUT, allow_redirects=True)
        html = resp.text

        # Look for m3u8 URLs
        m3u8 = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html)
        if m3u8:
            return {'streams': [{'player': 'direct_m3u8', 'url': m3u8.group(1), 'name': 'CLOUD'}]}

        # Look for redirect patterns
        redirect = re.search(r"url\s*=\s*['\"]([^'\"]+)['\"]", html)
        if redirect:
            r2 = requests.get(redirect.group(1), headers={'User-Agent': UA}, timeout=TIMEOUT, allow_redirects=True)
            m3u8 = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', r2.text)
            if m3u8:
                return {'streams': [{'player': 'direct_m3u8', 'url': m3u8.group(1), 'name': 'CLOUD'}]}

        # Look for iframes
        iframe = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', html)
        if iframe:
            iframe_url = iframe.group(1)
            if iframe_url.startswith('//'):
                iframe_url = 'https:' + iframe_url
            player = classify_url(iframe_url)
            extractor = EXTRACTORS.get(player)
            if extractor and extractor != extract_cloud_desidub_v2:
                return extractor(iframe_url)

        return {'streams': []}
    except:
        return {'streams': []}


# ========== FLIXCLOUD ==========

def extract_flixcloud_v2(url):
    """
    Extract from FlixCloud.
    URL format: https://flixcloud.cc/e/{id}?v={version}
    """
    try:
        resp = requests.get(url, headers={'User-Agent': UA}, timeout=TIMEOUT)
        html = resp.text

        # Find the fetch URL
        fetch_match = re.search(r'(https?://fetch7?\.flixcloud\.cc/_v\d+/[a-f0-9]+/master\.m3u8\?token=[^"\']+)', html)
        if fetch_match:
            m3u8_url = fetch_match.group(1)
            return {'streams': [{'player': 'direct_m3u8', 'url': m3u8_url, 'name': 'FlixCloud'}]}

        # Find UUID and get token
        uuid_match = re.search(r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', html)
        if uuid_match:
            uuid = uuid_match.group(1)
            # Try to get token from API
            token_resp = requests.get(f'https://flixcloud.cc/api/m3u8/{uuid}', headers={'User-Agent': UA}, timeout=TIMEOUT)
            if token_resp.status_code == 200:
                # Parse token response
                pass

        return {'streams': []}
    except:
        return {'streams': []}


# ========== ABYSS PLAYER ==========

def extract_abyss_v2(url):
    """
    Extract from Abyss Player.
    URL format: https://player.abyssplayer.com/{id} or https://abyssplayer.com/{id}
    """
    try:
        resp = requests.get(url, headers={'User-Agent': UA}, timeout=TIMEOUT)
        html = resp.text

        # Look for m3u8/mp4 in the page
        m3u8 = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html)
        if m3u8:
            return {'streams': [{'player': 'direct_m3u8', 'url': m3u8.group(1), 'name': 'Abyss'}]}

        mp4 = re.search(r'(https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*)', html)
        if mp4:
            return {'streams': [{'player': 'direct_m3u8', 'url': mp4.group(1), 'name': 'Abyss'}]}

        # Check for base64 encoded config
        datas = re.search(r'const datas = "([^"]+)"', html)
        if datas:
            try:
                config = json.loads(base64.b64decode(datas.group(1)))
                if isinstance(config.get('media'), str) and 'http' in config['media']:
                    return {'streams': [{'player': 'direct_m3u8', 'url': config['media'], 'name': 'Abyss'}]}
            except:
                pass

        # Try iframe redirect
        iframe = re.search(r'iframe[^>]*src=["\']([^"\']+)["\']', html)
        if iframe:
            iframe_url = iframe.group(1)
            if iframe_url.startswith('//'):
                iframe_url = 'https:' + iframe_url
            player = classify_url(iframe_url)
            extractor = EXTRACTORS.get(player)
            if extractor and extractor != extract_abyss_v2:
                return extractor(iframe_url)

        return {'streams': []}
    except:
        return {'streams': []}


# ========== STREAMRUBY (with proper Referer) ==========

def extract_streamruby_v2(url):
    """
    Extract from StreamRuby with proper Referer handling.
    URL format: https://streamruby.com/e/{id} or https://rubystm.com/e/{id}
    """
    try:
        match = re.search(r'/e/([a-zA-Z0-9]+)', url)
        if not match:
            return {'streams': []}
        fid = match.group(1)
        base = '/'.join(url.split('/')[:3])

        resp = requests.post(f'{base}/dl', headers={
            'User-Agent': UA,
            'Content-Type': 'application/x-www-form-urlencoded',
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
            except:
                pass

        m3u8 = re.search(r'file:\s*"(https?://[^"]*\.m3u8[^"]*)"', html)
        if m3u8:
            return {'streams': [{'player': 'direct_m3u8', 'url': m3u8.group(1), 'name': 'StreamRuby'}]}

        sources = re.search(r'sources:\s*\[(.*?)\]', html, re.DOTALL)
        if sources:
            fm = re.search(r'file:\s*"([^"]+)"', sources.group(1))
            if fm:
                return {'streams': [{'player': 'direct_m3u8', 'url': fm.group(1), 'name': 'StreamRuby'}]}

        return {'streams': []}
    except:
        return {'streams': []}


# ========== HELPERS ==========

def classify_url(url):
    """Auto-detect which player an embed URL belongs to"""
    if not url:
        return 'generic_embed'
    u = url.lower()
    PLAYER_MAP = {
        'gdmirrorbot.nl': 'gdmirrorbot', 'pro.iqsmartgames.com': 'gdmirrorbot',
        'vidmoly.org': 'vidmoly', 'vidmoly.net': 'vidmoly', 'vidmoly.biz': 'vidmoly',
        'streamruby.com': 'streamruby', 'rubystm.com': 'streamruby',
        'dood.li': 'doodstream', 'dood.to': 'doodstream',
        'streamtape.site': 'streamtape', 'streamtape.com': 'streamtape',
        'p2pplay.pro': 'streamp2p', '.strp': 'streamp2p',
        'rpmstream.live': 'rpmstream', 'rpmstream.com': 'rpmstream',
        'upns.live': 'upnshare', 'cloudy.upns': 'upnshare',
        'turbovidhls.com': 'turbovid', 'emturbovid.com': 'turbovid',
        'player.abyssplayer.com': 'abyss', 'play.abyssplayer.com': 'abyss', 'abyssplayer.com': 'abyss',
        'flixcloud.cc': 'flixcloud',
        'megacloud.animanga.fun': 'megacloud', 'mewstream': 'megacloud',
        'play.zephyrix.top': 'zephyrflick', 'as-cdn21.top': 'zephyrflick',
        'vidsrc.xyz': 'vidsrc', 'vidsrc.wtf': 'vidsrc',
        'moviesapi.club': 'moviesapi',
        'player.videasy.net': 'videasy',
        'hanerix.com': 'streamhg',
        'cloud.desidubanime.me': 'cloud',
        'desidubanime.p2pplay.pro': 'streamp2p',
        'desidubanime.rpmstream.live': 'rpmstream',
        'desidubanime.strp2p.site': 'streamp2p',
        'desidubanime.upns.live': 'upnshare',
    }
    for domain, player in PLAYER_MAP.items():
        if domain in u:
            return player
    if '.m3u8' in u:
        return 'direct_m3u8'
    return 'generic_embed'


# ========== EXTRACTOR REGISTRY ==========

EXTRACTORS = {
    'gdmirrorbot': extract_gdmirrorbot_v2,
    'upnshare': lambda url: extract_p2p_family(url, 'upnshare'),
    'streamp2p': lambda url: extract_p2p_family(url, 'streamp2p'),
    'rpmstream': lambda url: extract_p2p_family(url, 'rpmstream'),
    'cloud': extract_cloud_desidub_v2,
    'flixcloud': extract_flixcloud_v2,
    'abyss': extract_abyss_v2,
    'streamruby': extract_streamruby_v2,
}
