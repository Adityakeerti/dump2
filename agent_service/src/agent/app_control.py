"""App-control intents for the main voice agent.

The main agent can drive the citizen app: open screens, fly the map to a place, open a local
agent's chat, change language or voice, and fetch what the app shows (complaints, notices, events,
incidents). Parsing is rule-based (English, Hindi, Hinglish) so it is instant, offline and testable.

Data intents are still answered by their owning specialist (complaints -> complaint desk, notices /
events / incidents -> City Pulse); the main agent only adds the matching navigation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from src.agent.planner import TRACKING_RE


@dataclass
class AppIntent:
    kind: str  # navigate | focus_map | find_agent | preference | data
    params: dict[str, Any] = field(default_factory=dict)


_OPEN = r"(?:open|show|go to|take me to|navigate to|bring up|kholo|dikhao|par jao|पर जाओ|खोलो|दिखाओ)"
SCREENS = [
    ("settings", re.compile(rf"\b{_OPEN}\b.*\bsettings?\b|^\s*settings?\s*$|सेटिंग", re.I)),
    ("saved", re.compile(r"\b(saved|bookmark(?:ed|s)?)\s*(?:avatars?|agents?|list)?\b|सेव", re.I)),
    ("explore", re.compile(rf"\b{_OPEN}\b\s+(?:the\s+)?(?:city\s+)?map\b|\bexplore\b|नक्शा", re.I)),
    ("townhall", re.compile(r"\btown\s?hall\b|टाउनहॉल", re.I)),
    ("updates", re.compile(rf"\b{_OPEN}\b.*\bupdates?\b", re.I)),
    ("complaint_new", re.compile(r"\b(?:complaint|grievance)\s+form\b|\bnew\s+complaint\s+(?:form|screen)\b", re.I)),
]
DATA = [
    ("notices", re.compile(r"\bnotices?\b|\bannouncements?\b|\bcirculars?\b|सूचना|नोटिस", re.I), "updates"),
    ("incidents", re.compile(r"\bincidents?\b|घटना", re.I), "updates"),
    ("events", re.compile(r"\b(?:city\s+|civic\s+|upcoming\s+)?events?\b|\bwhat(?:'?s|\s+is)\s+(?:happening|on)\b"
                          r"|\bhappening\s+(?:in|around|this|today|tonight|near)\b|\bfestivals?\b|\bmelas?\b|\bconcerts?\b"
                          r"|\b(?:lit(?:erature)?\s*fest|marathon|meetups?)\b|कार्यक्रम|त्योहार|मेला", re.I), "townhall"),
    ("businesses", re.compile(r"\b(?:recommend|suggest|popular|best|good|nearby)\b.{0,30}\b(?:cafe|café|coffee|bakery|bakeries|"
                              r"restaurant|food|sweets?|mithai|book\s?(?:store|shop)s?|shops?|shopping|market|places?\s+to\s+eat|"
                              r"business(?:es)?)\b|\b(?:popular|local)\s+business(?:es)?\b|\bwhere\s+(?:can|should|to)\s+(?:i\s+)?"
                              r"(?:eat|shop|buy)\b|अच्छा\s+(?:कैफे|रेस्टोरेंट)|दुकान", re.I), "townhall"),
    ("complaints", re.compile(r"\b(?:my|all|active|open|pending|show|list)\b.{0,15}\b(?:complaints?|grievances?|tickets?)\b"
                              r"|मेरी\s+शिकायत", re.I), "townhall"),
]
FOCUS = re.compile(
    r"\b(?:show|find|locate|where\s+is|zoom\s+(?:in\s+)?to|fly\s+to)\s+(?:me\s+)?(?P<q>[A-Za-z][\w\s.'&-]{1,60}?)\s+on\s+(?:the\s+)?map\b"
    r"|\b(?:show|zoom|fly)\s+(?:the\s+)?map\s+(?:to|at|of)\s+(?P<q2>[A-Za-z][\w\s.'&-]{1,60})",
    re.I,
)
AGENT = re.compile(
    r"\b(?:talk|chat|speak|connect)\s+(?:to|with)\s+(?P<n>[A-Za-z][\w.]{1,30}(?:\s+[A-Z][\w.]{1,30})?)"
    r"|\bopen\s+(?P<n2>[A-Za-z][\w.]{1,30})'?s?\s+chat\b",
    re.I,
)
LANG_HI = re.compile(r"\b(?:switch|change|set)\b.{0,20}\bhindi\b|\bhindi\s+(?:me|mein)\b|हिंदी\s+में", re.I)
LANG_EN = re.compile(r"\b(?:switch|change|set)\b.{0,20}\benglish\b|\benglish\s+(?:me|mein)\b|अंग्रेज़ी\s+में", re.I)
VOICE_OFF = re.compile(r"\b(?:mute|stop\s+talking|be\s+quiet|turn\s+off\s+(?:the\s+)?(?:voice|sound|audio|speaker))\b|चुप", re.I)
VOICE_ON = re.compile(r"\b(?:unmute|turn\s+on\s+(?:the\s+)?(?:voice|sound|audio|speaker)|read\s+(?:it\s+)?(?:out|aloud))\b", re.I)
NOT_AGENT_NAMES = {"me", "you", "someone", "a", "the", "city", "sense", "police", "ambulance", "nagar"}


def parse(message: str) -> list[AppIntent]:
    text = message or ""
    intents: list[AppIntent] = []

    if LANG_HI.search(text):
        intents.append(AppIntent("preference", {"language": "hi"}))
    elif LANG_EN.search(text):
        intents.append(AppIntent("preference", {"language": "en"}))
    if VOICE_OFF.search(text):
        intents.append(AppIntent("preference", {"voice_auto_play": False}))
    elif VOICE_ON.search(text):
        intents.append(AppIntent("preference", {"voice_auto_play": True}))

    m = FOCUS.search(text)
    if m:
        intents.append(AppIntent("focus_map", {"query": (m.group("q") or m.group("q2")).strip(" .")}))

    m = AGENT.search(text)
    if m:
        name = (m.group("n") or m.group("n2") or "").strip(" .")
        if name and name.split()[0].lower() not in NOT_AGENT_NAMES:
            intents.append(AppIntent("find_agent", {"name": name}))

    tracking = TRACKING_RE.search(text)
    if tracking and re.search(r"\b(?:open|show|track|status)\b|दिखाओ|स्थिति", text, re.I):
        intents.append(AppIntent("navigate", {"screen": "complaint", "target_id": tracking.group(0).upper()}))

    screens_from_data: set[str] = set()
    for kind, rx, screen in DATA:
        if rx.search(text) and not (kind == "complaints" and tracking):
            intents.append(AppIntent("data", {"kind": kind}))
            screens_from_data.add(screen)
    for screen, rx in SCREENS:
        if rx.search(text) and screen not in screens_from_data:
            intents.append(AppIntent("navigate", {"screen": screen}))
    for screen in sorted(screens_from_data):
        intents.append(AppIntent("navigate", {"screen": screen}))
    return intents


def data_kinds(intents: list[AppIntent]) -> set[str]:
    return {i.params["kind"] for i in intents if i.kind == "data"}


SCREEN_NAMES = {
    "en": {"explore": "the city map", "townhall": "Townhall", "updates": "Updates", "saved": "your saved agents",
           "settings": "Settings", "complaint_new": "the complaint form", "complaint": "the complaint", "avatar": "the chat"},
    "hi": {"explore": "शहर का नक्शा", "townhall": "टाउनहॉल", "updates": "अपडेट्स", "saved": "सेव किए गए एजेंट",
           "settings": "सेटिंग्स", "complaint_new": "शिकायत फ़ॉर्म", "complaint": "शिकायत", "avatar": "चैट"},
}
