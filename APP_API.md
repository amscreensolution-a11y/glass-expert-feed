# GlassExpert Feed — App API

Public GitHub feed for Absolute Mobile Screen: https://github.com/amscreensolution-a11y/glass-expert-feed

**Privacy note:** the repo is public. It holds only the phone-glass catalog. Never put secrets in this feed.

## Stable download URLs (no token needed)

| File | URL |
|------|-----|
| **manifest.json** | `https://raw.githubusercontent.com/amscreensolution-a11y/glass-expert-feed/main/manifest.json` |
| **glass.json** | `https://raw.githubusercontent.com/amscreensolution-a11y/glass-expert-feed/main/glass.json` |
| **glass.sqlite** | `https://raw.githubusercontent.com/amscreensolution-a11y/glass-expert-feed/main/glass.sqlite` |
| **glass.py** | `https://raw.githubusercontent.com/amscreensolution-a11y/glass-expert-feed/main/glass.py` |
| **APP_API.md** | `https://raw.githubusercontent.com/amscreensolution-a11y/glass-expert-feed/main/APP_API.md` |

raw.githubusercontent.com is CDN-cached for about 5 minutes, so a new push can take a few minutes to show up. CORS is enabled (`Access-Control-Allow-Origin: *`), so browser and Flutter Web clients work.

## Daily client flow

1. `GET` manifest.json once per day (or on app launch if the last check was 24h or more ago).
2. Compare `version` (`YYYY-MM-DD`, or `YYYY-MM-DD.N` for a second publish on the same day; compare as strings) with the locally cached version.
3. If it is newer, `GET` `files["glass.json"].url` (apps) or `files["glass.sqlite"].url` (terminal tool).
4. Check `sha256` (lowercase hex) and `size`, then swap the local copy atomically.

## manifest.json schema

```json
{
  "version": "2026-10-16",
  "name": "GlassExpert-Feed",
  "repo": "https://github.com/amscreensolution-a11y/glass-expert-feed",
  "updated_at": "2026-10-16T00:30:00+0530",
  "files": {
    "glass.sqlite": {"sha256": "...", "size": 123, "url": "https://raw.githubusercontent.com/amscreensolution-a11y/glass-expert-feed/main/glass.sqlite"},
    "glass.json":   {"sha256": "...", "size": 123, "url": "https://raw.githubusercontent.com/amscreensolution-a11y/glass-expert-feed/main/glass.json"},
    "glass.py":     {"sha256": "...", "size": 123, "url": "https://raw.githubusercontent.com/amscreensolution-a11y/glass-expert-feed/main/glass.py"},
    "APP_API.md":   {"sha256": "...", "size": 123, "url": "https://raw.githubusercontent.com/amscreensolution-a11y/glass-expert-feed/main/APP_API.md"},
    "manifest.json":{"url": "https://raw.githubusercontent.com/amscreensolution-a11y/glass-expert-feed/main/manifest.json"}
  },
  "note": "..."
}
```

## glass.json schema (compact)

```json
{
  "version": "2026-10-15",
  "source": "Absolute Mobile Screen / GlassExpert",
  "counts": {"models": 0, "groups": 0, "tiers": 0, "privacy_pairs": 0},
  "models": [
    {
      "name": "Samsung Galaxy A05s",
      "aliases": [],
      "brand": "Samsung",
      "fam": "samsung",
      "core": "a05s",
      "series": "Galaxy A",
      "codes": {"ARC": "F018", "Full Glue (Prince)": "DM001"},
      "group_ids": ["P04-G0123"],
      "pred": {"code": "F018", "alt": ["F019"], "confidence": "High"},
      "tier_hint": "A"
    }
  ],
  "groups": {
    "P04-G0123": {
      "line": "ARC",
      "sku": "F018",
      "product_id": "P04",
      "title": "...",
      "notes": null,
      "models": ["Samsung Galaxy A05s", "..."]
    }
  },
  "tiers": {
    "F018": {
      "line": "ARC",
      "tier": "A",
      "rank": 1,
      "demand": 6.1379,
      "lifecycle": "Mature",
      "action": "Deep stock, never out",
      "top_phones": "..."
    }
  },
  "privacy_pairs": {
    "F018": {"privacy": "Pxxx", "share": 0.42}
  }
}
```

- **codes**: product-line name → SKU / glass code for that phone.
- **group_ids**: Princeshop groups this phone shares glass with (use `groups[id].models` for siblings).
- **pred**: predicted ARC (or other) code when not listed on Princeshop — always test-fit.
- **tiers**: India demand tier by glass code.

## Flutter example (daily JSON fetch)

```dart
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:crypto/crypto.dart'; // sha256

const manifestUrl =
  'https://raw.githubusercontent.com/amscreensolution-a11y/glass-expert-feed/main/manifest.json';

Future<Map<String, dynamic>?> fetchGlassFeedIfStale() async {
  final prefs = await SharedPreferences.getInstance();
  final last = prefs.getInt('glass_last_check') ?? 0;
  final now = DateTime.now().millisecondsSinceEpoch;
  if (now - last < 24 * 3600 * 1000 && prefs.containsKey('glass_json')) {
    return jsonDecode(prefs.getString('glass_json')!);
  }
  final manRes = await http.get(Uri.parse(manifestUrl));
  if (manRes.statusCode != 200) return null;
  final man = jsonDecode(manRes.body) as Map<String, dynamic>;
  final remoteVer = man['version'] as String;
  final localVer = prefs.getString('glass_version');
  if (localVer != null && remoteVer.compareTo(localVer) <= 0) {
    await prefs.setInt('glass_last_check', now);
    return jsonDecode(prefs.getString('glass_json')!);
  }
  final file = man['files']['glass.json'];
  final dataRes = await http.get(Uri.parse(file['url'] as String));
  if (dataRes.statusCode != 200) return null;
  if (sha256.convert(dataRes.bodyBytes).toString() != file['sha256']) return null;
  final body = utf8.decode(dataRes.bodyBytes);
  await prefs.setString('glass_json', body);
  await prefs.setString('glass_version', remoteVer);
  await prefs.setInt('glass_last_check', now);
  return jsonDecode(body) as Map<String, dynamic>;
}
```

## JavaScript example

```js
const MANIFEST_URL =
  "https://raw.githubusercontent.com/amscreensolution-a11y/glass-expert-feed/main/manifest.json";

async function fetchGlassJsonDaily(storage = localStorage) {
  const now = Date.now();
  const last = Number(storage.getItem("glass_last_check") || 0);
  if (now - last < 864e5 && storage.getItem("glass_json")) {
    return JSON.parse(storage.getItem("glass_json"));
  }
  const man = await fetch(MANIFEST_URL).then((r) => r.json());
  const localVer = storage.getItem("glass_version");
  if (localVer && man.version <= localVer) {
    storage.setItem("glass_last_check", String(now));
    return JSON.parse(storage.getItem("glass_json"));
  }
  const meta = man.files["glass.json"];
  const buf = await fetch(meta.url).then((r) => r.arrayBuffer());
  const hash = [...new Uint8Array(await crypto.subtle.digest("SHA-256", buf))]
    .map((b) => b.toString(16).padStart(2, "0")).join("");
  if (hash !== meta.sha256) throw new Error("sha256 mismatch");
  const text = new TextDecoder().decode(buf);
  storage.setItem("glass_json", text);
  storage.setItem("glass_version", man.version);
  storage.setItem("glass_last_check", String(now));
  return JSON.parse(text);
}
```

## Terminal tool self-update

`glass.py` checks the manifest at most once per 24h on start (silent if offline), or immediately with:

```bash
python3 glass.py update
```

It shows `data as of <version>` and atomically replaces `glass.sqlite` (and `glass.py` when the manifest lists a newer sha256).
