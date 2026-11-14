/**
 * AniBox Edge V2 - Cloudflare Workers Addon Router
 * Full rewrite of the AniBox Python codebase to Edge JavaScript.
 */

import { corsHeaders } from "./utils/http.js";
import { makeManifest } from "./handlers/manifest.js";
import { handleCatalog } from "./handlers/catalog.js";
import { handleMeta } from "./handlers/meta.js";
import { handleStream } from "./handlers/stream.js";
import { handleConfigure } from "./handlers/configure.js";
import { handleHlsManifest, handleHlsSegment } from "./handlers/hls.js";
import { handleStreamProxy } from "./handlers/proxy.js";

function parseConfig(seg) {
  if (!seg) return {};
  try {
    let padded = seg + "=".repeat((4 - (seg.length % 4)) % 4);
    let bin = atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(bin);
  } catch (e) {
    return {};
  }
}

export async function handleRequest(request) {
  const url = new URL(request.url);
  const path = url.pathname;

  if (request.method === "OPTIONS") {
    return new Response(null, { headers: corsHeaders() });
  }

  const rawSegments = path.split("/").filter(Boolean);
  if (rawSegments.length === 0 || path === "/" || path === "/configure") {
    return handleConfigure(request);
  }

  const last = rawSegments[rawSegments.length - 1];
  if (last === "manifest.json") {
    const configStr = rawSegments.length > 1 ? rawSegments[0] : "";
    const config = parseConfig(configStr);
    const manifest = makeManifest(config);
    return new Response(JSON.stringify(manifest), {
      headers: corsHeaders({ "Cache-Control": "public, max-age=3600, stale-while-revalidate=1800" })
    });
  }

  // Edge Video Stream Proxy (MP4 Range Proxy with Header Preservation)
  if (path === "/stream/proxy" || path.startsWith("/stream/proxy")) {
    return handleStreamProxy(request);
  }

  // Edge HLS Stream & Segment Routes
  if (path === "/hls/manifest" || path.startsWith("/hls/manifest")) {
    return handleHlsManifest(request);
  }
  if (path.startsWith("/hls/seg/")) {
    const segToken = path.replace(/^\/hls\/seg\//, "");
    return handleHlsSegment(request, segToken);
  }

  // Detect Stremio resource routes: "catalog", "meta", "stream"
  const resIdx = rawSegments.findIndex(s => ["catalog", "meta", "stream"].includes(s));
  if (resIdx !== -1) {
    const configStr = resIdx > 0 ? rawSegments[0] : "";
    const config = parseConfig(configStr);
    const resource = rawSegments[resIdx];
    const type = rawSegments[resIdx + 1] || "";
    let id = rawSegments[resIdx + 2] || "";
    let extra = rawSegments.slice(resIdx + 3).join("/");

    if (extra.endsWith(".json")) {
      extra = extra.slice(0, -5);
    } else if (id.endsWith(".json")) {
      id = id.slice(0, -5);
    }

    id = decodeURIComponent(id);
    extra = decodeURIComponent(extra);

    if (resource === "catalog") {
      return handleCatalog(config, type, id, extra, url);
    } else if (resource === "meta") {
      return handleMeta(config, type, id, url);
    } else if (resource === "stream") {
      return handleStream(config, type, id, url);
    }
  }

  return new Response(JSON.stringify({ status: "AniBox Edge V2 Online" }), {
    headers: corsHeaders()
  });
}

export default {
  async fetch(request, env, ctx) {
    return handleRequest(request);
  }
};
