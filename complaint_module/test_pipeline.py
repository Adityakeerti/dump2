import os
import sys
import tempfile
import unittest

# Keep test writes away from the real data/complaints.json.
os.environ.setdefault("COMPLAINT_STATE_DIR", tempfile.mkdtemp(prefix="complaint-test-"))
os.environ["OPERATOR_KEY"] = "test-operator-key"
OPERATOR = {"X-Operator-Key": "test-operator-key"}
from fastapi.testclient import TestClient

# Add module to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.server import app, SIMULATION_STATE
from app.storage import store
from app.models import ComplaintStatus

# Disable background loop during unit tests
SIMULATION_STATE["auto_tick_enabled"] = False


class TestComplaintModule(unittest.TestCase):
    def setUp(self):
        store.reset_complaints()
        self.client = TestClient(app)

    def tearDown(self):
        store.reset_complaints()

    def test_01_user_profile(self):
        """Single user account Aditya Sharma is available."""
        res = self.client.get("/api/user")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["user_id"], "CIT-2026-8921")
        self.assertEqual(data["full_name"], "Aditya Sharma")
        self.assertEqual(data["ward"], "Ward 14 - Rajpur Road")
        print("[PASS] User profile verified: single account CIT-2026-8921.")

    def test_02_authorities_profiles(self):
        """Higher authorities profiles are simulated from JSON."""
        res = self.client.get("/api/authorities")
        self.assertEqual(res.status_code, 200)
        authorities = res.json()
        self.assertEqual(len(authorities), 3)

        levels = [a["level"] for a in authorities]
        self.assertEqual(levels, [1, 2, 3])

        tiers = [a["tier_name"] for a in authorities]
        self.assertIn("Ward Officer", tiers[0])
        self.assertIn("Municipal Commissioner", tiers[1])
        self.assertIn("CM Portal", tiers[2])
        print("[PASS] Authorities profiles verified: Ward Officer, Commissioner, CM Portal.")

    def test_03_complaint_intake_and_worker_assignment(self):
        """User uploads photo without manual category -> Municipal Agent auto-classifies, assigns Worker and hands to Coordinator."""
        form_data = {
            "title": "Severe road cavity on Rajpur Road",
            # Category omitted! Municipal AI Agent automatically classifies from photo & text
            "description": "Vehicle axle damaged due to deep depression in asphalt road pothole",
            "address": "Rajpur Road, Ward 14",
            "sample_photo": "/uploads/sample_pothole.svg"
        }
        res = self.client.post("/api/complaints", data=form_data)
        self.assertEqual(res.status_code, 200)
        c = res.json()

        self.assertTrue(c["tracking_id"].startswith("CMP-2026-"))
        self.assertEqual(c["category"], "pothole")  # Auto-classified!
        self.assertEqual(c["status"], ComplaintStatus.WORKER_ASSIGNED.value)
        self.assertIsNotNone(c["assigned_worker"])
        self.assertEqual(c["assigned_worker"]["name"], "Rakesh Rawat")  # Pothole crew
        self.assertEqual(c["assigned_worker"]["team"], "Roads Rapid Repair Unit #3")
        self.assertEqual(c["coordinator_agent"], "Municipal Coordinator AI Agent")

        # Verify timeline events: CITIZEN filed -> MUNICIPAL_AGENT assigned worker
        timeline = c["timeline"]
        self.assertEqual(len(timeline), 2)
        self.assertEqual(timeline[0]["action"], "COMPLAINT_FILED")
        self.assertEqual(timeline[1]["action"], "WORKER_ASSIGNED")
        print(f"[PASS] Complaint filed ({c['tracking_id']}) -> Worker assigned ({c['assigned_worker']['name']}).")

    def test_04_full_escalation_ladder_to_cm_portal(self):
        """Coordinator escalates: Worker Assigned -> Warnings 1-5 -> Ward -> Commissioner -> CM Portal."""
        # 1. File complaint
        res = self.client.post("/api/complaints", data={
            "title": "Pothole Test",
            "category": "pothole",
            "description": "Test pothole",
            "sample_photo": "/uploads/sample_pothole.svg"
        })
        tracking_id = res.json()["tracking_id"]

        # Step 1: Warning 1
        res = self.client.post(f"/api/complaints/{tracking_id}/escalate-tick")
        c = res.json()
        self.assertEqual(c["status"], ComplaintStatus.WARNING_1.value)
        self.assertEqual(c["warnings_count"], 1)

        # Step 2: Warning 2
        res = self.client.post(f"/api/complaints/{tracking_id}/escalate-tick")
        c = res.json()
        self.assertEqual(c["status"], ComplaintStatus.WARNING_2.value)
        self.assertEqual(c["warnings_count"], 2)

        # Step 3: Warning 3
        res = self.client.post(f"/api/complaints/{tracking_id}/escalate-tick")
        c = res.json()
        self.assertEqual(c["status"], ComplaintStatus.WARNING_3.value)
        self.assertEqual(c["warnings_count"], 3)

        # Step 4: Warning 4
        res = self.client.post(f"/api/complaints/{tracking_id}/escalate-tick")
        c = res.json()
        self.assertEqual(c["status"], ComplaintStatus.WARNING_4.value)
        self.assertEqual(c["warnings_count"], 4)

        # Step 5: Warning 5 (100% breach)
        res = self.client.post(f"/api/complaints/{tracking_id}/escalate-tick")
        c = res.json()
        self.assertEqual(c["status"], ComplaintStatus.WARNING_5.value)
        self.assertEqual(c["warnings_count"], 5)

        # Step 6: Escalate to Ward Officer (Level 1)
        res = self.client.post(f"/api/complaints/{tracking_id}/escalate-tick")
        c = res.json()
        self.assertEqual(c["status"], ComplaintStatus.ESCALATED_WARD_OFFICER.value)
        self.assertIsNotNone(c["current_authority"])
        self.assertEqual(c["current_authority"]["tier_name"], "Ward Officer")

        # Step 7: Escalate to Municipal Commissioner (Level 2)
        res = self.client.post(f"/api/complaints/{tracking_id}/escalate-tick")
        c = res.json()
        self.assertEqual(c["status"], ComplaintStatus.ESCALATED_MUNICIPAL_COMMISSIONER.value)
        self.assertEqual(c["current_authority"]["tier_name"], "Municipal Commissioner")

        # Step 8: Escalate to CM Portal (Level 3 - Apex)
        res = self.client.post(f"/api/complaints/{tracking_id}/escalate-tick")
        c = res.json()
        self.assertEqual(c["status"], ComplaintStatus.ESCALATED_CM_PORTAL.value)
        self.assertIn("CM Portal", c["current_authority"]["tier_name"])

        print("[PASS] Full escalation ladder verified through all 5 warnings and 3 higher authority levels.")

    def test_05_worker_resolution(self):
        """Worker resolves task and coordinator closes grievance."""
        res = self.client.post("/api/complaints", data={
            "title": "Garbage dump",
            "category": "garbage",
            "description": "Garbage issue",
            "sample_photo": "/uploads/sample_garbage.svg"
        })
        tracking_id = res.json()["tracking_id"]

        resolve_res = self.client.post(
            f"/api/complaints/{tracking_id}/resolve",
            json={"resolution_note": "Trash cleared by sanitation unit"}
        )
        self.assertEqual(resolve_res.status_code, 200)
        c = resolve_res.json()
        self.assertEqual(c["status"], ComplaintStatus.RESOLVED.value)
        self.assertEqual(c["resolved_at_stage"], "WORKER_ASSIGNED")
        self.assertEqual(c["resolution_note"], "Trash cleared by sanitation unit")
        self.assertIsNotNone(c["resolution_time"])
        # Verify citizen notification was created and dispatched
        self.assertIsNotNone(c.get("citizen_notification"))
        self.assertEqual(c["citizen_notification"]["recipient"], "Aditya Sharma")
        self.assertIn("RESOLVED", c["citizen_notification"]["message"])
        print("[PASS] Worker resolution verified, resolved_at_stage captured, ticket marked RESOLVED, and citizen notification dispatched.")

    def test_06_spring_boot_feed_api(self):
        """Feed API serves all complaints for future Spring Boot com.citysense.civic consumption."""
        # Create one complaint
        self.client.post("/api/complaints", data={
            "title": "Broken Streetlight",
            "category": "streetlight",
            "description": "Dark spot on road",
            "sample_photo": "/uploads/sample_pothole.svg"
        })

        res = self.client.get("/api/feed")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertEqual(data["target_springboot_module"], "com.citysense.civic")
        self.assertTrue(data["spring_sync_ready"])
        self.assertEqual(data["summary"]["total_complaints"], 1)
        self.assertEqual(data["summary"]["active_unresolved"], 1)
        self.assertEqual(len(data["complaints"]), 1)
        self.assertEqual(data["complaints"][0]["category"], "streetlight")
        print("[PASS] Spring Boot Feed API verified: compliant with com.citysense.civic contract.")

    def test_07_ui_endpoint(self):
        """UI.html is accessible at GET / with blue-and-white theme."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.text
        if not os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "UI.html")):
            # The standalone UI moved to the unified dashboard; "/" serves a service landing page.
            self.assertIn("Civic Complaint", html)
            return
        self.assertIn("CitySense Civic Grievance & Escalation System", html)
        self.assertIn("Member C", html)
        self.assertIn("--primary: #1d4ed8;", html)
        print("[PASS] UI.html verified and accessible.")

    def test_07b_reassign_worker(self):
        """Stalled complaints can be reassigned to a rapid action squad."""
        res = self.client.post("/api/complaints", data={
            "title": "Deep pothole near Clock Tower",
            "description": "Large pothole on the main road causing two-wheeler accidents every evening.",
            "category": "pothole",
        })
        self.assertEqual(res.status_code, 200)
        tid = res.json()["tracking_id"]
        before = res.json()["assigned_worker"]
        out = self.client.post(f"/api/complaints/{tid}/reassign", json={"reason": "No progress"})
        self.assertEqual(out.status_code, 200)
        self.assertNotEqual(out.json()["assigned_worker"]["id"], (before or {}).get("id"))
        self.assertEqual(out.json()["timeline"][-1]["action"], "WORKER_REASSIGNED")
        self.assertEqual(self.client.post("/api/complaints/NOPE-1/reassign").status_code, 404)

    def test_08_langgraph_compiled_workflow(self):
        """LangGraph StateGraph nodes and conditional execution are verified."""
        from app.graph import civic_graph
        nodes = list(civic_graph.nodes.keys())
        expected_nodes = [
            'node_intake_classifier',
            'node_worker_dispatcher',
            'node_sla_governor',
            'node_authority_escalator',
            'node_resolution_handler',
            'node_citizen_notifier'
        ]
        for node in expected_nodes:
            self.assertIn(node, nodes)
        print(f"[PASS] LangGraph verified: {len(expected_nodes)} compiled graph nodes active.")


    def test_09_civic_guardrails_blocks_kadu(self):
        """Civic Guardrail blocks gibberish ('Kadu'), spam, and non-civic input with HTTP 422."""
        # 1. Test 'Kadu' single token gibberish
        res = self.client.post("/api/complaints", data={
            "title": "Kadu",
            "description": "Kadu"
        })
        self.assertEqual(res.status_code, 422)
        err = res.json()["detail"]
        self.assertEqual(err["error"], "CIVIC_GUARDRAIL_BLOCKED")
        self.assertIn("Kadu", err["message"])

        # 2. Test another random gibberish input
        res2 = self.client.post("/api/complaints", data={
            "title": "asdfghjk",
            "description": "test 12345678"
        })
        self.assertEqual(res2.status_code, 422)
        print("[PASS] Civic Guardrail verified: successfully blocked 'Kadu' and spam submissions.")

    def test_10_resolution_at_intermediate_warning_stage(self):
        """Resolving at Warning 2 marks resolved_at_stage as WARNING_2 without ticking higher stages."""
        res = self.client.post("/api/complaints", data={
            "title": "Overflowing public drain hazard",
            "description": "Monsoon drain overflowing across pedestrian lane near school",
            "address": "Rajpur Road, Ward 14"
        })
        tracking_id = res.json()["tracking_id"]

        # Advance to Warning 1, then Warning 2
        self.client.post(f"/api/complaints/{tracking_id}/escalate-tick")  # Warning 1
        self.client.post(f"/api/complaints/{tracking_id}/escalate-tick")  # Warning 2

        # Resolve now
        res_res = self.client.post(
            f"/api/complaints/{tracking_id}/resolve",
            json={"resolution_note": "Drain de-silted and cleared by crew"}
        )
        self.assertEqual(res_res.status_code, 200)
        c = res_res.json()
        self.assertEqual(c["status"], ComplaintStatus.RESOLVED.value)
        self.assertEqual(c["resolved_at_stage"], "WARNING_2")
        print("[PASS] Intermediate resolution verified: resolved_at_stage correctly pinned to WARNING_2.")

    def test_11_meta_ladder_matches_status_enum(self):
        """/api/meta lists every non-terminal status in escalation order, one label each."""
        meta = self.client.get("/api/meta").json()
        expected = [s.value for s in ComplaintStatus if s != ComplaintStatus.RESOLVED]
        self.assertEqual(meta["statuses"], expected)
        self.assertEqual(len(meta["escalationLadder"]), len(expected))

    def test_12_notices_publish_list_revoke(self):
        """Portal publishes a notice, the feed lists it newest-first, and it can be revoked."""
        from app import notices as notices_mod
        notices_mod._save([])

        first = self.client.post("/api/notices", json={"title": "Water supply shutdown", "department": "Jal Sansthan"}, headers=OPERATOR)
        self.assertEqual(first.status_code, 201, first.text)
        second = self.client.post("/api/notices", json={
            "title": "Road closure on Rajpur Road", "department": "PWD", "priority": "Urgent", "tags": [" roads ", ""],
        }, headers=OPERATOR).json()
        self.assertTrue(second["id"].startswith("NOT-"))
        self.assertTrue(second["referenceNumber"].startswith("UK-GOV/PWD/"))
        self.assertEqual(second["tags"], ["roads"])

        listed = self.client.get("/api/notices").json()
        self.assertEqual([n["id"] for n in listed], [second["id"], first.json()["id"]])

        self.assertEqual(self.client.delete(f"/api/notices/{second['id']}", headers=OPERATOR).status_code, 204)
        self.assertEqual(self.client.delete(f"/api/notices/{second['id']}", headers=OPERATOR).status_code, 404)
        self.assertEqual(len(self.client.get("/api/notices").json()), 1)

    def test_13_notices_validation_and_expiry(self):
        """Bad input is rejected; expired notices drop out of the feed unless asked for."""
        from app import notices as notices_mod
        notices_mod._save([])

        self.assertEqual(self.client.post("/api/notices", json={"title": "x", "department": "PWD"}, headers=OPERATOR).status_code, 422)
        self.assertEqual(self.client.post("/api/notices", json={
            "title": "Bad date", "department": "PWD", "expiryDate": "not-a-date"}, headers=OPERATOR).status_code, 422)

        self.client.post("/api/notices", json={
            "title": "Old advisory", "department": "PWD", "expiryDate": "2020-01-01T00:00:00Z"}, headers=OPERATOR)
        self.assertEqual(self.client.get("/api/notices").json(), [])
        self.assertEqual(len(self.client.get("/api/notices?include_expired=true").json()), 1)


    def test_14_notice_writes_need_operator_key(self):
        """Reads are public; publish/revoke need the operator key; no key configured disables writes."""
        body = {"title": "Unauthorised notice", "department": "PWD"}
        self.assertEqual(self.client.post("/api/notices", json=body).status_code, 401)
        self.assertEqual(self.client.post("/api/notices", json=body, headers={"X-Operator-Key": "wrong"}).status_code, 401)
        self.assertEqual(self.client.delete("/api/notices/NOT-X", headers={"X-Operator-Key": "wrong"}).status_code, 401)
        self.assertEqual(self.client.get("/api/notices").status_code, 200)
        os.environ["OPERATOR_KEY"] = ""
        try:
            self.assertEqual(self.client.post("/api/notices", json=body, headers=OPERATOR).status_code, 503)
        finally:
            os.environ["OPERATOR_KEY"] = "test-operator-key"


if __name__ == "__main__":
    unittest.main()
