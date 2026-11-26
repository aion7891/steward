"""Local Streamlit UI for Steward — talks exclusively to AgentOS via StewardClient."""

from pathlib import Path

import streamlit as st

from steward.client import StewardClient


class StewardUI:
    """Renders Steward's local chat, approval cards, reports, and settings interface."""

    def __init__(self, client=None):
        """Initialize the UI with a StewardClient connected to AgentOS."""
        self.client = client or StewardClient()

    def render(self):
        """Build the Streamlit page layout, sidebar status, and four main tabs."""
        st.set_page_config(page_title="Steward — Local AI Assistant", layout="wide")
        st.title("Steward")
        st.caption("Local-first AI assistant for files, storage, and curated OKF memory.")

        health = self._safe_call(self.client.health)
        if health is None:
            st.warning(
                f"Steward is starting or unreachable at `{self.client.base_url}`. "
                "Start the API with `uv run python -m steward.api`."
            )
            return

        self._render_sidebar(health)
        tab_chat, tab_actions, tab_reports, tab_settings = st.tabs(
            ["Chat", "Approvals & Actions", "Reports & Suggestions", "Settings"]
        )
        with tab_chat:
            self._render_chat_tab()
        with tab_actions:
            self._render_actions_tab(health)
        with tab_reports:
            self._render_reports_tab()
        with tab_settings:
            self._render_settings_tab()

    def _render_sidebar(self, health):
        """Display system health, OKF stats, privacy status, and quick-trigger buttons."""
        with st.sidebar:
            st.header("System Status")
            models = health.get("models", {})
            okf = health.get("okf_stats", {})
            st.metric("OKF Concepts", okf.get("nodes", 0))
            st.metric("Graph Links", okf.get("edges", 0))
            st.metric("Pending Approvals", health.get("pending_actions", 0))
            st.write(f"**Model:** `{models.get('chat_provider')}/{models.get('chat_model')}`")
            st.write(f"**Dry-Run Mode:** `{health.get('safety', {}).get('dry_run')}`")

            if models.get("chat_provider") != "ollama":
                st.warning("Cloud model active: prompts may leave this machine.")

            if st.button("Run Scan Workflow Now", use_container_width=True):
                with st.spinner("Scanning folders, updating RAG & OKF..."):
                    res = self._safe_call(self.client.trigger_scan)
                if res:
                    st.success("Scan workflow finished.")

            if st.button("Generate Weekly Report", use_container_width=True):
                with st.spinner("Generating Markdown & HTML reports..."):
                    res = self._safe_call(lambda: self.client.generate_report("weekly", "both"))
                if res:
                    st.success(res.get("message", "Report generated."))

    def _render_chat_tab(self):
        """Interactive chat window routed to the Agno Orchestrator Team."""
        if "messages" not in st.session_state:
            st.session_state["messages"] = []

        for msg in st.session_state["messages"]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg.get("sources"):
                    st.caption("Sources: " + ", ".join(msg["sources"]))

        prompt = st.chat_input("Ask about your files, recent work, or cleanup ideas...")
        if prompt:
            st.session_state["messages"].append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    res = self._safe_call(lambda: self.client.chat(prompt)) or {}
                reply = res.get("reply", "Could not reach AgentOS.")
                sources = res.get("sources", [])
                st.markdown(reply)
                if sources:
                    st.caption("Sources: " + ", ".join(sources))
                st.session_state["messages"].append(
                    {"role": "assistant", "content": reply, "sources": sources}
                )

    def _render_actions_tab(self, health):
        """Show confirmation cards for proposed actions and undo buttons for completed ones."""
        st.subheader("Approval Cards & Action History")
        dry_run_default = bool(health.get("safety", {}).get("dry_run", True))
        data = self._safe_call(self.client.list_actions) or {}
        actions = data.get("actions", [])
        if not actions:
            st.info("No file actions recorded yet.")
            return

        for act in actions:
            aid, status = act["id"], act["status"]
            with st.container(border=True):
                st.markdown(f"**#{aid} [{status.upper()}] `{act['action_type']}`** — `{act['source_path']}`")
                if act.get("target_path"):
                    st.caption(f"Target: {act['target_path']}")
                st.caption(f"Reason: {act.get('reason') or 'n/a'}")
                cols = st.columns(3)
                if status == "proposed":
                    if cols[0].button("Approve", key=f"approve_{aid}"):
                        res = self._safe_call(lambda i=aid: self.client.approve_action(i, execute=True, dry_run=dry_run_default))
                        st.toast(res.get("message", "Approved") if res else "Failed")
                        st.rerun()
                    if cols[1].button("Reject", key=f"reject_{aid}"):
                        res = self._safe_call(lambda i=aid: self.client.reject_action(i))
                        st.toast(res.get("message", "Rejected") if res else "Failed")
                        st.rerun()
                elif status == "done":
                    if cols[0].button("Undo", key=f"undo_{aid}"):
                        res = self._safe_call(lambda i=aid: self.client.undo_action(i))
                        st.toast(res.get("message", "Undone") if res else "Failed")
                        st.rerun()

    def _render_reports_tab(self):
        """Display proactive recommendations and generated Markdown/HTML reports."""
        st.subheader("Proactive Recommendations")
        rec = self._safe_call(self.client.get_recommendations) or {}
        for sug in rec.get("suggestions", []):
            st.write(f"- **[{sug['priority'].upper()}] {sug['title']}** ({sug['reclaimable_mb']} MB) — {sug['reason']}")

        st.subheader("Generated Reports")
        rep_data = self._safe_call(self.client.list_reports) or {}
        for rep in rep_data.get("reports", []):
            st.write(f"- `{rep['period']}` | `{rep['path']}` ({rep['created_at']})")
            p = Path(rep["path"])
            if p.suffix == ".md" and p.exists():
                with st.expander(f"Preview {p.name}"):
                    st.markdown(p.read_text(encoding="utf-8"))

    def _render_settings_tab(self):
        """Allow viewing and updating model provider, model ID, dry-run mode, and folders."""
        st.subheader("Configuration")
        settings = self._safe_call(self.client.get_settings) or {}
        models = settings.get("models", {})
        safety = settings.get("safety", {})
        folders = settings.get("watched_folders", [])

        with st.form("steward_settings_form"):
            providers = ["ollama", "openai", "anthropic", "gemini"]
            cur_prov = models.get("provider", "ollama")
            provider = st.selectbox("Model Provider", providers, index=providers.index(cur_prov) if cur_prov in providers else 0)
            model_id = st.text_input("Model ID", value=models.get("model_id", "gemma3:4b"))
            dry_run = st.checkbox("Dry-Run Mode (log only, never modify files)", value=bool(safety.get("dry_run", True)))
            folders_text = st.text_area("Watched Folders (one per line)", value="\n".join(folders))
            if st.form_submit_button("Save Settings"):
                new_folders = [line.strip() for line in folders_text.splitlines() if line.strip()]
                res = self._safe_call(
                    lambda: self.client.update_settings(provider=provider, model_id=model_id, dry_run=dry_run, watched_folders=new_folders)
                )
                if res:
                    st.success("Settings saved to config.yaml.")

    @staticmethod
    def _safe_call(fn):
        """Execute an API call and show a clean UI error instead of crashing."""
        try:
            return fn()
        except Exception as exc:
            st.error(f"API error: {exc}")
            return None


if __name__ == "__main__":
    StewardUI().render()
