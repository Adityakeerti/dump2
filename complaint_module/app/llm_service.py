import os
import json
import re
from typing import Dict, Any, Optional
import httpx


def load_root_env() -> Dict[str, str]:
    """Reads keys from /home/aditya/Desktop/STUDY/SmartCity/.env and environment."""
    env_vars = dict(os.environ)
    env_paths = [
        "/home/aditya/Desktop/STUDY/SmartCity/.env",
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"),
    ]
    for p in env_paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip('"').strip("'")
                            if k not in env_vars or not env_vars[k]:
                                env_vars[k] = v
            except Exception:
                pass
    return env_vars


class LLMService:
    def __init__(self):
        self.reload_keys()

    def reload_keys(self):
        self.env = load_root_env()
        self.groq_key = self.env.get("GROQ_API_KEY", "")
        self.gemini_key = self.env.get("GEMINI_API_KEY", "")

    def _call_groq(self, prompt: str, system: str = "", max_tokens: int = 500) -> Optional[str]:
        if not self.groq_key:
            return None
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.groq_key}",
            "Content-Type": "application/json"
        }
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": "llama-3.1-8b-instant",
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.2
        }
        try:
            with httpx.Client(timeout=2.5) as client:
                res = client.post(url, json=payload, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    return data["choices"][0]["message"]["content"].strip()
                else:
                    return None
        except Exception:
            return None

    def _call_gemini(self, prompt: str, system: str = "") -> Optional[str]:
        if not self.gemini_key:
            return None
        # Support standard Gemini API key
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_key}"
        text_prompt = f"{system}\n\n{prompt}" if system else prompt
        payload = {
            "contents": [{"parts": [{"text": text_prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 500}
        }
        try:
            with httpx.Client(timeout=2.5) as client:
                res = client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates and "content" in candidates[0]:
                        parts = candidates[0]["content"].get("parts", [])
                        if parts:
                            return parts[0].get("text", "").strip()
                return None
        except Exception:
            return None

    def _call_any_llm(self, prompt: str, system: str = "", max_tokens: int = 500) -> Optional[str]:
        # Try Groq first, then Gemini
        res = self._call_groq(prompt, system, max_tokens)
        if res:
            return res
        res = self._call_gemini(prompt, system)
        if res:
            return res
        return None

    def evaluate_guardrail(self, title: str, description: str, address: str = "") -> Dict[str, Any]:
        """Civic Guardrail Validator.
        Enforces strict input validation to block gibberish (e.g. 'Kadu'), spam,
        and non-civic submissions before they enter the municipal workflow."""
        self.reload_keys()

        clean_title = (title or "").strip()
        clean_desc = (description or "").strip()
        combined = f"{clean_title} {clean_desc}".strip().lower()

        # 1. Immediate rejection for single words / known gibberish / spam tokens
        gibberish_tokens = {
            "kadu", "test", "testing", "asdf", "asdfghjk", "qwerty", "hello", "hi",
            "random", "none", "null", "blah", "foo", "bar", "spam", "xyz", "abc"
        }
        if clean_title.lower() in gibberish_tokens and len(clean_desc.split()) <= 2:
            return {
                "allowed": False,
                "reason": f"Input '{clean_title}' rejected by Municipal Guardrail: Submission contains gibberish or spam with no actionable civic infrastructure details.",
                "flag": "GIBBERISH_SPAM",
                "llm_powered": False
            }

        # 2. Minimum length & substantive character check
        if len(clean_title) < 4:
            return {
                "allowed": False,
                "reason": "Title is too short (< 4 chars). Please provide a descriptive headline of the municipal hazard.",
                "flag": "INSUFFICIENT_LENGTH",
                "llm_powered": False
            }

        if len(combined) < 10:
            return {
                "allowed": False,
                "reason": "Complaint description is too brief. Please describe the civic hazard so municipal crews can locate and inspect it.",
                "flag": "INSUFFICIENT_LENGTH",
                "llm_powered": False
            }

        # 3. Check for obvious keyboard smashing (e.g. repeated single characters 'aaaaa', 'zzzzz')
        if re.search(r"(.)\1{4,}", combined):
            return {
                "allowed": False,
                "reason": "Submission flagged as keyboard-mash / spam characters.",
                "flag": "KEYBOARD_MASH",
                "llm_powered": False
            }

        # 4. LLM-Powered Guardrail Check (if LLM is available)
        system_guardrail = (
            "You are the Municipal Ingestion Guardrail Officer for Dehradun Smart City. "
            "A citizen has submitted a civic complaint. You must protect municipal systems from spam, "
            "gibberish, and non-civic submissions (e.g., random names like 'Kadu', personal chats, jokes, commercial ads).\n"
            "Valid civic complaints concern public infrastructure: road damage, potholes, footpaths, garbage/solid waste, "
            "streetlights, dark spots, drainage, waterlogging, broken water pipes, fallen trees, open manholes, or municipal public hazards.\n"
            "Return valid JSON ONLY (no markdown):\n"
            "{\"allowed\": true, \"reason\": \"Valid civic report\", \"flag\": \"VALID\"} OR\n"
            "{\"allowed\": false, \"reason\": \"Detailed reason for rejection\", \"flag\": \"GIBBERISH|SPAM|NON_CIVIC\"}"
        )
        user_prompt = f"Title: {clean_title}\nDescription: {clean_desc}\nLocation: {address}"

        raw = self._call_any_llm(user_prompt, system=system_guardrail, max_tokens=150)
        if raw:
            try:
                clean = re.sub(r"^```json\s*", "", raw)
                clean = re.sub(r"^```\s*", "", clean)
                clean = re.sub(r"\s*```$", "", clean).strip()
                parsed = json.loads(clean)
                if "allowed" in parsed:
                    parsed["llm_powered"] = True
                    return parsed
            except Exception:
                pass

        # 5. Deterministic Civic Domain Validator (Rule-based Fallback)
        civic_keywords = [
            "pothole", "cavity", "crater", "road", "sadak", "gaddha", "asphalt", "tar", "footpath",
            "pavement", "sidewalk", "divider", "manhole", "drain", "drainage", "naali", "gutter",
            "sewer", "waterlog", "flood", "leak", "pipe", "water", "garbage", "trash", "waste",
            "kachra", "dustbin", "dump", "bin", "filth", "smell", "sanitation", "dead animal",
            "carcass", "streetlight", "light", "lamp", "pole", "wire", "blackout", "dark",
            "electricity", "bijli", "batti", "traffic", "signal", "hazard", "caved", "collapsed",
            "fallen tree", "debris", "obstruction", "danger", "repair", "accident", "broken"
        ]

        has_civic_context = any(kw in combined for kw in civic_keywords)
        if not has_civic_context:
            return {
                "allowed": False,
                "reason": (
                    f"Submission '{clean_title}' rejected by Municipal Guardrail: "
                    "The report does not describe a recognized civic infrastructure or municipal hazard "
                    "(e.g., road pothole, garbage spill, streetlight dark spot, or stormwater overflow)."
                ),
                "flag": "NON_CIVIC_OR_GIBBERISH",
                "llm_powered": False
            }

        return {
            "allowed": True,
            "reason": "Civic integrity verified by Municipal Guardrail.",
            "flag": "VALID",
            "llm_powered": False
        }

    def classify_and_route(self, text: str, title: str = "", location: str = "") -> Dict[str, Any]:
        """Uses LLM to understand citizen complaints without forcing the citizen

        to know government departments.

        Falls back gracefully to rule-based classification."""
        self.reload_keys()

        system_prompt = (
            "You are the Municipal Ingestion AI for Dehradun Nagar Nigam (Smart City). "
            "A citizen has reported a civic problem. Citizens do not know government departments. "
            "Your job is to analyze their description and classify it precisely into JSON.\n"
            "Departments and categories allowed:\n"
            "1. category: 'pothole' (Public Works & Road Infrastructure)\n"
            "2. category: 'garbage' (Sanitation & Waste Management)\n"
            "3. category: 'streetlight' (Electrical & Street Lighting)\n"
            "4. category: 'drainage' (Stormwater Drainage & Sewerage)\n"
            "Priorities: 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'.\n"
            "Return valid JSON ONLY, no markdown, format:\n"
            "{\"category\": \"pothole\", \"department\": \"Public Works & Road Infrastructure\", "
            "\"priority\": \"HIGH\", \"clean_title\": \"...\", \"reasoning\": \"...\"}"
        )
        user_prompt = f"Citizen Title: {title}\nDescription: {text}\nLocation: {location}"

        raw = self._call_any_llm(user_prompt, system=system_prompt)
        if raw:
            try:
                # Clean code fences if present
                clean = re.sub(r"^```json\s*", "", raw)
                clean = re.sub(r"^```\s*", "", clean)
                clean = re.sub(r"\s*```$", "", clean).strip()
                parsed = json.loads(clean)
                if "category" in parsed and "department" in parsed:
                    parsed["llm_powered"] = True
                    return parsed
            except Exception:
                pass

        # Robust Deterministic Fallback Engine
        combined = f"{title} {text}".lower()
        if any(w in combined for w in ["flood", "drain", "sewer", "waterlog", "gutter", "overflow", "naali"]):
            category = "drainage"
            department = "Stormwater Drainage & Sewerage"
            priority = "CRITICAL" if any(w in combined for w in ["flood", "danger", "school", "child"]) else "HIGH"
            reasoning = "Detected stormwater/drainage blockage keywords indicating waterlogging hazard."
        elif any(w in combined for w in ["light", "dark", "lamp", "pole", "wire", "blackout", "bijli", "streetlight"]):
            category = "streetlight"
            department = "Electrical & Street Lighting"
            priority = "MEDIUM"
            reasoning = "Detected streetlighting malfunction keywords creating dark spot safety risk."
        elif any(w in combined for w in ["garbage", "trash", "waste", "dump", "smell", "filth", "kachra"]):
            category = "garbage"
            department = "Sanitation & Waste Management"
            priority = "MEDIUM"
            reasoning = "Detected solid waste accumulation keywords requiring sanitation dispatch."
        elif any(w in combined for w in ["pothole", "cavity", "asphalt", "crater", "sadak", "pit", "road damage", "pavement"]):
            category = "pothole"
            department = "Public Works & Road Infrastructure"
            priority = "HIGH"
            reasoning = "Detected road pavement cavity keywords impacting vehicular transit safety."
        else:
            category = "pothole"
            department = "Public Works & Road Infrastructure"
            priority = "MEDIUM"
            reasoning = "General municipal issue routed to civil works department."

        return {
            "category": category,
            "department": department,
            "priority": priority,
            "clean_title": title or "Civic Infrastructure Issue",
            "reasoning": reasoning,
            "llm_powered": False
        }

    def generate_citizen_notification(
        self, citizen_name: str, tracking_id: str, title: str, address: str, resolution_note: str, worker_name: str
    ) -> Dict[str, Any]:
        """Generates an official, polite SMS/Push notification informing the citizen

        that their issue is fixed."""
        self.reload_keys()

        system_prompt = (
            "You are the automated Citizen Notification Officer for Dehradun Smart City. "
            "Write a concise, polite, and reassuring SMS/WhatsApp notification to a citizen "
            "informing them that their reported municipal problem has been successfully resolved on-site. "
            "Mention the tracking ID, location, what work was completed, and a thank you. "
            "Keep it under 300 characters."
        )
        user_prompt = (
            f"Citizen Name: {citizen_name}\nTracking ID: {tracking_id}\nProblem: {title}\n"
            f"Address: {address}\nWorker: {worker_name}\nFix Note: {resolution_note}"
        )

        msg = self._call_any_llm(user_prompt, system=system_prompt, max_tokens=150)
        llm_powered = True
        if not msg:
            llm_powered = False
            msg = (
                f"Dear {citizen_name}, your grievance [{tracking_id}] at {address} "
                f"has been successfully RESOLVED by {worker_name}. "
                f"Work done: '{resolution_note}'. Thank you for helping keep Dehradun clean & safe!"
            )

        return {
            "recipient": citizen_name,
            "channel": "SMS & Civic Mobile Push Notification",
            "message": msg,
            "llm_powered": llm_powered
        }

    def generate_escalation_memo(
        self, tracking_id: str, title: str, address: str, authority_tier: str, authority_name: str, warnings_count: int
    ) -> str:
        """Generates an official bureaucratic memo for escalated authorities."""
        self.reload_keys()

        system_prompt = (
            "You are the automated Chief Municipal Governance Engine. "
            "Draft an official executive escalation memo addressed to a senior authority "
            "regarding an unresolved citizen grievance that breached SLA after repeated field crew warnings. "
            "Tone: Administrative, precise, urgent. Limit to 3 sentences."
        )
        user_prompt = (
            f"To: {authority_name} ({authority_tier})\nComplaint ID: {tracking_id}\n"
            f"Subject: {title}\nLocation: {address}\nWarnings Issued: {warnings_count}/5\n"
            f"Reason: SLA breached by assigned municipal worker without on-site resolution."
        )

        memo = self._call_any_llm(user_prompt, system=system_prompt, max_tokens=180)
        if not memo:
            memo = (
                f"OFFICIAL ADMINISTRATIVE MEMO [{tracking_id}]: Addressed to {authority_name} ({authority_tier}). "
                f"Grievance '{title}' at {address} has reached SLA failure after {warnings_count} unanswered field warnings. "
                f"Immediate departmental intervention and review mandated under Civic SLA Protocol."
            )
        return memo


llm = LLMService()
