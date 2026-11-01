import re
import secrets
from datetime import timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.subagents.base import BaseSubAgent, SubAgentResult
from src.agent.tool_registry import COMPLAINT, call_tool
from src.agent.tools import args_hash
from src.auth.schemas import Principal
from src.config import settings
from src.models import utcnow


KNOWN_LANDMARKS = [
    "clock tower",
    "rajpur road",
    "subhash road",
    "paltan bazaar",
    "jakhan",
    "it park",
    "prem nagar",
    "sahastradhara road",
    "ballupur",
    "gandhi park",
    "parade ground",
    "dharampur",
    "karanpur",
    "ec road",
    "haridwar road",
    "chakrata road",
    "ghanta ghar",
    "घंटाघर",
    "राजपुर रोड",
    "पलटन बाजार",
    "गांधी पार्क",
]


def extract_category(text: str) -> str | None:
    lower = text.lower()
    if any(k in lower for k in ["pothole", "crater", "broken road", "road damage", "asphalt", "गड्ढा", "गड्ढे", "सड़क"]):
        return "Potholes and Road Damage"
    if any(k in lower for k in ["streetlight", "street light", "street lamp", "dark", "light", "स्ट्रीट लाइट", "अंधेरा", "लाइट"]):
        return "Defective Streetlights"
    if any(k in lower for k in ["garbage", "trash", "waste", "dustbin", "dump", "sanitation", "कूड़ा", "कचरा", "सफाई", "डस्टबिन"]):
        return "Garbage and Sanitation Dumps"
    if any(k in lower for k in ["water leak", "pipeline", "drain", "sewage", "manhole", "water supply", "सीवर", "नाली", "पानी", "मैनहोल"]):
        return "Blocked Drains and Water Supply"
    if any(k in lower for k in ["encroachment", "illegal parking", "footpath blocked", "अतिक्रमण"]):
        return "Encroachments and Traffic Obstructions"
    if any(k in lower for k in ["complaint", "grievance", "issue", "damaged", "broken", "overflow", "not working", "fix", "repair", "problem", "शिकायत", "समस्या"]):
        return "Civic Grievance"
    return None


def extract_location(text: str) -> str | None:
    lower = text.lower()

    # 1. Match preposition phrases (English)
    match = re.search(
        r"(?:at|near|on|in|opposite|around|close to|behind)\s+([A-Za-z0-9\s,.-]{3,60}?)(?:,|\.|$|\s+(?:and|because|causing|damaging|blocking|leaking|overflowing|which|where|since|due|with|is|are|has|have|for|that|please))",
        text,
        re.IGNORECASE,
    )
    if match:
        loc = match.group(1).strip()
        loc = re.sub(r"^(?:at|near|on|in|opposite)\s+", "", loc, flags=re.IGNORECASE).strip(".,;: ")
        if len(loc) >= 3 and loc.lower() not in {"the road", "the street", "my area", "this area"}:
            return loc

    # 2. Check known landmarks
    for landmark in KNOWN_LANDMARKS:
        if landmark in lower:
            pattern = re.compile(rf"\b([A-Za-z0-9\s]{{0,25}}{re.escape(landmark)}[A-Za-z0-9\s]{{0,25}})\b", re.IGNORECASE)
            m = pattern.search(text)
            if m:
                found = m.group(1).strip(".,;: ")
                found = re.sub(r"^(?:at|near|on|in|opposite)\s+", "", found, flags=re.IGNORECASE).strip(".,;: ")
                if len(found) >= 3:
                    return found
            return landmark.title()

    # 3. Hindi preposition pattern match
    hindi_match = re.search(
        r"([A-Za-z0-9\s\u0900-\u097f]{3,60}?)\s*(?:के पास|में|पर|रोड|चौक|मार्ग|बाजार|कॉलोनी|गली)",
        text,
    )
    if hindi_match:
        loc = hindi_match.group(1).strip()
        if len(loc) >= 3:
            return loc

    return None


TRACKING_RE = re.compile(r"\b(NND-2026-\d{4}|CMP-\d{4}-[A-F0-9]{6}|MOCK-[A-F0-9]+|\b0?84[1-9]\b)", re.IGNORECASE)
ESCALATE_RE = re.compile(r"escalat|overdue|no action|not resolved|still pending|ऊपर भेज|एस्केलेट", re.IGNORECASE)
REASSIGN_RE = re.compile(r"reassign|another worker|different (?:worker|team)|rapid action|दूसरा कर्मचारी", re.IGNORECASE)
# Issues where a photo makes the difference for the field crew.
PHOTO_HELPS_RE = re.compile(
    r"sewage|sewer|drain|overflow|garbage|trash|waste|dump|dead animal|manhole|leak|waterlog|encroach|pothole|"
    r"crater|broken|debris|नाली|सीवर|कचरा|कूड़ा|गड्ढा|मैनहोल|जलभराव",
    re.IGNORECASE,
)
VERIFY_RE = re.compile(r"verify|proof|evidence|really (?:fixed|resolved)|सत्यापित|सबूत", re.IGNORECASE)


class CivicComplaintSpecialist(BaseSubAgent):
    name: str = COMPLAINT
    description: str = "Specialist for civic grievances, complaint intake, deduplication, and verification"

    async def execute(
        self,
        session: AsyncSession | None,
        principal: Principal,
        message: str,
        context: Any = None,
        language: str = "en",
        **kwargs: Any,
    ) -> SubAgentResult:
        execution_steps: list[str] = []
        trace = kwargs.get("trace")
        uid = principal.user_id

        history = kwargs.get("history") or []
        last_turn_context = ""
        if history:
            last_turn_context = " ".join(
                [m.get("content", "") for m in history[-4:] if isinstance(m, dict) and m.get("role") == "user" and m.get("content")]
            )
        full_query_context = f"{last_turn_context} {message}".lower()

        # Step 0A: Check if tracking a specific ticket ID (e.g., "status of NND-2026-0841")
        tracking_match = TRACKING_RE.search(message)
        if tracking_match:
            raw_id = tracking_match.group(1).upper()
            tracking_id = raw_id if raw_id.startswith(("NND-", "MOCK-", "CMP-")) else f"NND-2026-0{raw_id.lstrip('0')}"
            lifecycle = await self._lifecycle_action(tracking_id, message, uid, language, trace, execution_steps)
            if lifecycle:
                return lifecycle
            execution_steps.append("query_complaint_status")
            status_data = await call_tool(COMPLAINT, "get_complaint_status", {"tracking_id": tracking_id}, uid, trace)
            if status_data.get("status") != "not_found":
                item = status_data.get("data") or status_data
                loc_val = item.get("location", {})
                loc_str = loc_val.get("address", "Dehradun") if isinstance(loc_val, dict) else str(loc_val or "Dehradun")
                note_val = item.get("citizen_notification", {})
                note_str = note_val.get("message", "Inspection underway.") if isinstance(note_val, dict) else "Assigned and underway."
                worker_val = item.get("assigned_worker", {})
                worker_str = worker_val.get("name", "Field Crew") if isinstance(worker_val, dict) else str(worker_val or "Field Crew")

                if language == "hi":
                    resp = (
                        f"शिकायत टिकट **#{tracking_id}** की वर्तमान स्थिति:\n\n"
                        f"• **श्रेणी:** {item.get('category', 'नागरिक शिकायत')}\n"
                        f"• **स्थान:** {loc_str}\n"
                        f"• **स्थिति:** **{item.get('status', 'IN_PROGRESS')}**\n"
                        f"• **प्रभारी दल:** {worker_str}\n"
                        f"• **नवीनतम अपडेट:** {note_str}"
                    )
                else:
                    resp = (
                        f"Current status report for Ticket **#{tracking_id}**:\n\n"
                        f"• **Category:** {item.get('category', 'Civic Grievance')}\n"
                        f"• **Location:** {loc_str}\n"
                        f"• **Current Status:** **{item.get('status', 'IN_PROGRESS')}**\n"
                        f"• **Assigned Unit:** {worker_str}\n"
                        f"• **Field Update:** {note_str}"
                    )
                return SubAgentResult(
                    status="ANSWERED",
                    response_text=resp,
                    cta="report_issue",
                    execution_steps=execution_steps,
                    metadata={"tracking_id": tracking_id, "queried": True},
                )

        # Step 0B: Check if citizen is asking to LIST / SHOW active complaints
        # E.g. "check active complaints", "show all which are active", "list complaints"
        is_list_query = any(
            re.search(pat, message, re.IGNORECASE)
            for pat in [
                r"\b(?:check|show|list|view|track|status|get|see|display)\b.*\b(?:complaints?|grievances?|tickets?)\b",
                r"\b(?:active|my|all|open|pending)\s+(?:complaints?|grievances?|tickets?)\b",
                r"\b(?:complaints?|grievances?|tickets?)\s+(?:status|list|active)\b",
                r"\b(?:show|list|check|view)\s+all\s+(?:which\s+are\s+)?active\b",
                r"\b(?:show|list|check)\s+active\b",
                r"(?:सक्रिय|मेरी|सभी)\s+(?:शिकायत|शिकायतें|समस्याएं)",
                r"शिकायत\s+(?:की\s+स्थिति|दिखाओ|जांचें|सूची)",
            ]
        ) or (
            ("complaint" in full_query_context or "शिकायत" in full_query_context)
            and any(w in message.lower() for w in ["active", "all", "show", "list", "check", "open", "pending", "सक्रिय", "दिखाओ"])
        )

        if is_list_query:
            execution_steps.append("list_active_complaints")
            tool_data = await call_tool(COMPLAINT, "list_user_complaints", {"user_id": uid}, uid, trace)
            complaints = tool_data.get("complaints") or []

            if language == "hi":
                lines = []
                for c in complaints:
                    loc = c.get("location", "देहरादून")
                    lines.append(f"• **#{c['tracking_id']} [{c['status']}]**: {c['category']} - {c['description'][:80]} (स्थान: {loc})")
                resp = (
                    "देहरादून नगर निगम में वर्तमान में सक्रिय नागरिक शिकायतें:\n\n"
                    + "\n\n".join(lines)
                    + "\n\nविस्तृत जानकारी के लिए टिकट संख्या लिखें (जैसे: *#NND-2026-0841*) या नया मुद्दा दर्ज करें।"
                )
            else:
                lines = []
                for c in complaints:
                    loc = c.get("location", "Dehradun")
                    lines.append(
                        f"• **#{c['tracking_id']}** [{c['status']}]: **{c['category']}**\n"
                        f"  - **Issue:** {c['description']}\n"
                        f"  - **Location:** {loc}\n"
                        f"  - **Team:** {c.get('assigned_worker', 'Field Unit')}"
                    )
                resp = (
                    "Here are the active municipal complaints and field work orders in Dehradun:\n\n"
                    + "\n\n".join(lines)
                    + "\n\nWould you like to check details for a specific ticket, or report a new civic issue?"
                )

            return SubAgentResult(
                status="ANSWERED",
                response_text=resp,
                cta="report_issue",
                execution_steps=execution_steps,
                metadata={"active_count": len(complaints), "queried": True},
            )

        # Step 1: Parse & validate required parameters (category, location, description)
        execution_steps.append("parse_and_validate")

        provided_args = kwargs.get("args") or {}
        category = (
            kwargs.get("category")
            or provided_args.get("category")
            or extract_category(message)
        )
        location = (
            provided_args.get("location")
            or extract_location(message)
            or kwargs.get("location")  # resolved by the main agent (e.g. from GPS)
        )
        description = (
            kwargs.get("description")
            or provided_args.get("description")
            or (message.strip() if len(message.strip()) >= 10 else None)
        )

        missing_fields: list[str] = []
        if not category or category == "Civic Grievance":
            missing_fields.append("category")
        if not location:
            missing_fields.append("location")
        if not description or len(description.strip()) < 15 or description.lower().strip() in (
            "i want to file a complaint", "file a complaint", "complaint", "lodge a complaint", "register complaint", "शिकायत दर्ज करनी है"
        ):
            missing_fields.append("description")

        # Step 2: If required parameters missing, clarify missing fields
        if missing_fields:
            execution_steps.append("clarify_missing_fields")

            if language == "hi":
                if "location" in missing_fields and "category" not in missing_fields:
                    clarification = (
                        f"मैंने आपकी **{category}** संबंधी शिकायत दर्ज करने के लिए विवरण तैयार करना शुरू कर दिया है। "
                        "कृपया वह सटीक स्थान या लैंडमार्क (जैसे: सड़क, चौक, कॉलोनी) बताएं जहाँ यह समस्या है।"
                    )
                elif "category" in missing_fields and "location" not in missing_fields:
                    clarification = (
                        f"कृपया **{location}** पर आ रही विशिष्ट नागरिक समस्या (जैसे: गड्ढा, स्ट्रीट लाइट, कचरा, नाली) का विवरण दें।"
                    )
                else:
                    clarification = (
                        "देहरादून नगर निगम में शिकायत दर्ज करने के लिए, मैं आपकी पूरी सहायता करूँगा। "
                        "कृपया समस्या का प्रकार और उसका सटीक स्थान बताएं:\n\n"
                        "• **समस्या का प्रकार:** (जैसे: गड्ढा, स्ट्रीट लाइट, कचरा, नाली)\n"
                        "• **सटीक स्थान:** (जैसे: राजपुर रोड, घंटाघर, या पलटन बाजार)\n\n"
                        "आप सीधे लिख सकते हैं: *'राजपुर रोड पर गड्ढा'*।"
                    )
            else:
                if "location" in missing_fields and "category" not in missing_fields:
                    clarification = (
                        f"I can help you lodge a complaint for **{category}**.\n\n"
                        "Could you please specify the exact location or landmark in Dehradun (e.g., street name, ward, or chowk) so our field crew can be dispatched?"
                    )
                elif "category" in missing_fields and "location" not in missing_fields:
                    clarification = (
                        f"Could you please describe the specific problem you are reporting at **{location}** (e.g., pothole, defective streetlight, garbage dump, drainage)?"
                    )
                else:
                    clarification = (
                        "I can help you lodge a civic complaint with Nagar Nigam Dehradun right away.\n\n"
                        "Please describe the specific issue and its location:\n"
                        "• **Issue Type:** (e.g., Pothole, Defective Streetlight, Garbage Dump, Water/Drainage)\n"
                        "• **Location:** (e.g., Subhash Road, Clock Tower, Paltan Bazaar, or your ward)\n\n"
                        "You can also reply directly with details like *'Deep pothole on Subhash Road near Clock Tower'*."
                    )

            # Live LLM conversational enhancement with grounded fallback
            try:
                from src.providers.registry import generate_with_failover
                context_hint = [f"Category detected: {category or 'Civic Grievance'}, Missing: {', '.join(missing_fields)}"]
                gen = await generate_with_failover(
                    system=(
                        "You are City Sense, an empathetic municipal intake officer for Dehradun Nagar Nigam. "
                        "The citizen wants to lodge a civic issue. "
                        "Acknowledge their request warmly and in 2-3 concise sentences ask for the missing details "
                        f"({', '.join(missing_fields)}). "
                        "Mention helpful examples like 'pothole on Subhash Road' or 'broken streetlight near Clock Tower'."
                    ),
                    user=message,
                    context=context_hint,
                    language=language,
                )
                if gen and gen.text and len(gen.text.strip()) > 20:
                    clarification = gen.text.strip()
            except Exception:
                pass

            return SubAgentResult(
                status="CLARIFICATION_REQUIRED",
                response_text=clarification,
                cta="provide_details",
                execution_steps=execution_steps,
                metadata={
                    "missing_fields": missing_fields,
                    "parsed": {
                        "category": category,
                        "location": location,
                        "description": description,
                    },
                },
            )

        # Step 3: Deduplication check
        execution_steps.append("deduplication_check")
        duplicate_match = None
        try:
            complaint_list_res = await call_tool(COMPLAINT, "list_user_complaints", {"user_id": uid}, uid, trace)
            existing_complaints = complaint_list_res.get("complaints", [])
            for c in existing_complaints:
                same_cat = c.get("category", "").lower() == category.lower()
                c_loc = c.get("location", "").lower()
                overlap = any(word in c_loc for word in location.lower().split() if len(word) > 3)
                if same_cat and overlap:
                    duplicate_match = c
                    break
        except Exception:
            pass

        # Step 4: Propose action
        execution_steps.append("propose_action")
        token = secrets.token_urlsafe(32)
        expires_at = utcnow() + timedelta(seconds=settings.action_ttl_seconds)
        summary = f"Complaint ({category}) at {location}: {description[:150]}"
        action_args = {
            "category": category,
            "location": location,
            "description": description,
        }
        if kwargs.get("latitude") is not None and kwargs.get("longitude") is not None:
            action_args.update(latitude=float(kwargs["latitude"]), longitude=float(kwargs["longitude"]))

        action_dict = {
            "photo_suggested": bool(PHOTO_HELPS_RE.search(f"{category} {description}")),
            "token": token,
            "action_type": "create_complaint",
            "tool": "create_complaint",
            "summary": summary,
            "args": action_args,
            "expires_at": expires_at.isoformat(),
        }

        # Persist pending action to DB or memory
        if session and kwargs.get("session_id"):
            try:
                from src.models import PendingAction
                # Savepoint: a failed insert must not poison the turn's outer transaction.
                async with session.begin_nested():
                    session.add(PendingAction(
                        token=token,
                        session_id=kwargs["session_id"],
                        user_id=principal.user_id,
                        agent_id="municipal",
                        tool="create_complaint",
                        args=action_args,
                        args_hash=args_hash(action_args),
                        summary=summary,
                        expires_at=expires_at,
                    ))
            except Exception:
                from src.agent.offline import PENDING_ACTIONS
                PENDING_ACTIONS[token] = {
                    "token": token,
                    "user_id": principal.user_id,
                    "agent_id": "municipal",
                    "category": category,
                    "summary": summary,
                    "args": action_args,
                    "expires_at": expires_at,
                    "status": "pending",
                }
        else:
            from src.agent.offline import PENDING_ACTIONS
            PENDING_ACTIONS[token] = {
                "token": token,
                "user_id": principal.user_id,
                "agent_id": "municipal",
                "category": category,
                "summary": summary,
                "args": action_args,
                "expires_at": expires_at,
                "status": "pending",
            }

        duplicate_note = ""
        if duplicate_match:
            duplicate_note = (
                f"\n\n*Notice: An active complaint (#{duplicate_match.get('tracking_id')}) with status '{duplicate_match.get('status')}' "
                f"was recently filed for this area.*"
                if language != "hi"
                else
                f"\n\n*सूचना: इस क्षेत्र में हाल ही में स्थिति '{duplicate_match.get('status')}' के साथ शिकायत (#{duplicate_match.get('tracking_id')}) पहले से दर्ज है।*"
            )

        if language == "hi":
            response_text = (
                f"मैंने देहरादून नगर निगम के लिए **{category}** श्रेणी में शिकायत का मसौदा तैयार किया है:\n\n"
                f"• **स्थान:** {location}\n"
                f"• **विवरण:** {description}\n\n"
                "कृपया नीचे दिए गए विवरण की समीक्षा करें और संबंधित वार्ड निरीक्षण दल को भेजने के लिए 'Confirm' पर क्लिक करें।"
                f"{duplicate_note}"
            )
        else:
            response_text = (
                f"I have prepared a civic grievance draft for **{category}**:\n\n"
                f"• **Location:** {location}\n"
                f"• **Description:** {description}\n\n"
                "Please review the action card below and confirm to dispatch the Nagar Nigam Dehradun field unit."
                f"{duplicate_note}"
            )

        return SubAgentResult(
            status="ACTION_PENDING",
            response_text=response_text,
            action=action_dict,
            cta="confirm_complaint",
            execution_steps=execution_steps,
            metadata={
                "token": token,
                "category": category,
                "location": location,
                "duplicate_found": duplicate_match is not None,
                "duplicate_tracking_id": duplicate_match.get("tracking_id") if duplicate_match else None,
            },
        )

    async def _lifecycle_action(
        self, tracking_id: str, message: str, uid: str, language: str, trace: Any, steps: list[str]
    ) -> SubAgentResult | None:
        """Escalate / reassign / verify an existing ticket when the citizen asks for it."""
        hi = language == "hi"
        if ESCALATE_RE.search(message):
            steps.append("escalate_sla")
            res = await call_tool(COMPLAINT, "escalate_complaint_sla", {"tracking_id": tracking_id}, uid, trace)
            d = res.get("data") or res
            if d.get("status") == "not_found":
                return None
            text = (
                f"टिकट **#{tracking_id}** को अगले स्तर पर एस्केलेट किया गया। वर्तमान स्थिति: **{d.get('status')}**"
                + (f", प्राधिकारी: {d['current_authority']}" if d.get("current_authority") else "")
                if hi else
                f"Ticket **#{tracking_id}** has been escalated up the SLA ladder. Current stage: **{d.get('status')}**"
                + (f", now with: {d['current_authority']}" if d.get("current_authority") else "")
            )
            return SubAgentResult(status="ANSWERED", response_text=text, cta="track_complaint",
                                  execution_steps=steps, metadata={"tracking_id": tracking_id, "card": d})
        if REASSIGN_RE.search(message):
            steps.append("reassign_worker")
            res = await call_tool(COMPLAINT, "reassign_worker", {"tracking_id": tracking_id}, uid, trace)
            d = res.get("data") or res
            if d.get("status") == "not_found":
                return None
            worker = d.get("assigned_worker") or {}
            name = worker.get("team") or worker.get("name") if isinstance(worker, dict) else str(worker)
            text = (f"टिकट **#{tracking_id}** अब **{name}** को सौंपा गया है।" if hi
                    else f"Ticket **#{tracking_id}** has been reassigned to **{name}**.")
            return SubAgentResult(status="ANSWERED", response_text=text, cta="track_complaint",
                                  execution_steps=steps, metadata={"tracking_id": tracking_id, "card": d})
        if VERIFY_RE.search(message):
            steps.append("verify_photo_evidence")
            res = await call_tool(COMPLAINT, "verify_photo_evidence", {"tracking_id": tracking_id}, uid, trace)
            d = res.get("data") or res
            verdict = d.get("verdict", "UNVERIFIABLE")
            if verdict == "NOT_FOUND":
                return None
            text = (f"टिकट **#{tracking_id}** साक्ष्य जाँच: **{verdict}**" if hi
                    else f"Evidence check for ticket **#{tracking_id}**: **{verdict}**")
            if d.get("resolution_note"):
                text += f"\n\n> {d['resolution_note']}"
            return SubAgentResult(status="ANSWERED", response_text=text, cta="track_complaint",
                                  execution_steps=steps, metadata={"tracking_id": tracking_id, "card": d})
        return None
