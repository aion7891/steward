"""HTTP client used by the local Streamlit UI to talk exclusively to AgentOS."""

import os

import httpx


class StewardClient:
    """Thin HTTP client wrapping Steward's AgentOS /steward/* endpoints."""

    def __init__(self, base_url=None, timeout=60.0, transport=None):
        """Initialize the client pointing at the local Steward AgentOS server."""
        raw_url = base_url or os.getenv("STEWARD_API_URL", "http://127.0.0.1:7777")
        self.base_url = raw_url.rstrip("/")
        self.timeout = float(timeout)
        self.transport = transport

    def _request(self, method, path, json_body=None, params=None):
        """Send one HTTP request and return the parsed JSON response."""
        with httpx.Client(
            base_url=self.base_url, timeout=self.timeout, transport=self.transport
        ) as client:
            response = client.request(method, path, json=json_body, params=params)
            response.raise_for_status()
            return response.json()

    def health(self):
        """Check API liveness, database, OKF graph stats, and pending action count."""
        return self._request("GET", "/steward/health")

    def trigger_scan(self, folders=None):
        """Trigger ScanWorkflow via AgentOS."""
        payload = {"folders": folders} if folders else {}
        return self._request("POST", "/steward/scan", json_body=payload)

    def chat(self, message):
        """Send a user question to the Agno Orchestrator Team."""
        return self._request("POST", "/steward/chat", json_body={"message": message})

    def list_actions(self, status=None, limit=50):
        """Fetch proposed, approved, completed, or undone file actions."""
        params = {"limit": limit}
        if status:
            params["status"] = status
        return self._request("GET", "/steward/actions", params=params)

    def approve_action(self, action_id, execute=True, dry_run=None):
        """Approve (and optionally execute) a proposed action by ID."""
        payload = {"execute": execute}
        if dry_run is not None:
            payload["dry_run"] = dry_run
        return self._request("POST", f"/steward/actions/{int(action_id)}/approve", json_body=payload)

    def reject_action(self, action_id, reason="Rejected via UI"):
        """Reject a proposed action by ID."""
        return self._request(
            "POST", f"/steward/actions/{int(action_id)}/reject", json_body={"reason": reason}
        )

    def undo_action(self, action_id):
        """Reverse a completed action from the archive or recycle bin."""
        return self._request("POST", f"/steward/actions/{int(action_id)}/undo")

    def list_reports(self, limit=20):
        """Return previously generated Markdown and HTML reports."""
        return self._request("GET", "/steward/reports", params={"limit": limit})

    def generate_report(self, period="weekly", output_format="markdown"):
        """Generate a new report via AgentOS."""
        return self._request(
            "POST",
            "/steward/reports",
            json_body={"period": period, "output_format": output_format},
        )

    def get_recommendations(self):
        """Fetch learned work patterns and proactive cleanup suggestions."""
        return self._request("GET", "/steward/recommendations")

    def get_settings(self):
        """Fetch current model, safety, and watched folder settings."""
        return self._request("GET", "/steward/settings")

    def update_settings(self, provider=None, model_id=None, dry_run=None, watched_folders=None):
        """Update Steward settings through the API."""
        payload = {}
        if provider is not None:
            payload["provider"] = provider
        if model_id is not None:
            payload["model_id"] = model_id
        if dry_run is not None:
            payload["dry_run"] = dry_run
        if watched_folders is not None:
            payload["watched_folders"] = watched_folders
        return self._request("PUT", "/steward/settings", json_body=payload)
