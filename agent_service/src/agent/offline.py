import json
import logging
import re
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from src.agent.schemas import (
    AgentInfo,
    AgentResponse,
    ChatRequest,
    ConfirmResponse,
    PendingActionView,
    Source,
)
from src.auth.schemas import Principal

logger = logging.getLogger("citysense.offline")

# In-memory storage for offline mode
PENDING_ACTIONS: dict[str, dict[str, Any]] = {}
OFFLINE_SESSIONS: dict[UUID, dict[str, Any]] = {}
SESSION_HISTORY: dict[str, list[dict[str, Any]]] = defaultdict(list)

# Initial seeded Dehradun complaints for the Worker Island
MOCK_COMPLAINTS: list[dict[str, Any]] = [
    {
        "tracking_id": "NND-2026-0841",
        "title": "Severe Pothole on Subhash Road near Clock Tower",
        "description": "Deep asphalt crater causing traffic bottleneck and accident risk near Central Bank.",
        "category": "Potholes and Road Damage",
        "status": "IN_PROGRESS",
        "priority": "HIGH",
        "ward": "Ward 24 - Paltan Bazaar",
        "location": {"lat": 30.3244, "lng": 78.0418, "address": "Subhash Road near Clock Tower, Dehradun"},
        "created_at": "2026-10-31T08:30:00Z",
        "warnings_count": 1,
        "assigned_worker": {"name": "Ramesh Negi", "team": "NND Rapid Road Unit 2"},
        "photo_url": "",
        "citizen": {"name": "Aditya Sharma"},
        "citizen_notification": {
            "message": "Nagar Nigam field crew Ramesh Negi (Unit 2) has been assigned. Work is underway.",
            "channel": "SMS & App"
        }
    },
    {
        "tracking_id": "NND-2026-0842",
        "title": "Non-functional LED Streetlights on Rajpur Road",
        "description": "5 consecutive streetlight poles are completely dark between Jakhan and IT Park turn.",
        "category": "Defective Streetlights",
        "status": "WARNING_1",
        "priority": "MEDIUM",
        "ward": "Ward 12 - Rajpur",
        "location": {"lat": 30.3541, "lng": 78.0700, "address": "Rajpur Road near Jakhan, Dehradun"},
        "created_at": "2026-10-31T09:15:00Z",
        "warnings_count": 2,
        "assigned_worker": {"name": "Sunil Rawat", "team": "Electrical Maintenance Division"},
        "photo_url": "",
        "citizen": {"name": "Pooja Verma"},
        "citizen_notification": {
            "message": "Escalated to JE Electrical: Streetlight repair ticket scheduled for tonight.",
            "channel": "WhatsApp"
        }
    },
    {
        "tracking_id": "NND-2026-0843",
        "title": "Overflowing Public Dustbin at Paltan Bazaar Entrance",
        "description": "Commercial waste accumulating on pedestrian sidewalk, emitting foul odor.",
        "category": "Garbage and Sanitation Dumps",
        "status": "ASSIGNED",
        "priority": "HIGH",
        "ward": "Ward 24 - Paltan Bazaar",
        "location": {"lat": 30.3225, "lng": 78.0392, "address": "Paltan Bazaar North Gate, Dehradun"},
        "created_at": "2026-10-31T10:00:00Z",
        "warnings_count": 0,
        "assigned_worker": {"name": "Vikram Chauhan", "team": "Sanitary Inspection Squad 4"},
        "photo_url": "",
        "citizen": {"name": "Rajesh Gupta"},
        "citizen_notification": {
            "message": "Compactor truck dispatched to Paltan Bazaar entrance. ETA 30 mins.",
            "channel": "SMS"
        }
    }
]


STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "are", "was", "were",
    "will", "can", "could", "would", "should", "you", "your", "tell", "give",
    "what", "when", "where", "which", "who", "whom", "whose", "why", "how",
    "all", "any", "both", "each", "few", "more", "most", "other", "some", "such",
    "than", "too", "very", "about", "above", "after", "again", "against",
    "between", "into", "through", "during", "before", "after", "below", "world",
    "to", "of", "in", "on", "at", "by", "is", "it", "an", "as", "be", "or",
    "है", "हैं", "था", "थी", "थे", "का", "के", "की", "को", "में", "से", "पर",
    "और", "या", "तो", "भी", "नहीं", "क्या", "कहाँ", "कब", "कैसे", "कौन", "किस",
    "बताओ", "दीजिए", "करें", "नियम", "बारे"
}


def tokenize(text: str) -> list[str]:
    raw = [w.strip().lower() for w in re.split(r'[\s\.,?!;:\"\'()\[\]{}।]+', text) if w.strip()]
    return [t for t in raw if len(t) > 2 and t not in STOPWORDS]


class OfflineCorpus:
    def __init__(self, corpus_root: Path):
        self.documents: list[dict[str, Any]] = []
        self._load(corpus_root)

    def _load(self, root: Path):
        if not root.exists():
            return
        for md_path in root.rglob("*.md"):
            if md_path.name == "README.md":
                continue
            meta_path = md_path.with_name(f"{md_path.stem}.meta.json")
            meta = {}
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
            content = md_path.read_text(encoding="utf-8")
            # Extract title from markdown if not in meta
            title = meta.get("title")
            if not title:
                lines = content.strip().split("\n")
                title = lines[0].lstrip("# ").strip() if lines else md_path.stem
            doc_id = md_path.stem
            is_hindi = "_hi" in doc_id or meta.get("language") == "hi"
            self.documents.append({
                "doc_id": doc_id,
                "title": title,
                "url": meta.get("source_url") or "https://nagarnigamdehradun.com",
                "content": content,
                "language": "hi" if is_hindi else "en",
                "jurisdiction": meta.get("jurisdiction", "dehradun"),
                "publisher": meta.get("publisher", "Government of Uttarakhand")
            })
        logger.info("Loaded %d documents into offline corpus", len(self.documents))

    def search(self, query: str, language: str) -> list[tuple[dict[str, Any], float, str]]:
        """Performs token-based relevance scoring with language affinity."""
        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        scored = []
        for doc in self.documents:
            doc_lang = doc["language"]
            lang_mult = 1.3 if doc_lang == language else 0.7
            doc_text = doc["content"].lower()
            doc_title = doc["title"].lower()

            matched_tokens = 0
            score = 0.0
            for token in query_tokens:
                in_title = token in doc_title
                in_text = token in doc_text
                if in_title:
                    score += 6.0
                    matched_tokens += 1
                elif in_text:
                    score += 1.5
                    matched_tokens += 1

            # Require at least 2 matching tokens or high title overlap if multi-word query
            if len(query_tokens) >= 2 and matched_tokens < 2 and score < 5.0:
                continue

            if score > 0:
                final_score = score * lang_mult
                excerpt = self._extract_excerpt(doc["content"], set(query_tokens))
                scored.append((doc, final_score, excerpt))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def _extract_excerpt(self, content: str, tokens: set[str], max_len: int = 500) -> str:
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip() and not p.strip().startswith("#")]
        if not paragraphs:
            return content[:max_len]
        best_p = paragraphs[0]
        max_overlap = -1
        for p in paragraphs:
            p_tokens = set(re.findall(r"\w+", p.lower()))
            overlap = len(tokens.intersection(p_tokens))
            if overlap > max_overlap:
                max_overlap = overlap
                best_p = p
        return best_p[:max_len]


# Initialize corpus
CORPUS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "corpus"
offline_corpus = OfflineCorpus(CORPUS_PATH)

# Complaint detection keywords
COMPLAINT_PATTERNS = [
    r"pothole", r"potholes", r"road damage", r"broken road",
    r"garbage", r"waste", r"dustbin", r"trash", r"cleaning",
    r"streetlight", r"street light", r"dark", r"power cut", r"wire",
    r"water leak", r"drain", r"sewage", r"manhole", r"encroachment",
    r"complaint", r"shikayat", r"report", r"issue",
    # Hindi patterns
    r"गड्ढा", r"गड्ढे", r"सड़क", r"कचरा", r"कूड़ा", r"सफाई",
    r"लाइट", r"स्ट्रीट लाइट", r"अंधेरा", r"बिजली", r"पानी",
    r"नाली", r"सीवर", r"मैनहोल", r"शिकायत", r"समस्या"
]


def detect_complaint_intent(text: str) -> bool:
    lower = text.lower()
    return any(re.search(pat, lower, re.IGNORECASE) for pat in COMPLAINT_PATTERNS)


async def offline_chat(
    principal: Principal,
    request: ChatRequest,
    started: float
) -> AgentResponse:
    session_id = request.sessionId or uuid4()
    session_key = str(session_id)
    message_id = uuid4()
    agent_id = request.agentId or "general"
    agent_name = "Municipal Grievance Officer" if agent_id == "municipal" else "City Sense"

    # Multi-turn conversation history lookup (up to 6 previous turns)
    prior_history = list(SESSION_HISTORY[session_key][-6:])

    # Detect language
    is_hindi = (
        request.language == "hi"
        or any("\u0900" <= c <= "\u097f" for c in request.message)
    )
    lang = "hi" if is_hindi else "en"

    # Tier 1 & Tier 2: Supervised Guardrails & Sub-Agent Orchestration (with context memory)
    from src.agent.orchestrator import supervisor
    from src.models import AgentConfig, ChatSession

    outcome = await supervisor.evaluate_turn(
        session=None,
        principal=principal,
        request=request,
        chat_session=ChatSession(user_id=principal.user_id, agent_id=agent_id, language=lang),
        agent=AgentConfig(agent_id=agent_id, name=agent_name, role="citizen_agent", system_prompt=""),
        language=lang,
        city=request.context.cityId or "dehradun",
        started=started,
        history=prior_history,
    )

    handled, status, answer, sources, cta, pending_action = (
        outcome.handled, outcome.status, outcome.answer, outcome.sources, outcome.cta, outcome.pending_action
    )
    from src.agent.orchestrator import finalize_plan

    plan_fields = {"plan": outcome.plan, "toolCalls": outcome.tool_calls, "actionData": outcome.action_data,
                   "clientActions": outcome.client_actions}
    if not handled:
        finalize_plan(outcome.plan, "ANSWERED")
    if handled:
        # Save this turn to multi-turn conversation memory
        SESSION_HISTORY[session_key].append({"role": "user", "content": request.message})
        SESSION_HISTORY[session_key].append({"role": "assistant", "content": answer})

        source_objects = []
        for s in (sources or []):
            if isinstance(s, dict):
                source_objects.append(
                    Source(
                        docId=s.get("doc_id", "DOC"),
                        title=s.get("title", "Official Record"),
                        url=s.get("url", ""),
                        excerpt=s.get("excerpt"),
                        fetchedAt=datetime.now(timezone.utc),
                        stale=False,
                    )
                )
            elif isinstance(s, Source):
                source_objects.append(s)

        return AgentResponse(
            sessionId=session_id,
            messageId=message_id,
            status=status,
            answer=answer,
            agent=AgentInfo(id=agent_id, name=agent_name),
            sources=source_objects,
            cta=cta or "report_issue",
            pendingAction=pending_action,
            served="fallback",
            **plan_fields,
        )

    # Tier 3: Agentic Tool-Calling Loop with Real-Time APIs & LLM Synthesis
    from src.agent.tool_registry import TOOL_OWNERS, call_tool
    from src.agent.tools import READ_TOOL_NAMES, tool_schemas
    available_tools = tool_schemas(READ_TOOL_NAMES)

    # Context from verified municipal corpus
    hits = offline_corpus.search(request.message, lang)
    context_texts = [h[0].get("text", "") for h in hits[:2]] if hits else [
        "Nagar Nigam Dehradun provides municipal civil works, sanitation, public lighting, and health services across 100 wards."
    ]

    llm_history = [{"role": m["role"], "content": m["content"]} for m in prior_history]
    llm_history.append({"role": "user", "content": request.message})

    llm_answer = None
    served_provider = "fallback"
    tool_sources: list[Source] = []

    try:
        from src.providers.registry import generate_with_failover
        gen_res = await generate_with_failover(
            system=(
                "You are City Sense, the official municipal AI assistant for Dehradun Nagar Nigam. "
                "Synthesize helpful, accurate, and articulate answers for citizens. "
                "Use the available tools when the citizen asks for real-time information such as "
                "active alerts, traffic density, emergency corridors, civic events, or listing municipal complaints. "
                "Respond courteously, clearly, and actionably."
            ),
            user=request.message,
            context=context_texts,
            language=lang,
            tools=available_tools,
            history=llm_history,
        )

        if gen_res.tool_calls:
            tool_history = list(llm_history)
            tool_history.append({
                "role": "assistant",
                "content": gen_res.text or "",
                "tool_calls": gen_res.tool_calls,
            })
            for call in gen_res.tool_calls:
                fn_name = call.get("function", {}).get("name", "")
                raw_args = call.get("function", {}).get("arguments", "{}")
                parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                tool_data = await call_tool(TOOL_OWNERS[fn_name], fn_name, parsed_args, principal.user_id)
                tool_history.append({
                    "role": "tool",
                    "tool_call_id": call.get("id", "unknown"),
                    "content": json.dumps(tool_data, ensure_ascii=False),
                })
                tool_sources.append(
                    Source(
                        docId=fn_name,
                        title=f"Municipal API: {fn_name.replace('_', ' ').title()}",
                        url="https://nagarnigamdehradun.com",
                        excerpt=json.dumps(tool_data, ensure_ascii=False)[:300],
                        fetchedAt=datetime.now(timezone.utc),
                        stale=False,
                    )
                )

            synth_res = await generate_with_failover(
                system=(
                    "You are City Sense, the official municipal AI assistant for Dehradun Nagar Nigam. "
                    "Synthesize a clear, structured, and helpful response for the citizen based on the tool execution results."
                ),
                user="",
                context=context_texts,
                language=lang,
                history=tool_history,
            )
            if synth_res and synth_res.text and len(synth_res.text.strip()) > 15:
                llm_answer = synth_res.text.strip()
                served_provider = synth_res.provider
        elif gen_res and gen_res.text and len(gen_res.text.strip()) > 15:
            llm_answer = gen_res.text.strip()
            served_provider = gen_res.provider
    except Exception as exc:
        logger.warning("Live LLM tool execution exception: %s", exc)

    if llm_answer:
        SESSION_HISTORY[session_key].append({"role": "user", "content": request.message})
        SESSION_HISTORY[session_key].append({"role": "assistant", "content": llm_answer})
        return AgentResponse(
            sessionId=session_id,
            messageId=message_id,
            status="ANSWERED",
            answer=llm_answer,
            agent=AgentInfo(id=agent_id, name=f"City Sense ({served_provider.title()})"),
            sources=tool_sources if tool_sources else ([Source(docId=hits[0][0]["doc_id"], title=hits[0][0]["title"], url=hits[0][0]["url"], excerpt=hits[0][2], fetchedAt=datetime.now(timezone.utc), stale=False)] if hits else []),
            cta="report_issue",
            served="live" if served_provider != "fallback" else "fallback",
            **plan_fields,
        )

    # Fallback to grounded search excerpt if LLM was unavailable
    if hits and hits[0][1] >= 0.8:
        best_doc, score, excerpt = hits[0]
        sources = [
            Source(
                docId=best_doc["doc_id"],
                title=best_doc["title"],
                url=best_doc["url"],
                excerpt=excerpt,
                fetchedAt=datetime.now(timezone.utc),
                stale=False,
            )
        ]
        answer = f"Based on verified municipal records ({best_doc['title']}):\n\n{excerpt}"
        SESSION_HISTORY[session_key].append({"role": "user", "content": request.message})
        SESSION_HISTORY[session_key].append({"role": "assistant", "content": answer})
        return AgentResponse(
            sessionId=session_id,
            messageId=message_id,
            status="ANSWERED",
            answer=answer,
            agent=AgentInfo(id=agent_id, name=agent_name),
            sources=sources,
            cta="report_issue",
            served="fallback",
            **plan_fields,
        )

    # Main agent answers in its own words (conversation / capabilities / honest "not verified");
    # the template below is only used when no LLM is reachable.
    from src.agent.composer import compose

    composed_fallback = await compose(intent="no_verified_info", message=request.message, language=lang,
                                      history=prior_history)
    fallback_msg = composed_fallback or (
        "देहरादून नगर निगम में नागरिक सेवाओं के लिए आप सीधे शिकायत दर्ज कर सकते हैं या नागरिक हेल्पलाइन पर संपर्क कर सकते हैं:\n\n"
        "• **नागरिक शिकायत:** सड़क के गड्ढे, कचरा, स्ट्रीट लाइट या नाली की समस्या दर्ज करें\n"
        "• **हेल्पलाइन:** 1800-180-4107 या 0135-2653572\n"
        "• **कार्यालय:** नगर निगम मुख्यालय, क्लॉक टॉवर के पास, देहरादून (प्रातः 10 बजे से सायं 5 बजे तक)"
        if lang == "hi"
        else
        "For civic assistance in Dehradun, you can lodge a grievance, check alerts, or reach out directly to Nagar Nigam Dehradun:\n\n"
        "• **File a Grievance:** Report potholes, sanitation waste, dark streetlights, or drainage issues\n"
        "• **Citizen Toll-Free Helpline:** 1800-180-4107 or 0135-2653572\n"
        "• **Municipal Office:** Nagar Nigam Complex, near Clock Tower, Dehradun (Open 10:00 AM – 5:00 PM)"
    )
    SESSION_HISTORY[session_key].append({"role": "user", "content": request.message})
    SESSION_HISTORY[session_key].append({"role": "assistant", "content": fallback_msg})
    return AgentResponse(
        sessionId=session_id,
        messageId=message_id,
        status="ANSWERED",
        answer=fallback_msg,
        agent=AgentInfo(id=agent_id, name=agent_name),
        sources=[],
        cta="report_issue",
        served="fallback",
        **plan_fields,
    )


async def offline_confirm_action(principal: Principal, token: str) -> ConfirmResponse:
    action = PENDING_ACTIONS.get(token)
    if not action or action.get("user_id") not in (None, principal.user_id):
        return ConfirmResponse(status="rejected", detail="Action is invalid, expired, or already used")
    if action["status"] != "pending":
        return ConfirmResponse(status="rejected", detail=f"Action is already {action['status']}")
    if action["expires_at"] <= datetime.now(timezone.utc):
        action["status"] = "expired"
        return ConfirmResponse(status="rejected", detail="Action has expired")

    from src.config import settings

    if settings.complaint_service_url and action.get("args"):
        # Claim first so a double-tap cannot file twice, then file into the complaint module.
        action["status"] = "executing"
        try:
            from src.agent.tools import execute_complaint

            from src.agent.media import photo_for

            result = await execute_complaint(action["args"], token, principal.user_id, await photo_for(None, token))
        except Exception:
            action["status"] = "failed"
            return ConfirmResponse(status="failed", detail="Complaint service unavailable; please retry later")
        action["status"] = "executed"
        action["result_ref"] = result["trackingId"]
        return ConfirmResponse(status="executed", result=result)

    # Generate realistic tracking ID
    tracking_id = f"NND-2026-{secrets.randbelow(9000) + 1000}"
    action["status"] = "executed"
    action["result_ref"] = tracking_id

    # Add to complaints for Worker Island
    category = action.get("category", "Potholes and Road Damage")
    worker = "Ramesh Negi (Unit 2)" if "Road" in category else "Sunil Rawat (Electrical)"
    new_ticket = {
        "tracking_id": tracking_id,
        "title": action.get("summary", "Citizen Reported Civic Issue"),
        "description": action.get("message", "Citizen report lodged via City Sense Assistant."),
        "category": category,
        "status": "IN_PROGRESS",
        "priority": "HIGH",
        "ward": "Ward 14 - Rajpur Road",
        "location": {"lat": 30.3244, "lng": 78.0418, "address": "Rajpur Road, Dehradun"},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "warnings_count": 0,
        "assigned_worker": {"name": worker, "team": "NND Field Unit"},
        "photo_url": "",
        "citizen": {"name": "Citizen (Mobile App)"},
        "citizen_notification": {
            "message": f"Your complaint {tracking_id} has been registered. Field crew dispatched.",
            "channel": "SMS & Push"
        }
    }
    MOCK_COMPLAINTS.insert(0, new_ticket)

    return ConfirmResponse(
        status="executed",
        result={
            "trackingId": tracking_id,
            "category": category,
            "status": "ASSIGNED",
            "message": f"Grievance {tracking_id} successfully registered with Nagar Nigam Dehradun."
        }
    )


def offline_cancel_action(principal: Principal, token: str) -> ConfirmResponse:
    action = PENDING_ACTIONS.get(token)
    if not action or action["status"] != "pending":
        return ConfirmResponse(status="rejected", detail="Action is invalid or already completed")
    action["status"] = "cancelled"
    return ConfirmResponse(status="cancelled", detail="Action cancelled successfully")


def offline_action_status(principal: Principal, token: str) -> dict[str, Any] | None:
    action = PENDING_ACTIONS.get(token)
    if not action:
        return None
    state = "expired" if action["status"] == "pending" and action["expires_at"] <= datetime.now(timezone.utc) else action["status"]
    return {
        "status": state,
        "summary": action["summary"],
        "expiresAt": action["expires_at"],
        "resultRef": action.get("result_ref")
    }


def get_all_complaints() -> list[dict[str, Any]]:
    return MOCK_COMPLAINTS


def resolve_complaint_by_id(tracking_id: str, resolution_note: str) -> dict[str, Any] | None:
    for c in MOCK_COMPLAINTS:
        if c["tracking_id"] == tracking_id:
            c["status"] = "RESOLVED"
            c["resolution_note"] = resolution_note
            c["resolved_at"] = datetime.now(timezone.utc).isoformat()
            c["citizen_notification"] = {
                "message": f"Resolved: {resolution_note}",
                "channel": "SMS & App"
            }
            return c
    return None
