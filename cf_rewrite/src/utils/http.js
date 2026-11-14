/**
 * HTTP client optimized for Cloudflare Workers Edge runtime.
 */

export const DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36";

export const USER_AGENTS = [
  DEFAULT_UA,
  "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"
];

export function getRandomUa() {
  return USER_AGENTS[Math.floor(Math.random() * USER_AGENTS.length)];
}

export async function edgeFetch(url, options = {}) {
  const headers = {
    "User-Agent": options.userAgent || DEFAULT_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    ...(options.headers || {})
  };

  const timeoutMs = options.timeout || 8000;
  let signal = options.signal;
  let timeoutId = null;

  if (!signal && typeof AbortController !== "undefined") {
    const controller = new AbortController();
    signal = controller.signal;
    timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  }

  const fetchOpts = {
    method: options.method || "GET",
    headers,
    signal,
    body: options.body,
    redirect: options.redirect || "follow",
  };

  if (typeof fetch !== "undefined") {
    fetchOpts.cf = {
      cacheTtl: options.ttl || 300,
      cacheEverything: true,
      ...(options.cf || {})
    };
  }

  try {
    const res = await fetch(url, fetchOpts);
    return res;
  } finally {
    if (timeoutId) clearTimeout(timeoutId);
  }
}

export async function fetchText(url, options = {}) {
  try {
    const res = await edgeFetch(url, options);
    if (!res.ok) return "";
    return await res.text();
  } catch (err) {
    return "";
  }
}

export async function fetchJson(url, options = {}) {
  try {
    const res = await edgeFetch(url, {
      ...options,
      headers: { "Accept": "application/json", ...(options.headers || {}) }
    });
    if (!res.ok) return null;
    return await res.json();
  } catch (err) {
    return null;
  }
}

export function corsHeaders(extra = {}) {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
    "Access-Control-Allow-Headers": "*",
    "Content-Type": "application/json; charset=utf-8",
    ...extra
  };
}
