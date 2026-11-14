/**
 * Universal Player Dispatcher.
 */

import { resolveAbyss } from "./abyss.js";
import { resolveByse } from "./byse.js";
import { resolveModiplay, resolveDirectEmbed } from "./direct_m3u8.js";
import { resolveStreamRuby } from "./streamruby.js";
import { resolveTurboVid, resolveUpnShare } from "./extra_players.js";

export function classifyEmbedUrl(url) {
  const u = (url || "").toLowerCase();
  if (u.includes("abyssplayer.com") || u.includes("playhydrax.com") || u.includes("sssrr.org")) return "abyss";
  if (u.includes("bysetayico") || u.includes("bysezejataos") || u.includes("bysevepoin") || u.includes("byse")) return "byse";
  if (u.includes("modiplay") || u.includes("rozgarlelo")) return "modiplay";
  if (u.includes("rubystm") || u.includes("streamruby")) return "streamruby";
  if (u.includes("turbovid") || u.includes("emturbovid")) return "turbovid";
  if (u.includes("upns") || u.includes("uns.bio")) return "upnshare";
  if (u.includes("vidmmo") || u.includes("vidout")) return "dead";
  if (u.includes("embed.filmu.in") || u.includes("vidrift.net") || u.includes(".m3u8")) return "direct_m3u8";
  return "generic";
}

export async function resolveEmbedUrl(url, providerName = "AniBox") {
  const type = classifyEmbedUrl(url);
  try {
    if (type === "abyss") return await resolveAbyss(url, providerName);
    if (type === "byse") {
      const s = await resolveByse(url, providerName);
      return s ? [s] : [];
    }
    if (type === "modiplay") {
      const s = await resolveModiplay(url, providerName);
      return s ? [s] : [];
    }
    if (type === "streamruby") {
      const s = await resolveStreamRuby(url, providerName);
      return s ? [s] : [];
    }
    if (type === "turbovid") {
      const s = await resolveTurboVid(url, providerName);
      return s ? [s] : [];
    }
    if (type === "upnshare") {
      const s = await resolveUpnShare(url, providerName);
      return s ? [s] : [];
    }
    if (type === "direct_m3u8") {
      const s = await resolveDirectEmbed(url, providerName);
      return s ? [s] : [];
    }
  } catch (err) {
    console.error(`Error resolving ${url}:`, err);
  }
  return [];
}
