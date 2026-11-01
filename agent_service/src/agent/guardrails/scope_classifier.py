"""Scope Classifier module for City Sense Agent Service.

Classifies incoming queries into distinct civic domains, greetings, emergencies,
injections, or out-of-scope non-civic topics with bilingual (English/Hindi) support.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.agent.guardrails.input_guard import check_input_safety


class QueryScope(str, Enum):
    """Categorical classification of incoming user queries."""

    INJECTION = "INJECTION"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    CIVIC_GREETING = "CIVIC_GREETING"
    CIVIC_COMPLAINT = "CIVIC_COMPLAINT"
    CIVIC_EMERGENCY = "CIVIC_EMERGENCY"
    CIVIC_LIVE_DATA = "CIVIC_LIVE_DATA"
    CIVIC_KNOWLEDGE = "CIVIC_KNOWLEDGE"


@dataclass
class ScopeClassificationResult:
    """Detailed result of query scope analysis."""

    scope: QueryScope
    confidence: float
    detected_topic: str | None = None
    language: str = "en"
    is_civic: bool = False
    reason: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope.value,
            "confidence": self.confidence,
            "detected_topic": self.detected_topic,
            "language": self.language,
            "is_civic": self.is_civic,
            "reason": self.reason,
            "details": self.details,
        }


# --- REGEX PATTERN DEFINITIONS ---

# Emergency Patterns (Priority 1)
EMERGENCY_EN = re.compile(
    r"\b(?:"
    r"ambulance|108\b|112\b|102\b|101\b|"
    r"(?:severe|fatal|head-on|serious|major)\s+accident|"
    r"(?:car|truck|bus|vehicle|bike)\s+(?:crash|collision)|"
    r"hit\s+and\s+run|pedestrian\s+hit|bleeding\s+(?:profusely|heavily)|heart\s+attack|unconscious|"
    r"hospital\s+route|emergency\s+(?:route|ward|hospital|corridor)|"
    r"fire\s+brigade|building\s+on\s+fire|massive\s+fire|house\s+fire|cylinder\s+blast|"
    r"lpg\s+leak|gas\s+cylinder\s+leak|trapped\s+in\s+fire|"
    r"flash\s+flood|landslide|road\s+washed\s+away|building\s+collapse|roof\s+collapsed|"
    r"live\s+(?:electric\s+)?wire\s+(?:fallen|sparking|snapped)|electrocution\s+risk|drowning|"
    r"emergency\s+help\s+needed|urgent\s+medical\s+help|"
    r"(?<!accident\s)(?<!risk\sof\s)accident\b(?!\s*risk)"
    r")\b",
    re.IGNORECASE,
)

EMERGENCY_HI = re.compile(
    r"(?:"
    r"एम्बुलेंस|108\b|112\b|101\b|102\b|"
    r"दुर्घटना|एक्सीडेंट|सड़क\s+हादसा|अस्पताल\s+(?:का\s+रास्ता|पहुंचना|रूट)|"
    r"आग\s+लग\s+गई|भीषण\s+आग|दमकल|फायर\s+ब्रिगेड|सिलेंडर\s+ब्लास्ट|सिलेंडर\s+फट\s+गया|गैस\s+रिसाव|गैस\s+लीक|आग\s+में\s+फंसे|"
    r"बाढ़|भूस्खलन|पहाड़\s+खिसक|मकान\s+गिर\s+गया|दीवार\s+गिर\s+गई|"
    r"करंट\s+लग\s+रहा|बिजली\s+का\s+तार\s+(?:टूट|गिरा|स्पार्क)|नाली\s+में\s+बह|डूब\s+रहा|"
    r"आपातकाल|इमरजेंसी|तुरंत\s+(?:मदद|सहायता|एम्बुलेंस)"
    r")",
    re.IGNORECASE,
)

# Out of scope: Coding / Tech
OUT_OF_SCOPE_CODING = re.compile(
    r"\b(?:"
    r"(?:write|create|debug|fix|explain|give\s+me)\s+(?:a\s+)?(?:python|java|javascript|c\+\+|c#|html|css|sql|rust|typescript|php|bash)\s+(?:code|script|function|program|class|algorithm|query|regex)|"
    r"(?:def\s+\w+\(|function\s+\w+\(|console\.log|print\(|public\s+static\s+void|import\s+sys|import\s+os)|"
    r"binary\s+tree|quicksort|merge\s+sort|dynamic\s+programming|leetcode|hackerrank|coding\s+homework|"
    r"react\s+component|vue\s+template|css\s+styling|flexbox|npm\s+install|pip\s+install|"
    r"pydantic\s+model|fastapi\s+endpoint|django\s+orm"
    r")\b|"
    r"(?:पायथन\s+में\s+कोड|जावा\s*स्क्रिप्ट|प्रोग्रामिंग|कोडिंग\s+का\s+सवाल|सॉफ्टवेयर\s+बनाओ)",
    re.IGNORECASE,
)

# Out of scope: Math / Calculations
OUT_OF_SCOPE_MATH = re.compile(
    r"\b(?:"
    r"(?:solve|calculate|evaluate)\s+(?:(?:for\s+[xyz]|the\s+value\s+of\s+[xyz])|\d+\s*[\+\-\*\/]\s*\d+|x\^2|equation|integral|derivative|algebra)|"
    r"\d+\s*[\*\/]\s*\d+\s*(?:equals|\?|=)?|"
    r"what\s+is\s+\d+\s*(?:plus|minus|multiplied\s+by|divided\s+by|\*|\/|\+)\s*\d+|"
    r"pythagoras\s+theorem|calculus\s+problem|trigonometry\s+formula"
    r")\b|"
    r"(?:गणित\s+का\s+सवाल|समीकरण\s+हल\s+करो|गुणा\s+करो|भाग\s+दो|जोड़ो|घटाओ)",
    re.IGNORECASE,
)

# Out of scope: Food Recipes / Cooking
OUT_OF_SCOPE_COOKING = re.compile(
    r"\b(?:"
    r"(?:recipe\s+(?:for|of)|how\s+to\s+(?:cook|bake|make|prepare))\s+(?:[a-z\s]+)?(?:chicken|biryani|pasta|pizza|cake|cookies|samosa|paneer|curry|tea|chai|coffee|maggi|poha|dal|rice|bread|dessert|soup)|"
    r"ingredients\s+for\s+(?:cooking|making|baking)"
    r")\b|"
    r"(?:बनाने\s+की\s+विधि|रेसिपी|खाना\s+बनाना|पनीर\s+कैसे\s+बनाएं|चाय\s+कैसे\s+बनाएं|बिरयानी\s+की\s+विधि|सब्जी\s+कैसे\s+बनाएं)",
    re.IGNORECASE,
)

# Out of scope: Entertainment / Sports / Pop Culture / Creative Writing / General Trivia
OUT_OF_SCOPE_GENERAL = re.compile(
    r"\b(?:"
    r"tell\s+me\s+a\s+(?:funny\s+)?joke|write\s+a\s+(?:love\s+)?poem|write\s+a\s+(?:bedtime\s+)?story|"
    r"who\s+won\s+the\s+(?:cricket|football|fifa)?\s*(?:world\s+cup|match|ipl|tournament)|"
    r"cricket\s+score|ipl\s+score|football\s+score|"
    r"movie\s+review|lyrics\s+of|singer\s+of|taylor\s+swift|lionel\s+messi|cristiano\s+ronaldo|virat\s+kohli|"
    r"capital\s+of\s+(?:france|australia|germany|usa|japan|canada|italy|brazil)|"
    r"who\s+is\s+the\s+president\s+of\s+(?:usa|america|france|russia)|who\s+is\s+elon\s+musk|"
    r"horoscope\s+today|astrology\s+prediction|tarot\s+reading|"
    r"i\s+am\s+(?:bored|feeling\s+sad|lonely)|will\s+you\s+marry\s+me|be\s+my\s+friend|are\s+you\s+single"
    r")\b|"
    r"(?:चुटकुला\s+सुनाओ|जोक\s+सुनाओ|कविता\s+लिखो|कहानी\s+सुनाओ|फ्रांस\s+की\s+राजधानी|अमेरिका\s+का\s+राष्ट्रपति|क्रिकेट\s+स्कोर|फिल्म\s+कैसी\s+है|गाने\s+के\s+बोल|राशिफल|बोर\s+हो\s+रहा\s+हूँ)",
    re.IGNORECASE,
)

# Civic Greeting / Identity Patterns
GREETING_WORDS_EN = re.compile(
    r"^\s*(?:hi|hello|hey|greetings|good\s+morning|good\s+evening|good\s+afternoon|good\s+day)\b",
    re.IGNORECASE,
)

GREETING_WORDS_HI = re.compile(
    r"^\s*(?:नमस्ते|नमस्कार|प्रणाम|सुप्रभात|शुभ\s+संध्या|राम\s+राम|जय\s+श्री\s+राम|जय\s+हिंद|हैलो|हाय)(?:[\s,!?।.]|$)",
    re.IGNORECASE,
)

IDENTITY_EN = re.compile(
    r"\b(?:"
    r"who\s+are\s+you|what\s+are\s+you|what\s+is\s+your\s+name|what\s+can\s+you\s+do|"
    r"what\s+is\s+city\s+sense|how\s+can\s+you\s+help\s+me|who\s+created\s+you|"
    r"what\s+services\s+do\s+you\s+offer|tell\s+me\s+about\s+yourself|what\s+features\s+do\s+you\s+have"
    r")\b",
    re.IGNORECASE,
)

IDENTITY_HI = re.compile(
    r"(?:"
    r"तुम\s+कौन\s+हो|आप\s+कौन\s+हैं|तुम्हारा\s+नाम\s+क्या\s+है|आप\s+क्या\s+कर\s+सकते\s+(?:हो|हैं)|"
    r"सिटी\s+सेंस\s+क्या\s+है|मेरी\s+क्या\s+मदद\s+कर\s+सकते\s+हो|अपने\s+बारे\s+में\s+बताओ|आपकी\s+क्या\s+सेवाएं\s+हैं"
    r")",
    re.IGNORECASE,
)

# Civic Complaint Patterns
COMPLAINT_EN = re.compile(
    r"\b(?:"
    r"potholes?|crater|damaged\s+road|broken\s+road|bad\s+road|asphalt|cave-?in|sinkhole|"
    r"broken\s+divider|speed\s+breaker\s+broken|"
    r"garbage|trash|waste|dustbin|overflowing\s+(?:bin|dustbin|dump)|garbage\s+dump|"
    r"uncollected\s+waste|litter(?:ing)?|dead\s+animal|carcass|foul\s+smell|stench|"
    r"sanitation|sweeping\s+not\s+done|"
    r"streetlights?|street\s+light|lamp\s+post|dark\s+street|light\s+not\s+working|"
    r"broken\s+light|flickering\s+light|dangling\s+wire|hanging\s+cable|transformer\s+spark|"
    r"water\s+leak|pipe\s+burst|pipeline\s+broken|contaminated\s+water|dirty\s+tap\s+water|"
    r"yellow\s+water|low\s+water\s+pressure|no\s+water\s+supply|"
    r"blocked\s+drain|clogged\s+sewer|overflowing\s+gutter|open\s+manhole|manhole\s+cover\s+missing|waterlogging|"
    r"encroachments?|hawkers?\b|footpath\s+blocked|blocking\s+(?:pedestrian|sidewalk|footpath|road)|unauthorized\s+construction|"
    r"stray\s+dogs?\s+(?:pack|menace|biting)|stray\s+cattle|cows?\s+blocking\s+road|"
    r"\b(?:i\s+want\s+to\s+)?(?:file|lodge|register|submit|make|raise)\s+(?:a\s+)?(?:complaint|grievance|issue|report)\b|"
    r"\bcomplaints?\b|\bcomplain\b|\bgrievances?\b(?!\s*department)|shikayat"
    r")\b",
    re.IGNORECASE,
)

COMPLAINT_HI = re.compile(
    r"(?:"
    r"गड्ढा|गड्ढे|सड़क\s+(?:टूटी|खराब|धंस|गड्ढे)|डामर\s+उखड़|"
    r"कूड़ा|कचरा|डस्टबिन|कचरे\s+का\s+ढेर|सफाई\s+नहीं|बदबू|गंदगी|सड़\s+रहा|मृत\s+पशु|झाड़ू|"
    r"स्ट्रीट\s+लाइट|बत्ती\s+बंद|अंधेरा\s+है|खंभा\s+टूट|लाइट\s+खराब|बिजली\s+का\s+तार\s+झूल|"
    r"पानी\s+का\s+रिसाव|पाइप\s+(?:फटा|टूटा)|गंदा\s+पानी|पानी\s+नहीं\s+आ\s+रहा|नाली\s+(?:जाम|चोक)|सीवर\s+ओवरफ्लो|खुला\s+मैनहोल|गटर|जलभराव|"
    r"अतिक्रमण|अवैध\s+कब्जा|फुटपाथ\s+बंद|आवारा\s+कुत्ते|लावारिस\s+पशु|गाय\s+सड़क\s+पर|"
    r"शिकायत\s+(?:दर्ज|करनी\s+है|करना\s+चाहता|करनी\s+चाहती)|\bशिकायत\b|\bसमस्या\b|समस्या\s+की\s+रिपोर्ट|कार्रवाई\s+करें"
    r")",
    re.IGNORECASE,
)

# Civic Live Data Patterns
LIVE_DATA_EN = re.compile(
    r"\b(?:"
    r"traffic\s+(?:status|density|congestion|jam|condition|update|level)|"
    r"signals?\s+(?:working|red|green|timing|status)|"
    r"road\s+(?:closed|closure|block)|diversions?|detour|alternate\s+route|"
    r"parking\s+(?:status|available|availability|full|space|lot)|"
    r"live\s+alerts?|city\s+advisories?|weather\s+(?:alert|warning|department|forecast|advisory|update)|"
    r"(?:heavy\s+)?rain(?:fall)?\s+(?:alert|warning)|"
    r"air\s+quality|aqi|pollution\s+(?:level|index)|smog|"
    r"upcoming\s+(?:city\s+)?events?|city\s+marathon|mela|exhibition|cultural\s+festival|flower\s+show|cleanliness\s+drive|public\s+parade"
    r")\b",
    re.IGNORECASE,
)

LIVE_DATA_HI = re.compile(
    r"(?:"
    r"ट्रैफिक\s+(?:जाम|की\s+स्थिति|अपडेट|कैसा\s+है)|"
    r"सिग्नल\s+(?:चालू|खराब|काम\s+कर\s+रहा)|"
    r"रास्ता\s+(?:बंद|डायवर्जन)|रूट\s+डायवर्जन|पार्किंग\s+(?:उपलब्ध|खाली|की\s+स्थिति)|"
    r"लाइव\s+अलर्ट|चेतावनी|मौसम\s+की\s+चेतावनी|बारिश\s+का\s+अलर्ट|वायु\s+गुणवत्ता|एक्यूआई|प्रदूषण\s+का\s+स्तर|"
    r"शहर\s+के\s+कार्यक्रम|आगामी\s+कार्यक्रम|मेला|प्रदर्शनी|मैराथन|उत्सव"
    r")",
    re.IGNORECASE,
)

# Civic Knowledge Patterns
KNOWLEDGE_EN = re.compile(
    r"\b(?:"
    r"pm\s+awas\s+yojana|pmay|ayushman\s+bharat|golden\s+card|ration\s+card|bpl\s+card|"
    r"old\s+age\s+pension|widow\s+pension|disability\s+pension|gaura\s+devi|ujjwala|citizen\s+welfare\s+scheme|"
    r"birth\s+certificate|death\s+certificate|marriage\s+registration|property\s+mutation|building\s+permit|"
    r"map\s+approval|trade\s+license|commercial\s+license|noc\s+application|water\s+connection\s+application|"
    r"property\s+tax|house\s+tax|pay\s+tax\s+online|tax\s+rebate|"
    r"nagar\s+nigam\s+(?:office|hours|timings|address|circular|bylaws|rules)|"
    r"office\s+hours|office\s+timings|working\s+hours|grievance\s+department|"
    r"ward\s+counselor|parshad|mayor\s+contact|rti\s+application|citizen\s+charter|"
    r"how\s+to\s+apply\s+for|documents?\s+required\s+for|eligibility\s+for"
    r")\b",
    re.IGNORECASE,
)

KNOWLEDGE_HI = re.compile(
    r"(?:"
    r"आयुष्मान|आवास\s+योजना|राशन\s+कार्ड|बीपीएल\s+कार्ड|"
    r"वृद्धावस्था\s+पेंशन|विधवा\s+पेंशन|दिव्यांग\s+पेंशन|गौरा\s+देवी\s+कन्याधन|सरकारी\s+योजना|"
    r"जन्म\s+प्रमाण\s+पत्र|मृत्यु\s+प्रमाण\s+पत्र|विवाह\s+पंजीकरण|नामांतरण|म्यूटेशन|"
    r"नक्शा\s+पास|भवन\s+निर्माण\s+अनुमति|ट्रेड\s+लाइसेंस|जल\s+संयोजन|"
    r"गृह\s+कर|हाउस\s+टैक्स|संपत्ति\s+कर|टैक्स\s+जमा|ऑनलाइन\s+भुगतान|"
    r"नगर\s+निगम\s+कार्यालय|कार्यालय\s+समय|खुलने\s+का\s+समय|वार्ड\s+पार्षद|मेयर|नागरिक\s+अधिकार\s+पत्र|परिपत्र|नियम|"
    r"आवेदन\s+कैसे\s+करें|पात्रता|जरूरी\s+दस्तावेज"
    r")",
    re.IGNORECASE,
)

CIVIC_TOKENS = {
    "dehradun", "nagar", "nigam", "ward", "civic", "municipal", "city",
    "citizen", "government", "sarkar", "yojana", "uttarakhand", "road",
    "street", "tax", "certificate", "scheme", "police", "hospital"
}


class ScopeClassifier:
    """Classifies user queries into supported civic scopes or out-of-scope/injections."""

    def __init__(self, risk_threshold: float = 0.70):
        self.risk_threshold = risk_threshold

    @staticmethod
    def detect_language(text: str, override: str | None = None) -> str:
        """Determines if the text is in Hindi ('hi') or English ('en')."""
        if override in ("hi", "en"):
            return override
        if any("\u0900" <= c <= "\u097f" for c in text):
            return "hi"
        return "en"

    def classify(self, text: str, language: str | None = None) -> ScopeClassificationResult:
        """Classifies text into QueryScope with confidence and detected metadata."""
        clean_text = text.strip() if text else ""
        lang = self.detect_language(clean_text, language)

        if not clean_text:
            return ScopeClassificationResult(
                scope=QueryScope.OUT_OF_SCOPE,
                confidence=1.0,
                detected_topic="empty_query",
                language=lang,
                is_civic=False,
            )

        # 1. Injection & Safety Check
        guard_result = check_input_safety(clean_text, risk_threshold=self.risk_threshold)
        if not guard_result.is_safe:
            return ScopeClassificationResult(
                scope=QueryScope.INJECTION,
                confidence=guard_result.risk_score,
                detected_topic="prompt_injection",
                language=lang,
                is_civic=False,
                reason=guard_result.reason,
                details={"risk_score": guard_result.risk_score},
            )

        # 2. Civic Emergency Check (Priority 1)
        if EMERGENCY_EN.search(clean_text) or EMERGENCY_HI.search(clean_text):
            return ScopeClassificationResult(
                scope=QueryScope.CIVIC_EMERGENCY,
                confidence=0.98,
                detected_topic="civic_emergency",
                language=lang,
                is_civic=True,
            )

        # 3. Explicit Out-of-Scope Checks (Coding, Math, Cooking, General/Trivia)
        if OUT_OF_SCOPE_CODING.search(clean_text):
            return ScopeClassificationResult(
                scope=QueryScope.OUT_OF_SCOPE,
                confidence=0.95,
                detected_topic="coding and software engineering",
                language=lang,
                is_civic=False,
            )

        if OUT_OF_SCOPE_MATH.search(clean_text):
            return ScopeClassificationResult(
                scope=QueryScope.OUT_OF_SCOPE,
                confidence=0.95,
                detected_topic="mathematical calculations",
                language=lang,
                is_civic=False,
            )

        if OUT_OF_SCOPE_COOKING.search(clean_text):
            return ScopeClassificationResult(
                scope=QueryScope.OUT_OF_SCOPE,
                confidence=0.95,
                detected_topic="cooking recipes",
                language=lang,
                is_civic=False,
            )

        if OUT_OF_SCOPE_GENERAL.search(clean_text):
            return ScopeClassificationResult(
                scope=QueryScope.OUT_OF_SCOPE,
                confidence=0.92,
                detected_topic="general trivia, creative writing, or entertainment",
                language=lang,
                is_civic=False,
            )

        # 4. Civic Greeting & Bot Capabilities
        # Check if greeting or identity query is present WITHOUT an actionable complaint or query
        is_greeting = bool(GREETING_WORDS_EN.search(clean_text) or GREETING_WORDS_HI.search(clean_text))
        is_identity = bool(IDENTITY_EN.search(clean_text) or IDENTITY_HI.search(clean_text))

        has_complaint = bool(COMPLAINT_EN.search(clean_text) or COMPLAINT_HI.search(clean_text))
        has_live_data = bool(LIVE_DATA_EN.search(clean_text) or LIVE_DATA_HI.search(clean_text))
        has_knowledge = bool(KNOWLEDGE_EN.search(clean_text) or KNOWLEDGE_HI.search(clean_text))

        if (is_greeting or is_identity) and not (has_complaint or has_live_data or has_knowledge):
            return ScopeClassificationResult(
                scope=QueryScope.CIVIC_GREETING,
                confidence=0.95,
                detected_topic="civic_greeting",
                language=lang,
                is_civic=True,
            )

        # 5. Civic Complaint Check (Check complaints before general knowledge)
        if has_complaint:
            return ScopeClassificationResult(
                scope=QueryScope.CIVIC_COMPLAINT,
                confidence=0.95,
                detected_topic="civic_complaint",
                language=lang,
                is_civic=True,
            )

        # 6. Civic Live Data Check
        if has_live_data:
            return ScopeClassificationResult(
                scope=QueryScope.CIVIC_LIVE_DATA,
                confidence=0.92,
                detected_topic="civic_live_data",
                language=lang,
                is_civic=True,
            )

        # 7. Civic Knowledge Check
        if has_knowledge:
            return ScopeClassificationResult(
                scope=QueryScope.CIVIC_KNOWLEDGE,
                confidence=0.92,
                detected_topic="civic_knowledge",
                language=lang,
                is_civic=True,
            )

        # 8. Civic Keyword Fallback vs General Non-Civic Out-of-Scope
        words = set(re.findall(r"\w+", clean_text.lower()))
        matched_civic = words.intersection(CIVIC_TOKENS)

        if matched_civic:
            return ScopeClassificationResult(
                scope=QueryScope.CIVIC_KNOWLEDGE,
                confidence=0.75,
                detected_topic="civic_inquiry",
                language=lang,
                is_civic=True,
                details={"matched_keywords": list(matched_civic)},
            )

        # Default fallback for arbitrary non-civic input
        return ScopeClassificationResult(
            scope=QueryScope.OUT_OF_SCOPE,
            confidence=0.85,
            detected_topic="non-civic general inquiry",
            language=lang,
            is_civic=False,
        )


_DEFAULT_CLASSIFIER = ScopeClassifier()


def classify_scope(text: str, language: str | None = None) -> ScopeClassificationResult:
    """Convenience functional interface to classify query scope."""
    return _DEFAULT_CLASSIFIER.classify(text, language=language)
