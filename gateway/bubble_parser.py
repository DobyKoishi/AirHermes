"""Robust Streaming Message Boundary Parser for Hermes Agent (Phase 2.3 Hardened + Paragraph Fallback).

Features:
- Strict Delimiter Extraction: Detects autonomous message boundaries with balanced nesting depth.
- Alternative Delimiter Support: <<<bubble>>> and <bubble>...</bubble> with correct token precedence.
- Code Fence State Machine: Cross-bubble code fence tracking, balancing, and language preservation.
- Markdown/HTML Protection: Code blocks containing <bubble> example tags are preserved verbatim.
- Robust Incomplete Tag Handling: Incomplete control tags at stream end are stripped cleanly without leaking.
- Natural Paragraph Fallback: When no bubble tags are used, breaks on clean paragraph boundaries (\\n\\n)
  outside code blocks for smooth streaming on plain text outputs.
- Comprehensive Multimodal Tags: Tapbacks, interactive polls, calendar cards (.ics), Apple Maps cards,
  and native iOS animations / invisible ink effects.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from urllib.parse import quote_plus


class BubbleParser:
    """Parses incremental LLM streaming deltas into discrete, Markdown-balanced bubbles."""

    _OPEN_TAG = "<bubble>"
    _CLOSE_TAG = "</bubble>"
    _SEP_MARKER = "<<<bubble>>>"
    _MD_LINK_RE = re.compile(r'\[(?P<text>[^\]\r\n]+)\]\((?P<url>(?:https?|shortcuts|maps|mobilenotes)://[a-zA-Z0-9\-._~:/?#\[\]@!$&\'()*+,;=%]+)\)')
    _BARE_URL_RE = re.compile(r'(?:https?|shortcuts|maps|mobilenotes)://[a-zA-Z0-9\-._~:/?#\[\]@!$&\'()*+,;=%]+')
    _TRAILING_PUNCT = ".,;:!?()[]{}<>\"'“”‘’，。！？；：、（）《》【】"

    _TAPBACK_RE = re.compile(
        r'<(?:tapback|reaction)(?:\s+emoji=["\']([^"\']+)["\'])?\s*>(.*?)</(?:tapback|reaction)>|<(?:tapback|reaction)\s+emoji=["\']([^"\']+)["\']\s*/?>',
        re.IGNORECASE | re.DOTALL,
    )
    _POLL_RE = re.compile(
        r'<poll(?:\s+title=["\'](?P<attr_title>[^"\']+)["\'])?\s*>(?P<body>.*?)</poll>',
        re.IGNORECASE | re.DOTALL,
    )
    _EFFECT_RE = re.compile(
        r'<(?:effect:(?P<colon_eff>[a-zA-Z0-9_]+)|effect(?:\s+(?P<attrs>[^>]*))?)\s*>(?P<text>.*?)</(?:effect(?::[a-zA-Z0-9_]+)?)>|'
        r'<(?:effect:(?P<prefix_colon>[a-zA-Z0-9_]+)|effect\s+name=["\'](?P<prefix_name>[^"\']+)["\']|effect\s+type=["\'](?P<prefix_type>[^"\']+)["\']|effect\s+(?P<prefix_bare>[a-zA-Z0-9_]+))\s*/?>',
        re.IGNORECASE | re.DOTALL,
    )
    _CALENDAR_RE = re.compile(
        r'<(?:calendar|calendar_event|event|schedule)(?:\s+(?P<attrs>[^>]*?))?\s*>(?P<body>.*?)</(?:calendar|calendar_event|event|schedule)>|'
        r'<(?:calendar|calendar_event|event|schedule)(?:\s+(?P<self_attrs>(?:[^"\'/>]|"[^"]*"|\'[^\']*\')*?))?\s*/?>',
        re.IGNORECASE | re.DOTALL,
    )
    _MAP_RE = re.compile(
        r'<(?:map|location)(?:\s+(?P<attrs>[^>]*))?\s*>(?P<body>.*?)</(?:map|location)>|<(?:map|location)(?:\s+(?P<self_attrs>(?:[^"\'/>]|"[^"]*"|\'[^\']*\')*?))?\s*/>',
        re.IGNORECASE | re.DOTALL,
    )
    _APPLE_MAPS_URL_RE = re.compile(
        r'https?://(?:maps\.apple\.com|maps\.google\.com)[^\s<>"\'\)]+',
        re.IGNORECASE,
    )
    _SHORTCUTS_URL_RE = re.compile(
        r'shortcuts://[^\r\n<>"\'\)]+',
        re.IGNORECASE,
    )
    _APPLE_MUSIC_URL_RE = re.compile(
        r'https?://(?:music|podcasts)\.apple\.com/[^\s<>"\'\)]+',
        re.IGNORECASE,
    )
    _SPOILER_RE = re.compile(
        r'<spoiler>(?P<text>.*?)</spoiler>|(?<!\|)\|\|(?!\|)(?P<pipe_text>.+?)\|\|',
        re.IGNORECASE | re.DOTALL,
    )
    _BOILERPLATE_PATTERNS = [
        re.compile(r'(?:[🌦️🎬📖]?\s*)?(?:天气胶囊|天气卡片|电影卡片|影视卡片|电影档案|单词卡片|词典卡片|词汇卡片)(?:已|给你)?(?:生成好?|备好|整理好|做好)啦?[～！。:，,\s]*', re.IGNORECASE),
        re.compile(r'已为你?生成(?:天气|电影|影视|美剧|单词|词典).*?卡片[～！。:，,\s]*', re.IGNORECASE),
        re.compile(r'名片卡片(?:给你)?生成好啦[，,、\s]*点击[^，。！\n]*?(?:拨打|存入)[^，。！\n]*[～！。]?', re.IGNORECASE),
        re.compile(r'投票卡片(?:给你)?做好了[，,、\s]*戳选项[^，。！:\n]*[～！。:]?', re.IGNORECASE),
        re.compile(r'原生日程卡片已生成[，,、\s]*点(?:一下|击)[^，。！\n]*?存入[^，。！\n]*[～！。]?', re.IGNORECASE),
        re.compile(r'[📅📇📍]?\s*已为你?生成.*?卡片[，,、\s]*点击即可[^，。！:\n]*[～！。:]?', re.IGNORECASE),
        re.compile(r'(?:给你)?做成\s*(?:Apple\s*HIG\s*)?(?:视网膜|高清|对比)?(?:长图|表格)啦?[:：]?', re.IGNORECASE),
        re.compile(r'原生地图卡片给你放这[，,、\s]*点开能直接[^，。！:\n]*[～！。:]?', re.IGNORECASE),
        re.compile(r'(?:想去哪[种个]|需要的话)[，,、\s]*我?直接把地图(?:导航)?卡片给你甩过来[～！。]?', re.IGNORECASE),
        re.compile(r'答案给你用隐形墨水遮好啦[，,、\s]*猜完刮开[^，。！:\n]*[～！。:👀\s]*', re.IGNORECASE),
        re.compile(r'(?:睡前压轴)?全屏大烟花给你放上啦[！!～]?', re.IGNORECASE),
        re.compile(r'点[击一下]卡片(?:即可|可以|直接).*?[存入保存添加查看导航拨打][^，。！\n]*[～！。]?', re.IGNORECASE),
        re.compile(r'点击(?:上面|下方|这里)的?卡片(?:即可|可以|直接)?[^，。！\n]*[～！。]?', re.IGNORECASE),
        re.compile(r'(?:和|的)?(?:具体)?(?:路线|地图)?卡片[？?～！。]?', re.IGNORECASE),
        re.compile(r'.*?(?:土区|国区|Apple\s*Music|播客|音乐|歌单)?(?:搜索直达|歌单|播放器)?(?:给你)?(?:备好|生成好|整理好)啦?[，,、\s]*点(?:开|击)?(?:就能|即可|直接)?(?:直接)?(?:拉起|打开)?(?:大图|原生)?(?:播放器|卡片)?(?:试听|收听|播放)?[:：]?', re.IGNORECASE),
        re.compile(r'.*?(?:搜索直达|大图播放器).*?[:：]?', re.IGNORECASE),
    ]

    @classmethod
    def _prune_robotic_boilerplate(cls, text: str) -> str:
        if not text or not isinstance(text, str):
            return ""
        res = text
        matched_any = False
        for p in cls._BOILERPLATE_PATTERNS:
            if p.search(res):
                res = p.sub("", res)
                matched_any = True
        if matched_any:
            res = re.sub(r'[\s:：，,、-]+$', '', res)
        return res.strip()
    _CONTACT_RE = re.compile(
        r'<(?:contact|vcard|card)(?:\s+(?P<attrs>[^>]*?))?\s*>(?P<body>.*?)</(?:contact|vcard|card)>|'
        r'<(?:contact|vcard|card)(?:\s+(?P<self_attrs>(?:[^"\'/>]|"[^"]*"|\'[^\']*\')*?))?\s*/>',
        re.IGNORECASE | re.DOTALL,
    )
    _IMAGE_TAG_RE = re.compile(
        r'<(?:image|img|photo|media|meme)(?:\s+(?P<attrs>[^>]*?))?\s*>(?P<body>.*?)</(?:image|img|photo|media|meme)>|'
        r'<(?:image|img|photo|media|meme)(?:\s+(?P<self_attrs>(?:[^"\'/>]|"[^"]*"|\'[^\']*\')*?))?\s*/>',
        re.IGNORECASE | re.DOTALL,
    )
    _MEDIA_DIRECTIVE_RE = re.compile(
        r'(?P<pre>[\r\n\s>]|^)(?P<tag>(?:[`*_]{0,3})(?:MEDIA|IMAGE|FILE):[ \t]*'
        r'(?:"(?P<qpath>[^\r\n"]+)"|\'(?P<sqpath>[^\r\n\']+)\'|`(?P<btpath>[^\r\n`]+)`|(?P<path>[^\r\n<>]+?))'
        r'[`"\'*_]*[ \t]*)(?=(?:[\r\n]|$|<))',
        re.IGNORECASE,
    )
    _CHEAT_SHEET_RE = re.compile(
        r'<(?:cheat_sheet|visual_table|sheet)(?:\s+(?P<attrs>[^>]*?))?\s*>(?P<body>.*?)</(?:cheat_sheet|visual_table|sheet)>',
        re.IGNORECASE | re.DOTALL,
    )
    _ACTION_RE = re.compile(
        r'<(?:action|shortcut|deeplink)(?:\s+(?P<attrs>[^>]*?))?\s*>(?P<body>.*?)</(?:action|shortcut|deeplink)>|'
        r'<(?:action|shortcut|deeplink)(?:\s+(?P<self_attrs>(?:[^"\'/>]|"[^"]*"|\'[^\']*\')*?))?\s*/>',
        re.IGNORECASE | re.DOTALL,
    )
    _EFFECT_ALIAS_MAP = {
        "invisible_ink": "invisible", "ink": "invisible", "hidden": "invisible", "secret": "invisible",
        "firework": "fireworks", "laser": "lasers", "balloon": "balloons",
        "sparkle": "sparkles", "hearts": "heart", "love": "heart",
        "impact": "slam", "shout": "loud", "whisper": "gentle",
    }
    _CODE_BLOCK_RE = re.compile(
        r'```(?P<lang>[a-zA-Z0-9_\-\+]*)\r?\n(?P<code>.*?)```',
        re.DOTALL,
    )
    _EXT_MAP = {
        "python": "py", "py": "py", "javascript": "js", "js": "js", "typescript": "ts", "ts": "ts",
        "bash": "sh", "sh": "sh", "shell": "sh", "zsh": "sh", "json": "json", "html": "html",
        "css": "css", "sql": "sql", "yaml": "yaml", "yml": "yml", "rust": "rs", "cpp": "cpp",
        "c": "c", "go": "go", "java": "java", "ruby": "rb", "php": "php", "swift": "swift",
    }
    _EMOJI_NAME_MAP = {
        "love": "❤️", "heart": "❤️", "thanks": "❤️", "thank": "❤️",
        "like": "👍", "thumbsup": "👍", "thumbs_up": "👍", "ok": "👍",
        "dislike": "👎", "thumbsdown": "👎", "thumbs_down": "👎",
        "haha": "😂", "laugh": "😂", "lol": "😂", "joy": "😂",
        "exclamation": "‼️", "shock": "‼️", "emphasize": "‼️", "wow": "‼️",
        "question": "❓", "confused": "❓", "what": "❓",
    }

    def __init__(self, paragraph_fallback: bool = True, isolate_urls: bool = False) -> None:
        self._buffer: str = ""
        self._in_code_block: bool = False
        self._active_code_lang: str = ""
        self._pending_effect: Optional[str] = None
        self._has_emitted_map: bool = False
        self._has_emitted_poll: bool = False
        self.paragraph_fallback: bool = paragraph_fallback
        self.isolate_urls: bool = isolate_urls

    @property
    def buffer(self) -> str:
        return self._buffer

    @property
    def in_code_block(self) -> bool:
        return self._in_code_block

    @property
    def active_code_lang(self) -> str:
        return self._active_code_lang

    @classmethod
    def _normalize_tapback_emoji(cls, raw: str) -> Optional[str]:
        raw = raw.strip()
        if not raw:
            return None
        lower = raw.lower()
        return cls._EMOJI_NAME_MAP.get(lower, raw)

    def feed(self, delta: str) -> List[str]:
        """Feed a streaming chunk/delta and return list of fully ready bubbles."""
        self._buffer += delta
        return self._extract_ready_bubbles(is_finish=False)

    def finish(self, exception_occurred: bool = False) -> List[str]:
        """Finalize parsing at the end of streaming or upon exception."""
        ready = self._extract_ready_bubbles(is_finish=True)
        if exception_occurred:
            # Discard residual unclosed buffer upon fatal stream exception
            self._buffer = ""
            self._in_code_block = False
            self._active_code_lang = ""
            self._pending_effect = None
            return ready

        # Check for unclosed <tapback> tag in remaining buffer
        unclosed_tap = re.search(
            r'<(?:tapback|reaction)(?:\s+emoji=["\']([^"\']+)["\'])?\s*>([^<]*)$',
            self._buffer,
            re.IGNORECASE,
        )
        if unclosed_tap and not self._is_inside_code_block(self._buffer[:unclosed_tap.start()]):
            raw_emoji = unclosed_tap.group(1) or unclosed_tap.group(2) or ""
            clean_emoji = self._normalize_tapback_emoji(raw_emoji)
            pre = self._buffer[:unclosed_tap.start()].strip()
            self._buffer = ""
            if pre:
                ready.extend(self._emit_bubble(pre))
            if clean_emoji:
                ready.append(f"TAPBACK:{clean_emoji}")

        rem = self._buffer.strip()
        self._buffer = ""

        if rem:
            rem = self._strip_dangling_control_tags(rem)
            if rem:
                if self.paragraph_fallback and "\n\n" in rem and not self._is_inside_code_block(rem):
                    # Cleanly split leftover paragraphs into individual bubbles
                    paras = [p.strip() for p in re.split(r'\n\s*\n', rem) if p.strip()]
                    for p in paras:
                        ready.extend(self._emit_bubble(p))
                else:
                    ready.extend(self._emit_bubble(rem))

        # Reset cross-turn parser state
        self._in_code_block = False
        self._active_code_lang = ""
        self._pending_effect = None
        self._has_emitted_poll = False
        return ready

    def _find_matching_bubble_close(self, buffer: str, open_pos: int) -> int:
        """Find the matching </bubble> for <bubble> at open_pos, respecting tag nesting."""
        idx = open_pos + len(self._OPEN_TAG)
        depth = 1
        while idx < len(buffer):
            next_open = buffer.find(self._OPEN_TAG, idx)
            next_close = buffer.find(self._CLOSE_TAG, idx)
            if next_close == -1:
                return -1
            if next_open != -1 and next_open < next_close:
                depth += 1
                idx = next_open + len(self._OPEN_TAG)
            else:
                depth -= 1
                if depth == 0:
                    return next_close
                idx = next_close + len(self._CLOSE_TAG)
        return -1

    def _balance_and_track_fences(self, content: str) -> str:
        """Auto-balance code fences for a single bubble while updating cross-bubble state."""
        text = content
        if self._in_code_block:
            text = f"```{self._active_code_lang}\n" + text

        lines = text.splitlines()
        in_code = False
        current_lang = ""
        for l in lines:
            s = l.strip()
            fence_idx = s.find("```")
            if fence_idx != -1:
                if not in_code:
                    in_code = True
                    rest = s[fence_idx + 3:].strip()
                    current_lang = rest.split()[0] if rest else ""
                else:
                    in_code = False
                    current_lang = ""

        if in_code:
            text = text.rstrip() + "\n```"
            self._in_code_block = True
            self._active_code_lang = current_lang
        else:
            self._in_code_block = False
            self._active_code_lang = ""

        return text

    def _strip_dangling_control_tags(self, text: str) -> str:
        """Strip incomplete dangling tags at stream end while protecting code blocks."""
        cleaned = re.sub(r'</?b(u(b(b(l(e)?)?)?)?)?$', '', text, flags=re.IGNORECASE)
        cleaned = re.sub(r'<{1,3}b(u(b(b(l(e)?)?)?)?)?>{0,3}$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'</?t(a(p(b(a(c(k)?)?)?)?)?)?$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'</?r(e(a(c(t(i(o(n)?)?)?)?)?)?)?$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'</?p(o(l(l)?)?)?$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'</?e(f(f(e(c(t)?)?)?)?)?$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'</?c(a(l(e(n(d(a(r)?)?)?)?)?)?)?$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'</?(?:calendar_event|event|schedule)[^>]*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'<effect:[^>]*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'</?m(a(p)?)?$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'</?l(o(c(a(t(i(o(n)?)?)?)?)?)?)?$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'</?s(p(o(i(l(e(r)?)?)?)?)?)?$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'</?(?:contact|vcard|card)[^>]*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'</?(?:image|img|photo|media|meme)[^>]*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'(?:^|[\r\n\s>])(?:[`*_]{0,3})(?:MEDIA|IMAGE|FILE):[ \t]*[`"\'*_]{0,3}$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'</?(?:cheat_sheet|visual_table|sheet)[^>]*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'</?(?:action|shortcut|deeplink)[^>]*$', '', cleaned, flags=re.IGNORECASE)
        return cleaned.strip()

    @staticmethod
    def _parse_tag_attrs(attr_str: str) -> dict[str, str]:
        if not attr_str:
            return {}
        matches = re.findall(r'([a-zA-Z0-9_\-]+)\s*=\s*["\']([^"\']*)["\']', attr_str)
        return {k.lower(): v for k, v in matches}

    @classmethod
    def _resolve_media_directive(cls, raw_path: str, caption: str = "", delay: float = 1.5) -> Optional[str]:
        if not raw_path or not isinstance(raw_path, str):
            return None
        p = raw_path.strip(" \t\r\n`\"'").strip()
        if not p:
            return None

        md_match = re.match(r'!?\[.*?\]\((.+?)\)', p)
        if md_match:
            p = md_match.group(1).strip(" \t\r\n`\"'").strip()

        if p.lower().startswith("file://"):
            from urllib.parse import unquote
            p = unquote(p[7:].strip())

        if not os.path.isabs(p) and not p.startswith(('http://', 'https://')):
            try:
                from hermes_constants import get_hermes_home
                cache_dir = get_hermes_home() / "cache"
                cand_cache = cache_dir / p
                if cand_cache.is_file():
                    p = str(cand_cache)
            except Exception:
                pass

        if not p.startswith(('http://', 'https://')):
            p = os.path.normpath(p)
            if not os.path.isfile(p):
                return None

        ext = os.path.splitext(p)[1].lower()
        image_exts = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.heic', '.tiff')
        if ext in image_exts or p.startswith(('http://', 'https://')):
            payload = json.dumps({"path": p, "caption": caption, "delay": delay}, ensure_ascii=False)
            return f"IMAGE:{payload}"
        else:
            return f"FILE:{p}"

    @staticmethod
    def _generate_vcf(
        name: str,
        phone: str = "",
        email: str = "",
        org: str = "",
        title: str = "",
        address: str = "",
        note: str = "",
    ) -> Optional[str]:
        clean_name = name.strip() or "新联系人"
        lines = [
            "BEGIN:VCARD",
            "VERSION:3.0",
            "PRODID:-//Hermes Agent//iMessage Contact Card//CN",
            f"FN:{clean_name}",
            f"N:;{clean_name};;;",
        ]
        if org:
            lines.append(f"ORG:{org.strip()}")
        if title:
            lines.append(f"TITLE:{title.strip()}")
        if phone:
            clean_phone = re.sub(r"[^\d\+\-\s]", "", phone.strip())
            lines.append(f"TEL;TYPE=CELL,VOICE:{clean_phone}")
        if email:
            lines.append(f"EMAIL;TYPE=INTERNET,WORK:{email.strip()}")
        if address:
            lines.append(f"ADR;TYPE=WORK:;;{address.strip()};;;;")
        if note:
            lines.append(f"NOTE:{note.strip()}")
        lines.append("END:VCARD")
        lines.append("")

        vcf_content = "\r\n".join(lines)
        h = hashlib.sha256(vcf_content.encode("utf-8")).hexdigest()[:8]
        safe_name = re.sub(r'[\\/:*?"<>|\r\n\t]+', '', clean_name).strip()
        safe_name = re.sub(r'\s+', ' ', safe_name)
        safe_name = safe_name[:40].strip(' ._') or "联系人"
        try:
            from hermes_constants import get_hermes_home
            scratch_dir = str(get_hermes_home() / "cache" / "contacts")
        except Exception:
            scratch_dir = os.path.expanduser("~/.hermes/cache/contacts")
        target_dir = os.path.join(scratch_dir, h)
        try:
            os.makedirs(target_dir, exist_ok=True)
            file_path = os.path.join(target_dir, f"{safe_name}.vcf")
            with open(file_path, "w", encoding="utf-8") as fp:
                fp.write(vcf_content)
            return file_path
        except Exception:
            return None

    @staticmethod
    def _generate_ics(title: str, start_str: str, end_str: str = "", location: str = "", description: str = "") -> Optional[str]:
        def parse_dt(s: str) -> Optional[datetime]:
            s = s.strip()
            try:
                return datetime.fromisoformat(s)
            except Exception:
                pass
            formats = [
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
                "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y/%m/%d",
                "%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M",
            ]
            for fmt in formats:
                try:
                    return datetime.strptime(s, fmt)
                except ValueError:
                    pass
            return None

        dt_start = parse_dt(start_str) if start_str else None
        if not dt_start:
            now = datetime.now()
            dt_start = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

        dt_end = parse_dt(end_str) if end_str else None
        if not dt_end or dt_end <= dt_start:
            dt_end = dt_start + timedelta(hours=1)

        fmt_ics = "%Y%m%dT%H%M%S"
        if dt_start.tzinfo is not None:
            start_ics = dt_start.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        else:
            start_ics = dt_start.strftime(fmt_ics)

        if dt_end.tzinfo is not None:
            end_ics = dt_end.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        else:
            end_ics = dt_end.strftime(fmt_ics)

        now_ics = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        uid = f"{uuid.uuid4().hex[:12]}@hermes-calendar"

        def escape_ics(val: str) -> str:
            return val.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

        clean_title = title.strip() or "新日程"
        ics_content = (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//Hermes Agent//iMessage Calendar//CN\r\n"
            "CALSCALE:GREGORIAN\r\n"
            "METHOD:PUBLISH\r\n"
            "BEGIN:VEVENT\r\n"
            f"UID:{uid}\r\n"
            f"DTSTAMP:{now_ics}\r\n"
            f"DTSTART:{start_ics}\r\n"
            f"DTEND:{end_ics}\r\n"
            f"SUMMARY:{escape_ics(clean_title)}\r\n"
        )
        if description:
            ics_content += f"DESCRIPTION:{escape_ics(description.strip())}\r\n"
        if location:
            ics_content += f"LOCATION:{escape_ics(location.strip())}\r\n"

        ics_content += (
            "STATUS:CONFIRMED\r\n"
            "BEGIN:VALARM\r\n"
            "TRIGGER:-PT15M\r\n"
            "ACTION:DISPLAY\r\n"
            f"DESCRIPTION:提醒: {escape_ics(clean_title)}\r\n"
            "END:VALARM\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )

        h = hashlib.sha256(ics_content.encode("utf-8")).hexdigest()[:8]
        safe_name = re.sub(r'[\\/:*?"<>|\r\n\t]+', '', clean_title).strip()
        safe_name = re.sub(r'\s+', ' ', safe_name)
        safe_name = safe_name[:40].strip(' ._') or "日程"
        try:
            from hermes_constants import get_hermes_home
            scratch_dir = str(get_hermes_home() / "cache" / "scratch" / "events")
        except Exception:
            scratch_dir = os.path.expanduser("~/.hermes/cache/scratch/events")
        target_dir = os.path.join(scratch_dir, h)
        try:
            os.makedirs(target_dir, exist_ok=True)
            file_path = os.path.join(target_dir, f"{safe_name}.ics")
            with open(file_path, "w", encoding="utf-8") as fp:
                fp.write(ics_content)
            return file_path
        except Exception:
            return None

    def _is_inside_code_block(self, text: str) -> bool:
        """Check if *text* currently ends inside an open markdown code block."""
        in_code = self._in_code_block
        for line in text.splitlines():
            if "```" in line:
                in_code = not in_code
        return in_code

    @staticmethod
    def _encode_custom_schemes(text: str) -> str:
        """Ensure custom URL schemes (shortcuts://, maps://) have properly percent-encoded query parameters for iOS."""
        def _sub(m: re.Match) -> str:
            raw = m.group(0).strip()
            if not any(ord(c) > 127 for c in raw) and " " not in raw:
                return raw
            from urllib.parse import urlsplit, parse_qsl, quote, urlunsplit
            try:
                parsed = urlsplit(raw)
                if not parsed.query:
                    return raw
                pairs = parse_qsl(parsed.query, keep_blank_values=True)
                encoded_query = "&".join(f"{quote(k)}={quote(v, safe=',+')}" for k, v in pairs)
                return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, encoded_query, parsed.fragment))
            except Exception:
                return raw
        return re.sub(r'(?:(?:shortcuts|maps|mobilenotes)://|https?://(?:maps\.apple\.com|maps\.google\.com|(?:music|podcasts)\.apple\.com)/)[^\r\n<>\'\"()]+', _sub, text)

    @classmethod
    def _normalize_apple_media_url(cls, url: str) -> str:
        """Ensure Apple Music and Apple Podcasts URLs target the Turkey storefront (/tr/) and have percent-encoded query params."""
        if not url:
            return url
        clean = url.strip()
        m = re.match(r'^(https?://(?:music|podcasts)\.apple\.com)(?:/([a-zA-Z]{2}))?(/.*)?$', clean, re.IGNORECASE)
        if m:
            base = m.group(1)
            rest = m.group(3) or ""
            clean = f"{base}/tr{rest}"
        return cls._encode_custom_schemes(clean).strip()

    def _split_standalone_urls(self, text: str) -> List[str]:
        """Split text so bare URLs (or markdown links) become their own discrete bubbles for iMessage Rich Link Previews."""
        if not self.isolate_urls or "```" in text or self._in_code_block:
            return [text]

        text = self._encode_custom_schemes(text)

        # Expand markdown links [text](url) -> "text\nurl"
        def _expand_md(match):
            title = match.group("text").strip()
            url = match.group("url").strip().rstrip(self._TRAILING_PUNCT)
            if title:
                return f"{title}\n{url}\n"
            return f"\n{url}\n"

        expanded = self._MD_LINK_RE.sub(_expand_md, text)

        parts: List[str] = []
        last_idx = 0

        for m in self._BARE_URL_RE.finditer(expanded):
            start, end = m.span()
            raw_url = m.group(0)
            clean_url = raw_url.rstrip(self._TRAILING_PUNCT)
            trailing_punct = raw_url[len(clean_url):]

            pre = expanded[last_idx:start].strip()
            if pre.endswith(("（", "(", "【", "[")):
                pre = pre[:-1].strip()
            if pre:
                parts.append(pre)

            if clean_url:
                if self._has_emitted_map and ("maps.apple.com" in clean_url or "maps.google.com" in clean_url):
                    continue
                if "music.apple.com" in clean_url or "podcasts.apple.com" in clean_url:
                    if "/search?" in clean_url or "/search/" in clean_url:
                        continue
                    clean_url = self._normalize_apple_media_url(clean_url)
                parts.append(clean_url)

            last_idx = end - len(trailing_punct)

        tail = expanded[last_idx:].strip()
        if tail.startswith(("）", ")", "】", "]")):
            tail = tail[1:].strip()
        tail = tail.lstrip(".,;:!?，。！？；：、 ")
        if tail:
            parts.append(tail)

        return parts or [text]

    def _offload_code_blocks(self, text: str) -> List[str]:
        """If a bubble contains a large code block (>15 lines), offload it to a scratch file attachment."""
        matches = list(self._CODE_BLOCK_RE.finditer(text))
        if not matches:
            return [text]

        file_items: List[str] = []
        replaced = text
        for m in reversed(matches):
            lang = (m.group("lang") or "txt").strip()
            code = m.group("code")
            lines = code.splitlines()
            if len(lines) > 15:
                h = hashlib.sha256(code.encode("utf-8")).hexdigest()[:8]
                ext = self._EXT_MAP.get(lang.lower(), "txt")
                scratch_dir = os.path.expanduser(r"~\AppData\Local\hermes\cache\scratch")
                try:
                    os.makedirs(scratch_dir, exist_ok=True)
                    filename = f"snippet_{h}.{ext}"
                    file_path = os.path.join(scratch_dir, filename)
                    with open(file_path, "w", encoding="utf-8") as fp:
                        fp.write(code)

                    preview = "\n".join(lines[:5])
                    omitted = len(lines) - 5
                    sub = f"```{lang}\n{preview}\n# ... (已省略其余 {omitted} 行代码，完整脚本见下方附件)\n```"
                    start, end = m.span()
                    replaced = replaced[:start] + sub + replaced[end:]
                    file_items.append(f"FILE:{file_path}")
                except Exception:
                    pass

        return [replaced] + file_items

    def _process_embedded_spoilers(self, text: str) -> List[str]:
        if "```" in text or self._is_inside_code_block(text):
            return [text]

        results: List[str] = []
        last_idx = 0
        for m in self._SPOILER_RE.finditer(text):
            start, end = m.span()
            pre = text[last_idx:start].strip()
            if pre:
                results.append(pre)
            spoiler_content = (m.group("text") or m.group("pipe_text") or "").strip()
            if spoiler_content:
                payload = json.dumps({"effect": "invisible", "text": spoiler_content}, ensure_ascii=False)
                results.append(f"EFFECT:{payload}")
            last_idx = end
        post = text[last_idx:].strip()
        if post:
            results.append(post)
        return results or [text]

    def _process_embedded_effects(self, text: str) -> List[str]:
        if "```" in text or self._is_inside_code_block(text):
            return [text]

        results: List[str] = []
        last_idx = 0
        for m in self._EFFECT_RE.finditer(text):
            start, end = m.span()
            pre = text[last_idx:start].strip()
            if pre:
                results.append(pre)
            colon_eff = m.group("colon_eff") if "colon_eff" in m.groupdict() else None
            prefix_colon = m.group("prefix_colon") if "prefix_colon" in m.groupdict() else None
            prefix_name = m.group("prefix_name") if "prefix_name" in m.groupdict() else None
            prefix_type = m.group("prefix_type") if "prefix_type" in m.groupdict() else None
            prefix_bare = m.group("prefix_bare") if "prefix_bare" in m.groupdict() else None
            attrs_str = m.group("attrs") if "attrs" in m.groupdict() else None

            eff_name = colon_eff or prefix_colon or prefix_name or prefix_type or prefix_bare
            if not eff_name:
                attrs = self._parse_tag_attrs(attrs_str or "")
                eff_name = attrs.get("name") or attrs.get("type") or "confetti"
            eff_name = self._EFFECT_ALIAS_MAP.get(eff_name.lower(), eff_name.lower())
            eff_text = (m.group("text") or "").strip() if "text" in m.groupdict() and m.group("text") else ""

            if not eff_text:
                tail = text[end:].strip()
                if tail:
                    payload = json.dumps({"effect": eff_name, "text": tail}, ensure_ascii=False)
                    results.append(f"EFFECT:{payload}")
                    last_idx = len(text)
                    break
            else:
                payload = json.dumps({"effect": eff_name, "text": eff_text}, ensure_ascii=False)
                results.append(f"EFFECT:{payload}")
            last_idx = end
        post = text[last_idx:].strip()
        if post:
            results.append(post)
        return results or [text]

    def _process_embedded_calendars(self, text: str) -> List[str]:
        if "```" in text or self._is_inside_code_block(text):
            return [text]

        results: List[str] = []
        last_idx = 0
        for m in self._CALENDAR_RE.finditer(text):
            start, end = m.span()
            pre = text[last_idx:start].strip()
            if pre:
                results.append(pre)
            attrs_str = m.group("attrs") or m.group("self_attrs") or ""
            attrs = self._parse_tag_attrs(attrs_str)
            title = attrs.get("title") or attrs.get("summary") or attrs.get("name") or "新日程"
            start_str = attrs.get("start") or attrs.get("time") or attrs.get("date") or attrs.get("start_time") or ""
            end_str = attrs.get("end") or attrs.get("end_time") or ""
            location = attrs.get("location") or attrs.get("loc") or attrs.get("place") or attrs.get("address") or ""
            description = attrs.get("description") or attrs.get("desc") or attrs.get("notes") or attrs.get("note") or ""
            body = (m.group("body") or "").strip() if "body" in m.groupdict() and m.group("body") else ""

            if body:
                results.append(body)
            ics_path = self._generate_ics(title, start_str, end_str, location, description)
            if ics_path:
                results.append(f"FILE:{ics_path}")
            last_idx = end
        post = text[last_idx:].strip()
        if post:
            results.append(post)
        return results or [text]

    def _process_embedded_maps(self, text: str) -> List[str]:
        if "```" in text or self._is_inside_code_block(text):
            return [text]

        results: List[str] = []
        last_idx = 0
        for m in self._MAP_RE.finditer(text):
            start, end = m.span()
            pre = text[last_idx:start].strip()
            if pre:
                results.append(pre)
            attrs_str = m.group("attrs") or m.group("self_attrs") or ""
            attrs = self._parse_tag_attrs(attrs_str)
            body = (m.group("body") or "").strip() if "body" in m.groupdict() and m.group("body") else ""
            query = attrs.get("query") or attrs.get("q") or attrs.get("name") or body or attrs.get("title") or ""
            title = attrs.get("title") or attrs.get("name") or query or "地图定位"
            address = attrs.get("address") or attrs.get("addr") or ""
            ll = attrs.get("ll") or attrs.get("coords") or attrs.get("location") or ""

            maps_url = f"https://maps.apple.com/?q={quote_plus(query, safe=',+')}"
            if address:
                maps_url += f"&address={quote_plus(address, safe=',+')}"
            if ll:
                maps_url += f"&ll={ll}"

            if body:
                results.append(body)
            results.append(maps_url)
            self._has_emitted_map = True
            last_idx = end
            trailing_match = re.match(r'^\s*(?:https?://(?:maps\.apple\.com|maps\.google\.com)[^\s<>"\'\)]*|maps://[^\s<>"\'\)]*)', text[last_idx:])
            if trailing_match:
                last_idx += trailing_match.end()
        post = text[last_idx:].strip()
        if post:
            results.append(post)
        return results or [text]

    def _process_embedded_contacts(self, text: str) -> List[str]:
        if "```" in text or self._is_inside_code_block(text):
            return [text]

        results: List[str] = []
        last_idx = 0
        for m in self._CONTACT_RE.finditer(text):
            start, end = m.span()
            pre = text[last_idx:start].strip()
            if pre:
                results.append(pre)
            attrs_str = m.group("attrs") or m.group("self_attrs") or ""
            attrs = self._parse_tag_attrs(attrs_str)
            body = (m.group("body") or "").strip() if "body" in m.groupdict() and m.group("body") else ""
            name = attrs.get("name") or attrs.get("fn") or attrs.get("title") or body or "联系人"
            phone = attrs.get("phone") or attrs.get("tel") or attrs.get("mobile") or ""
            email = attrs.get("email") or attrs.get("mail") or ""
            org = attrs.get("org") or attrs.get("company") or attrs.get("organization") or ""
            title = attrs.get("title") or attrs.get("role") or attrs.get("position") or ""
            address = attrs.get("address") or attrs.get("addr") or attrs.get("location") or ""
            note = attrs.get("note") or attrs.get("desc") or attrs.get("description") or ""

            if body:
                results.append(body)
            vcf_path = self._generate_vcf(name, phone, email, org, title, address, note)
            if vcf_path:
                results.append(f"FILE:{vcf_path}")
            last_idx = end
        post = text[last_idx:].strip()
        if post:
            results.append(post)
        return results or [text]

    def _process_embedded_cheat_sheets(self, text: str) -> List[str]:
        if "```" in text or self._is_inside_code_block(text):
            return [text]

        if not self._CHEAT_SHEET_RE.search(text):
            return [text]

        results: List[str] = []
        last_idx = 0
        for m in self._CHEAT_SHEET_RE.finditer(text):
            start, end = m.span()
            pre = text[last_idx:start].strip()
            if pre:
                results.append(pre)
            body = (m.group("body") or "").strip()
            if body:
                results.append(body)
            last_idx = end
        post = text[last_idx:].strip()
        if post:
            results.append(post)
        return results or [text]

    def _process_embedded_images(self, text: str) -> List[str]:
        if "```" in text or self._is_inside_code_block(text):
            return [text]

        results: List[str] = []
        last_idx = 0
        for m in self._IMAGE_TAG_RE.finditer(text):
            start, end = m.span()
            pre = text[last_idx:start].strip()
            if pre:
                results.append(pre)
            attrs_str = m.group("attrs") or m.group("self_attrs") or ""
            attrs = self._parse_tag_attrs(attrs_str)
            body = (m.group("body") or "").strip() if "body" in m.groupdict() and m.group("body") else ""
            img_path = attrs.get("path") or attrs.get("src") or attrs.get("url") or attrs.get("name") or body or ""
            caption = attrs.get("caption") or attrs.get("title") or ""
            try:
                delay = float(attrs.get("delay", 1.5))
            except (ValueError, TypeError):
                delay = 1.5

            norm_item = self._resolve_media_directive(img_path, caption=caption, delay=delay)
            if norm_item:
                results.append(norm_item)
            last_idx = end
        post = text[last_idx:].strip()
        if post:
            results.append(post)
        return results or [text]

    def _process_embedded_media_directives(self, text: str) -> List[str]:
        if "```" in text or self._is_inside_code_block(text):
            return [text]

        if not self._MEDIA_DIRECTIVE_RE.search(text):
            return [text]

        results: List[str] = []
        last_idx = 0
        for m in self._MEDIA_DIRECTIVE_RE.finditer(text):
            pre_str = m.group("pre") or ""
            tag_start = m.start() + len(pre_str)
            tag_end = m.end()
            pre = text[last_idx:tag_start].strip()
            if pre:
                results.append(pre)
            raw_path = m.group("qpath") or m.group("sqpath") or m.group("btpath") or m.group("path") or ""
            norm_item = self._resolve_media_directive(raw_path)
            if norm_item:
                results.append(norm_item)
            last_idx = tag_end
        post = text[last_idx:].strip()
        if post:
            results.append(post)
        return results or [text]

    def _process_embedded_actions(self, text: str) -> str:
        if "```" in text or self._is_inside_code_block(text):
            return text

        def _sub_action(m: re.Match) -> str:
            attrs_str = m.group("attrs") or m.group("self_attrs") or ""
            attrs = self._parse_tag_attrs(attrs_str)
            body = (m.group("body") or "").strip() if "body" in m.groupdict() and m.group("body") else ""
            title = attrs.get("title") or attrs.get("name") or body or "快捷操作"
            url = attrs.get("url") or attrs.get("link") or ""

            shortcut = attrs.get("shortcut") or attrs.get("shortcuts")
            shortcut_input = attrs.get("input") or attrs.get("text") or attrs.get("param") or ""
            from urllib.parse import quote
            if shortcut and not url:
                url = f"shortcuts://run-shortcut?name={quote(shortcut)}"
                if shortcut_input:
                    url += f"&input=text&text={quote(shortcut_input)}"

            map_dest = attrs.get("map") or attrs.get("navigate") or attrs.get("destination") or attrs.get("daddr")
            if map_dest and not url:
                url = f"maps://?daddr={quote(map_dest)}&dirflg=d"

            if attrs.get("reminder") or attrs.get("todo"):
                if not url:
                    url = "x-apple-reminderkit://"

            if attrs.get("note") or attrs.get("notes") or attrs.get("mobilenotes"):
                if not url:
                    url = "mobilenotes://"

            clean_url = url.strip()
            if clean_url:
                return f"\n\n👉 {title}：\n{clean_url}"
            return body or title

        return self._ACTION_RE.sub(_sub_action, text)

    def _emit_bubble(self, raw_text: str) -> List[str]:
        """Balance fences, offload large code blocks, unpack embedded effects/spoilers/cards, and isolate URLs."""
        balanced = self._balance_and_track_fences(raw_text)
        balanced = self._encode_custom_schemes(balanced)
        offloaded = self._offload_code_blocks(balanced)
        results: List[str] = []
        for item in offloaded:
            if item.startswith("FILE:") or item.startswith("TAPBACK:") or item.startswith("POLL:") or item.startswith("EFFECT:") or item.startswith("IMAGE:"):
                results.append(item)
                continue

            stage1 = self._process_embedded_effects(item)
            stage2: List[str] = []
            for s1 in stage1:
                if s1.startswith("EFFECT:") or s1.startswith("IMAGE:"):
                    stage2.append(s1)
                else:
                    stage2.extend(self._process_embedded_spoilers(s1))
            stage3: List[str] = []
            for s2 in stage2:
                if s2.startswith("EFFECT:") or s2.startswith("FILE:") or s2.startswith("IMAGE:"):
                    stage3.append(s2)
                else:
                    stage3.extend(self._process_embedded_calendars(s2))
            stage4: List[str] = []
            for s3 in stage3:
                if s3.startswith("EFFECT:") or s3.startswith("FILE:") or s3.startswith("IMAGE:"):
                    stage4.append(s3)
                else:
                    stage4.extend(self._process_embedded_maps(s3))
            stage5: List[str] = []
            for s4 in stage4:
                if s4.startswith("EFFECT:") or s4.startswith("FILE:") or s4.startswith("IMAGE:"):
                    stage5.append(s4)
                else:
                    stage5.extend(self._process_embedded_contacts(s4))
            stage6: List[str] = []
            for s5 in stage5:
                if s5.startswith("EFFECT:") or s5.startswith("FILE:") or s5.startswith("IMAGE:"):
                    stage6.append(s5)
                else:
                    stage6.extend(self._process_embedded_cheat_sheets(s5))
            stage7: List[str] = []
            for s6 in stage6:
                if s6.startswith("EFFECT:") or s6.startswith("FILE:") or s6.startswith("IMAGE:"):
                    stage7.append(s6)
                else:
                    stage7.extend(self._process_embedded_images(s6))
            stage7b: List[str] = []
            for s7 in stage7:
                if s7.startswith("EFFECT:") or s7.startswith("FILE:") or s7.startswith("IMAGE:"):
                    stage7b.append(s7)
                else:
                    stage7b.extend(self._process_embedded_media_directives(s7))
            stage8: List[str] = []
            for s7b in stage7b:
                if s7b.startswith("EFFECT:") or s7b.startswith("FILE:") or s7b.startswith("IMAGE:"):
                    stage8.append(s7b)
                else:
                    stage8.append(self._process_embedded_actions(s7b))

            for s8 in stage8:
                if s8.startswith("FILE:") or s8.startswith("TAPBACK:") or s8.startswith("POLL:") or s8.startswith("EFFECT:") or s8.startswith("IMAGE:"):
                    results.append(s8)
                else:
                    for item in self._split_standalone_urls(s8):
                        if item.startswith("http://") or item.startswith("https://") or item.startswith("maps://") or item.startswith("shortcuts://"):
                            results.append(item)
                        else:
                            cleaned = self._prune_robotic_boilerplate(item)
                            if cleaned:
                                results.append(cleaned)

        if self._pending_effect and results:
            for i, res in enumerate(results):
                if not (res.startswith("FILE:") or res.startswith("TAPBACK:") or res.startswith("POLL:") or res.startswith("EFFECT:")):
                    payload = json.dumps({"effect": self._pending_effect, "text": res}, ensure_ascii=False)
                    results[i] = f"EFFECT:{payload}"
                    self._pending_effect = None
                    break

        return results

    def _extract_ready_bubbles(self, is_finish: bool = False) -> List[str]:
        """Extract complete bubbles delimited by tags with chronological ordering and nesting-aware boundaries."""
        bubbles: List[str] = []

        while True:
            candidates = []

            m_tap = self._TAPBACK_RE.search(self._buffer)
            if m_tap and not self._is_inside_code_block(self._buffer[:m_tap.start()]):
                candidates.append((m_tap.start(), "tapback", m_tap))

            m_poll = self._POLL_RE.search(self._buffer)
            if m_poll and not self._is_inside_code_block(self._buffer[:m_poll.start()]):
                candidates.append((m_poll.start(), "poll", m_poll))

            m_cal = self._CALENDAR_RE.search(self._buffer)
            if m_cal and not self._is_inside_code_block(self._buffer[:m_cal.start()]):
                candidates.append((m_cal.start(), "calendar", m_cal))

            m_map = self._MAP_RE.search(self._buffer)
            if m_map and not self._is_inside_code_block(self._buffer[:m_map.start()]):
                candidates.append((m_map.start(), "map", m_map))

            m_eff = self._EFFECT_RE.search(self._buffer)
            if m_eff and not self._is_inside_code_block(self._buffer[:m_eff.start()]):
                candidates.append((m_eff.start(), "effect", m_eff))

            m_spoil = self._SPOILER_RE.search(self._buffer)
            if m_spoil and not self._is_inside_code_block(self._buffer[:m_spoil.start()]):
                candidates.append((m_spoil.start(), "spoiler", m_spoil))

            m_map_url = self._APPLE_MAPS_URL_RE.search(self._buffer)
            if m_map_url and not self._is_inside_code_block(self._buffer[:m_map_url.start()]):
                # Wait for trailing whitespace or stream end to ensure complete URL
                if m_map_url.end() < len(self._buffer) or is_finish:
                    candidates.append((m_map_url.start(), "apple_maps_url", m_map_url))

            m_sc_url = self._SHORTCUTS_URL_RE.search(self._buffer)
            if m_sc_url and not self._is_inside_code_block(self._buffer[:m_sc_url.start()]):
                if m_sc_url.end() < len(self._buffer) or is_finish:
                    candidates.append((m_sc_url.start(), "shortcuts_url", m_sc_url))

            m_act = self._ACTION_RE.search(self._buffer)
            if m_act and not self._is_inside_code_block(self._buffer[:m_act.start()]):
                candidates.append((m_act.start(), "action", m_act))

            m_music_url = self._APPLE_MUSIC_URL_RE.search(self._buffer)
            if m_music_url and not self._is_inside_code_block(self._buffer[:m_music_url.start()]):
                if m_music_url.end() < len(self._buffer) or is_finish:
                    candidates.append((m_music_url.start(), "apple_music_url", m_music_url))

            m_contact = self._CONTACT_RE.search(self._buffer)
            if m_contact and not self._is_inside_code_block(self._buffer[:m_contact.start()]):
                candidates.append((m_contact.start(), "contact", m_contact))

            m_img = self._IMAGE_TAG_RE.search(self._buffer)
            if m_img and not self._is_inside_code_block(self._buffer[:m_img.start()]):
                candidates.append((m_img.start(), "image", m_img))

            m_media = self._MEDIA_DIRECTIVE_RE.search(self._buffer)
            if m_media:
                pre_str = m_media.group("pre") or ""
                tag_start = m_media.start() + len(pre_str)
                tag_end = m_media.end()
                if not self._is_inside_code_block(self._buffer[:tag_start]):
                    if tag_end < len(self._buffer) or is_finish or self._buffer.endswith(('\n', '\r', '<', '>')):
                        candidates.append((tag_start, "media_directive", (m_media, tag_start, tag_end)))

            open_idx = self._buffer.find(self._OPEN_TAG)
            if open_idx != -1 and open_idx >= 2 and self._buffer[open_idx-2:open_idx+len(self._OPEN_TAG)+2] == self._SEP_MARKER:
                open_idx = -1
            if open_idx != -1 and not self._is_inside_code_block(self._buffer[:open_idx]):
                candidates.append((open_idx, "bubble_open", open_idx))

            sep_idx = self._buffer.find(self._SEP_MARKER)
            if sep_idx != -1 and not self._is_inside_code_block(self._buffer[:sep_idx]):
                candidates.append((sep_idx, "sep_marker", sep_idx))

            if not candidates:
                # Paragraph fallback if no tags exist
                if self.paragraph_fallback:
                    if re.search(r'</?[a-zA-Z]{0,10}$', self._buffer) or re.search(r'<{1,3}[a-zA-Z]{0,10}$', self._buffer):
                        break
                    # Strip leading newlines if buffer starts with them
                    stripped = self._buffer.lstrip("\r\n")
                    if len(stripped) < len(self._buffer):
                        self._buffer = stripped

                    nl_idx = self._buffer.find("\n\n")
                    if nl_idx != -1:
                        pre_nl = self._buffer[:nl_idx]
                        if not self._is_inside_code_block(pre_nl):
                            candidate_text = pre_nl.strip()
                            self._buffer = self._buffer[nl_idx + 2:].lstrip("\r\n")
                            if candidate_text:
                                bubbles.extend(self._emit_bubble(candidate_text))
                                continue
                break

            # Pick the earliest candidate in chronological document order
            candidates.sort(key=lambda c: c[0])
            start_pos, c_type, c_obj = candidates[0]

            pre = self._buffer[:start_pos]
            has_bubble_tags = (self._OPEN_TAG in self._buffer) or (self._SEP_MARKER in self._buffer)
            pre_clean = pre.strip()

            if c_type == "tapback":
                start, end = c_obj.span()
                attr1 = c_obj.group(1)
                body = c_obj.group(2)
                attr2 = c_obj.group(3)
                clean_emoji = self._normalize_tapback_emoji(attr1 or body or attr2 or "")
                self._buffer = self._buffer[end:]
                if pre_clean:
                    bubbles.extend(self._emit_bubble(pre_clean))
                if clean_emoji:
                    bubbles.append(f"TAPBACK:{clean_emoji}")
                continue

            elif c_type == "poll":
                self._has_emitted_poll = True
                start, end = c_obj.span()
                attr_title = c_obj.group("attr_title")
                body = c_obj.group("body") or ""
                opt_matches = re.findall(r'<option>(.*?)</option>', body, re.IGNORECASE | re.DOTALL)
                if opt_matches:
                    options = [o.strip() for o in opt_matches if o.strip()]
                elif "|" in body:
                    options = [o.strip() for o in body.split("|") if o.strip()]
                else:
                    options = [line.strip().lstrip("1234567890.-*• ") for line in body.splitlines() if line.strip()]
                title = (attr_title or "").strip() or "请选择"
                self._buffer = self._buffer[end:]
                if pre_clean:
                    bubbles.extend(self._emit_bubble(pre_clean))
                if options:
                    payload = json.dumps({"title": title, "options": options}, ensure_ascii=False)
                    bubbles.append(f"POLL:{payload}")
                continue

            elif c_type == "calendar":
                start, end = c_obj.span()
                attrs_str = c_obj.group("attrs") or c_obj.group("self_attrs") or ""
                attrs = self._parse_tag_attrs(attrs_str)
                title = attrs.get("title") or attrs.get("summary") or attrs.get("name") or "新日程"
                start_str = attrs.get("start") or attrs.get("time") or attrs.get("date") or attrs.get("start_time") or ""
                end_str = attrs.get("end") or attrs.get("end_time") or ""
                location = attrs.get("location") or attrs.get("loc") or attrs.get("place") or attrs.get("address") or ""
                description = attrs.get("description") or attrs.get("desc") or attrs.get("notes") or attrs.get("note") or ""
                body = (c_obj.group("body") or "").strip() if "body" in c_obj.groupdict() and c_obj.group("body") else ""

                self._buffer = self._buffer[end:]
                if pre_clean:
                    bubbles.extend(self._emit_bubble(pre_clean))

                if body:
                    bubbles.extend(self._emit_bubble(body))
                ics_path = self._generate_ics(title, start_str, end_str, location, description)
                if ics_path:
                    bubbles.append(f"FILE:{ics_path}")
                continue

            elif c_type == "map":
                start, end = c_obj.span()
                attrs_str = c_obj.group("attrs") or c_obj.group("self_attrs") or ""
                attrs = self._parse_tag_attrs(attrs_str)
                body = (c_obj.group("body") or "").strip() if "body" in c_obj.groupdict() and c_obj.group("body") else ""
                query = attrs.get("query") or attrs.get("q") or attrs.get("name") or body or attrs.get("title") or ""
                title = attrs.get("title") or attrs.get("name") or query or "地图定位"
                address = attrs.get("address") or attrs.get("addr") or ""
                ll = attrs.get("ll") or attrs.get("coords") or attrs.get("location") or ""

                self._buffer = self._buffer[end:]

                if pre_clean:
                    bubbles.extend(self._emit_bubble(pre_clean))

                maps_url = f"https://maps.apple.com/?q={quote_plus(query, safe=',+')}"
                if address:
                    maps_url += f"&address={quote_plus(address, safe=',+')}"
                if ll:
                    maps_url += f"&ll={ll}"

                if body:
                    bubbles.extend(self._emit_bubble(body))
                bubbles.append(maps_url)
                self._has_emitted_map = True
                continue

            elif c_type == "effect":
                start, end = c_obj.span()
                colon_eff = c_obj.group("colon_eff") if "colon_eff" in c_obj.groupdict() else None
                prefix_colon = c_obj.group("prefix_colon") if "prefix_colon" in c_obj.groupdict() else None
                prefix_name = c_obj.group("prefix_name") if "prefix_name" in c_obj.groupdict() else None
                prefix_type = c_obj.group("prefix_type") if "prefix_type" in c_obj.groupdict() else None
                prefix_bare = c_obj.group("prefix_bare") if "prefix_bare" in c_obj.groupdict() else None
                attrs_str = c_obj.group("attrs") if "attrs" in c_obj.groupdict() else None

                eff_name = colon_eff or prefix_colon or prefix_name or prefix_type or prefix_bare
                if not eff_name:
                    attrs = self._parse_tag_attrs(attrs_str or "")
                    eff_name = attrs.get("name") or attrs.get("type") or "confetti"
                eff_name = self._EFFECT_ALIAS_MAP.get(eff_name.lower(), eff_name.lower())
                eff_text = (c_obj.group("text") or "").strip() if "text" in c_obj.groupdict() and c_obj.group("text") else ""

                self._buffer = self._buffer[end:]
                if pre_clean:
                    bubbles.extend(self._emit_bubble(pre_clean))

                if eff_text:
                    payload = json.dumps({"effect": eff_name, "text": eff_text}, ensure_ascii=False)
                    bubbles.append(f"EFFECT:{payload}")
                else:
                    self._pending_effect = eff_name
                continue

            elif c_type == "spoiler":
                start, end = c_obj.span()
                spoiler_content = (c_obj.group("text") or c_obj.group("pipe_text") or "").strip()
                self._buffer = self._buffer[end:]
                if pre_clean:
                    bubbles.extend(self._emit_bubble(pre_clean))
                if spoiler_content:
                    payload = json.dumps({"effect": "invisible", "text": spoiler_content}, ensure_ascii=False)
                    bubbles.append(f"EFFECT:{payload}")
                continue

            elif c_type == "apple_maps_url":
                start, end = c_obj.span()
                raw_url = c_obj.group(0).rstrip(self._TRAILING_PUNCT)
                self._buffer = self._buffer[end:]
                if pre_clean and not has_bubble_tags:
                    bubbles.extend(self._emit_bubble(pre_clean))
                # If a map card was already emitted in this session turn, or if <map is pending in buffer, discard duplicate bare link!
                if self._has_emitted_map or "<map" in self._buffer:
                    continue
                if raw_url:
                    clean_maps = self._encode_custom_schemes(raw_url).strip()
                    bubbles.append(clean_maps)
                continue

            elif c_type == "shortcuts_url":
                start, end = c_obj.span()
                raw_url = c_obj.group(0).rstrip(self._TRAILING_PUNCT)
                self._buffer = self._buffer[end:]
                if pre_clean and not has_bubble_tags:
                    bubbles.extend(self._emit_bubble(pre_clean))
                if raw_url:
                    clean_sc = self._encode_custom_schemes(raw_url).strip()
                    bubbles.append(clean_sc)
                continue

            elif c_type == "action":
                start, end = c_obj.span()
                action_text = c_obj.group(0)
                self._buffer = self._buffer[end:]
                if pre_clean and not has_bubble_tags:
                    bubbles.extend(self._emit_bubble(pre_clean))
                processed = self._process_embedded_actions(action_text)
                if processed:
                    bubbles.extend(self._emit_bubble(processed))
                continue

            elif c_type == "apple_music_url":
                start, end = c_obj.span()
                raw_url = c_obj.group(0).rstrip(self._TRAILING_PUNCT)
                self._buffer = self._buffer[end:]
                if pre_clean and not has_bubble_tags:
                    bubbles.extend(self._emit_bubble(pre_clean))
                # Search URLs do not render player cards in iMessage; discard them
                if "/search?" in raw_url or "/search/" in raw_url:
                    continue
                if raw_url:
                    clean_music = self._normalize_apple_media_url(raw_url).strip()
                    bubbles.append(clean_music)
                continue

            elif c_type == "contact":
                start, end = c_obj.span()
                attrs_str = c_obj.group("attrs") or c_obj.group("self_attrs") or ""
                attrs = self._parse_tag_attrs(attrs_str)
                body = (c_obj.group("body") or "").strip() if "body" in c_obj.groupdict() and c_obj.group("body") else ""
                name = attrs.get("name") or attrs.get("fn") or attrs.get("title") or body or "联系人"
                phone = attrs.get("phone") or attrs.get("tel") or attrs.get("mobile") or ""
                email = attrs.get("email") or attrs.get("mail") or ""
                org = attrs.get("org") or attrs.get("company") or attrs.get("organization") or ""
                title = attrs.get("title") or attrs.get("role") or attrs.get("position") or ""
                address = attrs.get("address") or attrs.get("addr") or attrs.get("location") or ""
                note = attrs.get("note") or attrs.get("desc") or attrs.get("description") or ""

                self._buffer = self._buffer[end:]
                if pre_clean:
                    bubbles.extend(self._emit_bubble(pre_clean))

                if body:
                    bubbles.extend(self._emit_bubble(body))
                vcf_path = self._generate_vcf(name, phone, email, org, title, address, note)
                if vcf_path:
                    bubbles.append(f"FILE:{vcf_path}")
                continue

            elif c_type == "media_directive":
                m_match, tag_start, tag_end = c_obj
                raw_path = m_match.group("qpath") or m_match.group("sqpath") or m_match.group("btpath") or m_match.group("path") or ""
                self._buffer = self._buffer[tag_end:]
                if pre_clean:
                    bubbles.extend(self._emit_bubble(pre_clean))
                norm_item = self._resolve_media_directive(raw_path)
                if norm_item:
                    bubbles.append(norm_item)
                continue

            elif c_type == "image":
                start, end = c_obj.span()
                attrs_str = c_obj.group("attrs") or c_obj.group("self_attrs") or ""
                attrs = self._parse_tag_attrs(attrs_str)
                body = (c_obj.group("body") or "").strip() if "body" in c_obj.groupdict() and c_obj.group("body") else ""
                img_path = attrs.get("path") or attrs.get("src") or attrs.get("url") or attrs.get("name") or body or ""
                caption = attrs.get("caption") or attrs.get("title") or ""
                try:
                    delay = float(attrs.get("delay", 1.5))
                except (ValueError, TypeError):
                    delay = 1.5

                self._buffer = self._buffer[end:]
                if pre_clean:
                    bubbles.extend(self._emit_bubble(pre_clean))

                norm_item = self._resolve_media_directive(img_path, caption=caption, delay=delay)
                if norm_item:
                    bubbles.append(norm_item)
                continue

            elif c_type == "sep_marker":
                self._buffer = self._buffer[c_obj + len(self._SEP_MARKER):]
                if pre_clean:
                    bubbles.extend(self._emit_bubble(pre_clean))
                continue

            elif c_type == "bubble_open":
                close_idx = self._find_matching_bubble_close(self._buffer, c_obj)
                if close_idx != -1:
                    bubble_raw = self._buffer[c_obj + len(self._OPEN_TAG):close_idx].strip()
                    self._buffer = self._buffer[close_idx + len(self._CLOSE_TAG):]
                    is_uri_or_action = bool(re.search(r'[a-zA-Z0-9_\-\.]+:[^\s]+', pre_clean))
                    if pre_clean and (not has_bubble_tags or is_uri_or_action):
                        bubbles.extend(self._emit_bubble(pre_clean))
                    if bubble_raw:
                        bubbles.extend(self._emit_bubble(bubble_raw))
                    continue
                # Bubble open tag arrived, wait for stream to provide closing tag
                break

        return bubbles
