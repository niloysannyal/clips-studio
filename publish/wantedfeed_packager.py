"""WantedFeed multi-platform packaging, placeholder blocker, BST scheduler & KPI loop."""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

BST = timezone(timedelta(hours=6))
BST_PEAK_HOURS = (20, 1, 5)  # 20:00, 01:00, 05:00 BST (UTC+6)
MIN_SLOT_GAP_HOURS = 6.0

_PLACEHOLDER_RE = re.compile(r"\[[A-Za-z0-9_ -]+\]")
_VIDEO_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_WATCHLIST = _REPO_ROOT / "context" / "streamer-watchlist.json"
_DEFAULT_TRACKER = _REPO_ROOT / "logs" / "performance-tracker.csv"
_DEFAULT_TIMERS = _REPO_ROOT / "logs" / "bounty-timers.json"

_EXTRA_HANDLES = {
    "typical gamer": ("TypicalGamer", "YouTube"),
    "caseoh": ("CaseOh", "Twitch"),
    "lacy": ("Lacy", "Twitch"),
    "ohnepixel": ("ohnePixel", "Twitch"),
}

_FB_DISCOVERY_TAGS = [
    "#GTAV", "#GrandTheftAuto", "#GTAReels", "#GamingCommunity",
    "#StreamHighlights", "#ViralGaming", "#ViceCity",
]


def load_watchlist(watchlist_path: Path | None = None) -> list[dict]:
    path = watchlist_path or _DEFAULT_WATCHLIST
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return list(data.get("streamers") or [])
    except Exception:
        return []


def resolve_streamer(channel_name: str, platform_hint: str = "", watchlist_path: Path | None = None) -> dict:
    """Resolve canonical streamer name, clean handle, platform, and mandatory credit line."""
    raw = (channel_name or "").strip() or "Creator"
    lowered = raw.lower().lstrip("@")
    for row in load_watchlist(watchlist_path):
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        if lowered == name.lower() or lowered in str(row.get("channel_url") or "").lower():
            plat = str(row.get("platform") or platform_hint or "Twitch").strip()
            handle = re.sub(r"[^A-Za-z0-9_.]", "", name)
            return {
                "name": name,
                "handle": handle,
                "tag": handle.lower(),
                "platform": plat,
                "credit_line": f"Credit: @{handle} on {plat}",
            }
    if lowered in _EXTRA_HANDLES:
        name, plat = _EXTRA_HANDLES[lowered]
        handle = re.sub(r"[^A-Za-z0-9_.]", "", name)
        return {
            "name": name,
            "handle": handle,
            "tag": handle.lower(),
            "platform": platform_hint or plat,
            "credit_line": f"Credit: @{handle} on {platform_hint or plat}",
        }
    handle = re.sub(r"[^A-Za-z0-9_.]", "", raw) or "Creator"
    plat = (platform_hint or "Twitch").strip().capitalize()
    return {
        "name": raw,
        "handle": handle,
        "tag": handle.lower(),
        "platform": plat,
        "credit_line": f"Credit: @{handle} on {plat}",
    }


def _fit_short_title(core: str, suffix: str = "#GTA6 #Shorts", limit: int = 59, end_punct: str = "") -> str:
    clean = re.sub(r"\s+", " ", core).strip().strip('"\'.,;:')
    if end_punct and clean.endswith(end_punct):
        clean = clean[:-len(end_punct)].rstrip()
    max_core = limit - len(suffix) - 1 - len(end_punct)
    if len(clean) > max_core:
        trimmed = clean[:max_core].rsplit(" ", 1)[0].strip() or clean[:max_core]
        clean = trimmed.rstrip(" ,;:-")
    if end_punct:
        clean = f"{clean}{end_punct}"
    return f"{clean} {suffix}".strip()


_PRESERVE_UPPER = {
    "GTA", "VI", "V", "NPC", "FPS", "DLC", "RP", "FBI", "LSPD", "US",
    "POV", "IRL", "HUD", "PVP", "AI", "VIP", "TV", "PC",
}
_MINOR_WORDS = {
    "a", "an", "and", "as", "at", "by", "for", "from", "in", "into",
    "of", "on", "or", "the", "to", "vs", "with",
}
_VERB_BASE_MAP = {
    "pulls": "pull", "pulled": "pull",
    "survives": "survive", "survived": "survive",
    "escapes": "escape", "escaped": "escape",
    "steals": "steal", "stole": "steal",
    "triggers": "trigger", "triggered": "trigger",
    "breaks": "break", "broke": "break",
    "tests": "test", "tested": "test",
    "finds": "find", "found": "find",
    "hits": "hit",
    "gets": "get", "got": "get",
    "reaches": "reach", "reached": "reach",
    "fails": "fail", "failed": "fail",
    "tries": "try", "tried": "try",
    "plays": "play", "played": "play",
    "wins": "win", "won": "win",
    "loses": "lose", "lost": "lose",
    "fights": "fight", "fought": "fight",
    "beats": "beat",
    "pushes": "push", "pushed": "push",
}


def _strip_streamer_prefix(text: str, streamer_name: str) -> str:
    out = text.strip()
    if not streamer_name:
        return out
    variants = {streamer_name.strip(), re.sub(r"\s+", "", streamer_name.strip())}
    for v in sorted(variants, key=len, reverse=True):
        if v:
            out = re.sub(rf"^(?:@?{re.escape(v)})\b[\s:,\-—]*", "", out, flags=re.IGNORECASE).strip()
    return out


def _normalize_topic_phrase(raw: str, streamer_name: str = "") -> str:
    """Clean hashtags/placeholders and normalize ALL-CAPS text to readable Title/Sentence Case."""
    s = re.sub(r"#\w+", "", raw or "")
    s = _PLACEHOLDER_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip().strip('"\'.,!?:;-')
    s = _strip_streamer_prefix(s, streamer_name)
    s = re.sub(r"\b(?:in|on|at)\s+GTA\s*(?:6|VI)\b", "", s, flags=re.IGNORECASE).strip(" ,;:-")
    s = re.sub(r"\bGTA\s*(?:6|VI)\b", "", s, flags=re.IGNORECASE).strip(" ,;:-")
    if not s:
        return ""
    tokens = s.split()
    out: list[str] = []
    for idx, tok in enumerate(tokens):
        clean_tok = tok.strip(".,!?:;\"'")
        upper_tok = clean_tok.upper()
        if upper_tok in _PRESERVE_UPPER or clean_tok.isdigit():
            out.append(upper_tok if upper_tok in _PRESERVE_UPPER else tok)
        elif clean_tok.isupper() or idx == 0:
            low = clean_tok.lower()
            if idx > 0 and low in _MINOR_WORDS:
                out.append(low)
            else:
                out.append(low.capitalize())
        else:
            # Preserve intentional mixed casing (e.g. IShowSpeed, xQc, iPhone)
            out.append(tok if any(c.isupper() for c in clean_tok[1:]) else (clean_tok.lower() if (idx > 0 and clean_tok.lower() in _MINOR_WORDS) else clean_tok.capitalize()))
    return " ".join(out)


def _to_when_clause(raw: str, streamer_name: str = "") -> str:
    phrase = _normalize_topic_phrase(raw, streamer_name=streamer_name)
    if not phrase:
        return "You Test This Mechanic"
    words = phrase.split()
    first_low = words[0].lower()
    if first_low in ("you", "players", "someone", "cops", "police", "npcs", "they"):
        return " ".join(words[:5])
    if first_low in ("he", "she"):
        words = words[1:]
        if not words:
            return "You Test This Mechanic"
        first_low = words[0].lower()
    if first_low in _VERB_BASE_MAP:
        words[0] = _VERB_BASE_MAP[first_low].capitalize()
        clause = ["You", *words[:4]]
        return " ".join(clause)
    if first_low in ("after", "during", "inside", "before", "without", "at", "on", "in"):
        return " ".join(["You", "Play", *words[:3]])
    return " ".join(["You", "Try", *words[:4]])


def _sanitize_llm_title(raw: str, fallback: str) -> str:
    if not raw or not isinstance(raw, str):
        return fallback
    cleaned = re.sub(r"#\w+", "", raw).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip('"\' ')
    if not cleaned or _PLACEHOLDER_RE.search(cleaned):
        return fallback
    # Reject shouted all-caps titles from an LLM
    alpha = [c for c in cleaned if c.isalpha()]
    if alpha and sum(1 for c in alpha if c.isupper()) / len(alpha) > 0.70:
        return fallback
    end_p = "?" if cleaned.endswith("?") else ""
    return _fit_short_title(cleaned, end_punct=end_p)


def build_three_pattern_titles(
    base_title: str,
    streamer_name: str,
    hook_text: str = "",
    *,
    summary: str = "",
    llm=None,
) -> dict[str, str]:
    """Generate Pattern 1/2/3 titles strictly under 60 chars ending with #GTA6 #Shorts.

    Derives clean sentence/title-cased phrasing from summary & base_title (never
    pasting all-caps overlay hooks verbatim into mechanic/contrast templates), with
    optional LLM generation when an llm backend is provided.
    """
    reaction_src = _normalize_topic_phrase(base_title, streamer_name=streamer_name)
    summary_src = _normalize_topic_phrase(summary, streamer_name=streamer_name)
    hook_src = _normalize_topic_phrase(hook_text, streamer_name=streamer_name)

    reaction_phrase = reaction_src or summary_src or hook_src or "Wild GTA 6 Moment"
    mechanic_seed = summary or base_title or hook_text
    when_clause = _to_when_clause(mechanic_seed, streamer_name=streamer_name)
    contrast_phrase = summary_src or reaction_src or hook_src or "Gameplay Details"

    fallback = {
        "pattern_1_reaction": _fit_short_title(f"{streamer_name}: {reaction_phrase}"),
        "pattern_2_mechanic": _fit_short_title(f"What Happens When {when_clause}", end_punct="?"),
        "pattern_3_contrast": _fit_short_title(f"GTA 6 vs GTA 5: {contrast_phrase}"),
    }

    if llm is not None:
        try:
            prompt = (
                "Write 3 distinct YouTube Shorts title cores (MAX 42 characters each, NO hashtags, "
                "NO brackets, NO ALL CAPS) for a GTA 6 clip.\n"
                f"Streamer: {streamer_name}\n"
                f"Clip Title: {base_title}\n"
                f"Summary/Transcript: {summary or hook_text}\n"
                "Return JSON only with keys:\n"
                '- "pattern_1_reaction": Streamer reaction/milestone angle\n'
                '- "pattern_2_mechanic": Must start with "What Happens When " and end with "?"\n'
                '- "pattern_3_contrast": Must start with "GTA 6 vs GTA 5: "\n'
            )
            raw = llm.generate(prompt, json_mode=True)
            data = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(data, dict):
                return {
                    k: _sanitize_llm_title(str(data.get(k) or ""), fallback[k])
                    for k in ("pattern_1_reaction", "pattern_2_mechanic", "pattern_3_contrast")
                }
        except Exception:
            pass

    return fallback


def validate_no_placeholders(obj) -> None:
    """Raise ValueError if any unresolved [placeholder] token appears in metadata."""
    def _walk(node, path: str) -> None:
        if isinstance(node, str):
            m = _PLACEHOLDER_RE.search(node)
            if m:
                raise ValueError(f"Unresolved placeholder {m.group(0)!r} found in {path}")
        elif isinstance(node, dict):
            for k, v in node.items():
                _walk(v, f"{path}.{k}")
        elif isinstance(node, (list, tuple)):
            for idx, item in enumerate(node):
                _walk(item, f"{path}[{idx}]")

    _walk(obj, "meta")


def _read_tracker_rows(csv_path: Path | None = None) -> list[dict]:
    path = csv_path or _DEFAULT_TRACKER
    if not path.is_file():
        return []
    try:
        with path.open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def ingest_kpi_metrics(csv_path: Path | None = None) -> dict[str, dict]:
    """Summarize real performance-tracker.csv KPIs into per-streamer scoring weights."""
    rows = _read_tracker_rows(csv_path)
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        streamer = str(row.get("streamer") or "").strip()
        if not streamer:
            continue
        grouped.setdefault(streamer, []).append(row)

    summary: dict[str, dict] = {}
    all_apvs: list[float] = []
    for s_rows in grouped.values():
        for r in s_rows:
            try:
                all_apvs.append(float(r.get("apv_percent") or 0))
            except ValueError:
                pass
    global_apv = (sum(all_apvs) / len(all_apvs)) if all_apvs else 65.0

    for streamer, s_rows in grouped.items():
        views = [float(r.get("views") or 0) for r in s_rows if str(r.get("views") or "").strip()]
        apvs = [float(r.get("apv_percent") or 0) for r in s_rows if str(r.get("apv_percent") or "").strip()]
        payouts = [float(r.get("revenue_usd") or 0) for r in s_rows if str(r.get("revenue_usd") or "").strip()]
        avg_views = sum(views) / max(len(views), 1)
        avg_apv = sum(apvs) / max(len(apvs), 1) if apvs else global_apv
        ratio = avg_apv / max(global_apv, 1.0)
        weight = round(max(0.85, min(1.25, ratio)), 3)
        summary[streamer] = {
            "clips_logged": len(s_rows),
            "avg_views": round(avg_views, 1),
            "avg_apv_percent": round(avg_apv, 2),
            "total_revenue_usd": round(sum(payouts), 2),
            "weight_multiplier": weight,
        }
    return summary


def schedule_slot_bst(
    streamer_name: str,
    *,
    now: datetime | None = None,
    csv_path: Path | None = None,
    existing_slots: list[dict] | None = None,
) -> dict:
    """Pick the next open BST peak slot (20:00, 01:00, 05:00 BST, >=6h spacing)
    while enforcing anti-cannibalization streamer rotation."""
    ref_now = (now or datetime.now(timezone.utc)).astimezone(BST)
    rows = _read_tracker_rows(csv_path)
    last_streamer = ""
    last_slot_dt: datetime | None = None

    if existing_slots:
        tail = existing_slots[-1]
        last_streamer = str(tail.get("streamer") or "")
        try:
            last_slot_dt = datetime.fromisoformat(str(tail.get("scheduled_bst"))).astimezone(BST)
        except Exception:
            last_slot_dt = None
    elif rows:
        last_row = rows[-1]
        last_streamer = str(last_row.get("streamer") or "")
        date_str = str(last_row.get("date") or "").strip()
        if date_str:
            try:
                parsed_d = datetime.fromisoformat(date_str)
                if parsed_d.tzinfo is None:
                    parsed_d = parsed_d.replace(hour=20, minute=0, tzinfo=BST)
                last_slot_dt = parsed_d.astimezone(BST)
            except Exception:
                last_slot_dt = None

    earliest = ref_now + timedelta(minutes=15)
    if last_slot_dt is not None:
        earliest = max(earliest, last_slot_dt + timedelta(hours=MIN_SLOT_GAP_HOURS))

    same_streamer_consecutive = bool(
        last_streamer and last_streamer.strip().lower() == streamer_name.strip().lower()
    )
    if same_streamer_consecutive:
        # Enforce rotation by delaying past the next peak slot so another streamer goes first
        earliest = earliest + timedelta(hours=MIN_SLOT_GAP_HOURS)

    candidates: list[datetime] = []
    base_day = earliest.date() - timedelta(days=1)
    for d_off in range(0, 7):
        day = base_day + timedelta(days=d_off)
        for hr in BST_PEAK_HOURS:
            slot_dt = datetime(day.year, day.month, day.day, hr, 0, 0, tzinfo=BST)
            if slot_dt >= earliest:
                candidates.append(slot_dt)
    candidates.sort()
    chosen = candidates[0] if candidates else earliest.replace(minute=0, second=0, microsecond=0)
    return {
        "scheduled_bst": chosen.isoformat(),
        "scheduled_utc": chosen.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "streamer": streamer_name,
        "rotation_deferred": same_streamer_consecutive,
        "previous_streamer": last_streamer,
    }


def start_bounty_timer(
    clip_id: int | str,
    campaign_name: str,
    post_url: str,
    *,
    timers_path: Path | None = None,
    window_minutes: int = 30,
    now: datetime | None = None,
) -> dict:
    """Track a 30-minute Clipster / Whop live-URL bounty submission timer."""
    path = timers_path or _DEFAULT_TIMERS
    path.parent.mkdir(parents=True, exist_ok=True)
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    deadline = current + timedelta(minutes=window_minutes)

    existing: list[dict] = []
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing = []
    if not isinstance(existing, list):
        existing = []

    record = {
        "clip_id": clip_id,
        "campaign_name": campaign_name.strip(),
        "post_url": post_url.strip(),
        "started_utc": current.isoformat().replace("+00:00", "Z"),
        "deadline_utc": deadline.isoformat().replace("+00:00", "Z"),
        "deadline_bst": deadline.astimezone(BST).isoformat(),
        "window_minutes": window_minutes,
        "status": "active",
    }
    existing = [r for r in existing if not (str(r.get("clip_id")) == str(clip_id) and r.get("campaign_name") == record["campaign_name"])]
    existing.append(record)
    path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    return {**record, "remaining_minutes": float(window_minutes)}


def list_bounty_timers(*, timers_path: Path | None = None, now: datetime | None = None) -> list[dict]:
    path = timers_path or _DEFAULT_TIMERS
    if not path.is_file():
        return []
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    out = []
    for item in items if isinstance(items, list) else []:
        try:
            dl = datetime.fromisoformat(str(item["deadline_utc"]).replace("Z", "+00:00")).astimezone(timezone.utc)
            rem = (dl - current).total_seconds() / 60.0
        except Exception:
            rem = 0.0
        urgency = "expired" if rem <= 0 else ("urgent" if rem <= 10 else "on_track")
        out.append({**item, "remaining_minutes": round(rem, 1), "urgency": urgency})
    return out


def _recent_related_suggestion(csv_path: Path | None = None) -> str:
    rows = _read_tracker_rows(csv_path)
    for row in reversed(rows):
        cid = str(row.get("clip_id") or "").strip()
        streamer = str(row.get("streamer") or "").strip()
        notes = str(row.get("notes") or "").strip()
        if cid:
            return f"{streamer}: {notes or cid}".strip(": ")
    return ""


def build_package(
    *,
    clip_path: Path,
    channel_name: str,
    title: str,
    hook_text: str = "",
    summary: str = "",
    duration_s: float = 30.0,
    platform_hint: str = "",
    safety: dict | None = None,
    watchlist_path: Path | None = None,
    tracker_path: Path | None = None,
    llm=None,
) -> dict:
    """Build complete validated multi-platform metadata package for WantedFeed."""
    streamer = resolve_streamer(channel_name, platform_hint=platform_hint, watchlist_path=watchlist_path)
    titles = build_three_pattern_titles(
        title,
        streamer["name"],
        hook_text=hook_text,
        summary=summary,
        llm=llm,
    )
    safety = safety or {}
    gore_warning = bool(safety.get("gore_safety_warning", False))
    music_risk = bool(safety.get("music_copyright_risk", False))

    locked_meta_tags = [
        "#gta6",
        f"#{streamer['tag']}",
        "#gta6clips",
        "#gamingclips",
        "#wantedfeed",
    ]
    hook_line = (hook_text or title or "Wait until the ending in GTA 6!").strip()
    summary_line = (summary or f"{streamer['name']} pulled off one of the wildest moments in GTA 6.").strip()
    debate_q = f"Would you survive what {streamer['name']} just did in GTA 6? Drop your take!"
    credit = streamer["credit_line"]

    meta_caption = (
        f"{hook_line}\n\n"
        f"{debate_q}\n\n"
        f"{credit}\n"
        f"{' '.join(locked_meta_tags)}"
    )
    yt_desc = (
        f"{summary_line}\n\n"
        f"{credit}\n"
        f"#GTA6 #{streamer['tag']} #Shorts"
    )
    tiktok_caption = (
        f"{hook_line} {credit} #gta6 #{streamer['tag']} #gta6clips #gamingclips #wantedfeed"
    )
    threads_p1 = f"{hook_line}\n\n{summary_line}\n{credit}"
    threads_p2 = f"Rate this GTA 6 clip from 1 to 10 — could you pull this off?"

    x_copy_raw = f"{hook_line} — {streamer['name']} in GTA 6. {credit} #GTA6 #WantedFeed"
    x_copy = _VIDEO_URL_RE.sub("", x_copy_raw).strip()

    schedule = schedule_slot_bst(streamer["name"], csv_path=tracker_path)
    kpis = ingest_kpi_metrics(csv_path=tracker_path)

    pkg = {
        "clip_file": clip_path.name,
        "streamer": streamer,
        "duration_seconds": round(float(duration_s), 2),
        "titles": titles,
        "platforms": {
            "meta_reels": {
                "caption": meta_caption,
                "locked_tags": locked_meta_tags,
                "fb_discovery_tags": list(_FB_DISCOVERY_TAGS),
            },
            "youtube_shorts": {
                "account": "@WantedFeedHQ",
                "title": titles["pattern_1_reaction"],
                "description": yt_desc,
                "category": "Gaming",
                "game_title": "Grand Theft Auto VI",
                "related_video": _recent_related_suggestion(tracker_path),
            },
            "tiktok": {
                "account": "@wanted.feed",
                "caption": tiktok_caption,
                "location": "",
                "tiktok_safe": not gore_warning,
                "creator_rewards_60s": float(duration_s) >= 60.0,
            },
            "threads": {
                "account": "@wanted.feed",
                "topic": "GTA 6",
                "part_1": threads_p1,
                "part_2": threads_p2,
            },
            "x": {
                "account": "@wantedfeed",
                "caption": x_copy,
            },
        },
        "safety": {
            "music_copyright_risk": music_risk,
            "vocal_band_ratio": safety.get("vocal_band_ratio", 1.0),
            "gore_safety_warning": gore_warning,
            "warning_range": safety.get("warning_range", ""),
            "music_stripped": bool(safety.get("music_stripped", False)),
        },
        "schedule_bst": schedule,
        "streamer_kpi_weight": (kpis.get(streamer["name"]) or {}).get("weight_multiplier", 1.0),
    }
    validate_no_placeholders(pkg)
    return pkg


def package_to_markdown(pkg: dict) -> str:
    t = pkg["titles"]
    p = pkg["platforms"]
    s = pkg["safety"]
    sched = pkg["schedule_bst"]
    return (
        f"# WantedFeed Clip Package — `{pkg['clip_file']}`\n\n"
        f"- **Streamer:** {pkg['streamer']['name']} ({pkg['streamer']['credit_line']})\n"
        f"- **Duration:** {pkg['duration_seconds']}s | **TikTok >60s Rewards:** {p['tiktok']['creator_rewards_60s']}\n"
        f"- **Scheduled Slot (BST):** `{sched['scheduled_bst']}`"
        + (" *(rotation deferred: consecutive streamer avoided)*" if sched["rotation_deferred"] else "")
        + "\n"
        f"- **Safety:** Music risk=`{s['music_copyright_risk']}` | TikTok Safe=`{p['tiktok']['tiktok_safe']}`"
        + (f" *(Warning window: {s['warning_range']})*" if s["warning_range"] else "")
        + "\n\n"
        f"## Title Variations (<60 chars)\n"
        f"1. **Reaction / Milestone:** {t['pattern_1_reaction']}\n"
        f"2. **Mechanic Test:** {t['pattern_2_mechanic']}\n"
        f"3. **Contrast / Comparison:** {t['pattern_3_contrast']}\n\n"
        f"## YouTube Shorts (`@WantedFeedHQ`)\n"
        f"- **Category:** Gaming | **Game Title:** Grand Theft Auto VI\n"
        f"- **Related Video Suggestion:** {p['youtube_shorts']['related_video'] or 'None yet'}\n\n"
        f"```text\n{p['youtube_shorts']['description']}\n```\n\n"
        f"## Meta Reels (Facebook + Instagram `@wanted.feed`)\n"
        f"```text\n{p['meta_reels']['caption']}\n```\n"
        f"- **FB Discovery Tags:** {' '.join(p['meta_reels']['fb_discovery_tags'])}\n\n"
        f"## TikTok (`@wanted.feed`)\n"
        f"```text\n{p['tiktok']['caption']}\n```\n\n"
        f"## Threads (`@wanted.feed`, Topic: GTA 6)\n"
        f"- **Part 1:**\n```text\n{p['threads']['part_1']}\n```\n"
        f"- **Part 2 (0 hashtags):**\n```text\n{p['threads']['part_2']}\n```\n\n"
        f"## X (`@wantedfeed`)\n"
        f"```text\n{p['x']['caption']}\n```\n"
    )


def write_package_files(clip_path: Path, pkg: dict) -> tuple[Path, Path]:
    validate_no_placeholders(pkg)
    json_path = clip_path.with_name(f"{clip_path.stem}_meta.json")
    md_path = clip_path.with_name(f"{clip_path.stem}_meta.md")
    json_path.write_text(json.dumps(pkg, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(package_to_markdown(pkg), encoding="utf-8")
    return json_path, md_path
