#!/usr/bin/env python3
"""
INSULINTEL Instruction Manager — Streamlit admin panel.

Run:
    streamlit run app/streamlit_app.py

Features:
  ✏️  Editor     — edit individual instruction modules
  📋  Preview    — see assembled text (live from editor state)
  🔍  Diff       — compare repo vs Snowflake
  ☁️  Live       — view current Snowflake state
  💬  Test       — chat with CORTEX.COMPLETE using your instructions
"""
from __future__ import annotations

import difflib
import subprocess
import sys
from pathlib import Path

import streamlit as st
import yaml

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]

# Prefer installed package; fall back to repo-relative import
try:
    import semantic_diff  # noqa: F401  — package is pip-installed
except ImportError:
    if str(REPO_ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(REPO_ROOT / "scripts"))

if str(REPO_ROOT / "app") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "app"))

from deployer import (  # noqa: E402
    deploy_semantic_view,
    deploy_agent_field,
    get_live_custom_instructions,
    get_live_agent_instructions,
    test_with_cortex,
)
from semantic_diff.assemble import (  # noqa: E402
    load_assembly_config as _load_assembly,
    read_module_data,
    read_module_content,
    concat_modules,
)
from snapshot_manager import (  # noqa: E402
    save_snapshot,
    list_snapshots,
    get_latest_snapshot,
    format_timestamp,
    snapshot_summary,
)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def load_assembly_config() -> dict:
    return _load_assembly(REPO_ROOT)


def read_module(rel_path: str) -> dict:
    return read_module_data(REPO_ROOT, rel_path)


def save_module(rel_path: str, content: str) -> None:
    """Write edited content back to a module YAML, preserving other fields."""
    full = REPO_ROOT / "instructions" / rel_path
    with open(full, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    data["content"] = content

    class _Dumper(yaml.SafeDumper):
        pass

    def _repr(dumper, val):
        style = "|" if "\n" in val else None
        return dumper.represent_scalar("tag:yaml.org,2002:str", val, style=style)

    _Dumper.add_representer(str, _repr)

    with open(full, "w", encoding="utf-8") as f:
        yaml.dump(
            data, f,
            Dumper=_Dumper,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
            width=10000,
        )


def get_shared_targets(module_path: str, assembly: dict) -> list[str]:
    """Return all targets (view.field / agent.field) that use this module."""
    targets: list[str] = []
    for view, fields in (assembly.get("semantic_views") or {}).items():
        for field, mods in (fields or {}).items():
            if module_path in (mods or []):
                targets.append(f"{view}.{field}")
    for agent, fields in (assembly.get("agent") or {}).items():
        for field, mods in (fields or {}).items():
            if module_path in (mods or []):
                targets.append(f"Agent:{agent}.{field}")
    return targets


def _get_modules(
    target_type: str, target: str, field: str, assembly: dict,
) -> list[str]:
    """Return the list of module paths for a given target/field."""
    section = "semantic_views" if target_type == "Semantic View" else "agent"
    return (assembly.get(section) or {}).get(target, {}).get(field, [])


def assemble_from_state(
    target_type: str, target: str, field: str, assembly: dict,
) -> str:
    """Assemble instruction text using editor state → file fallback."""
    modules = _get_modules(target_type, target, field, assembly)
    parts: list[str] = []
    for mod in modules:
        key = f"editor_{mod}"
        if key in st.session_state:
            text = st.session_state[key].strip()
        else:
            text = read_module_content(REPO_ROOT, mod)
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def assemble_from_files(
    target_type: str, target: str, field: str, assembly: dict,
) -> str:
    """Assemble instruction text from files only (ignores editor state)."""
    modules = _get_modules(target_type, target, field, assembly)
    return concat_modules(REPO_ROOT, modules)


# ── Connection ────────────────────────────────────────────────────────────

@st.cache_resource(ttl=300)
def init_connection():
    """Create and cache a Snowflake connection (returns None if unconfigured)."""
    try:
        import snowflake.connector

        sf = st.secrets["snowflake"]
        params = {}
        for key in (
            "account", "user", "password", "role", "warehouse",
            "database", "schema", "authenticator", "token",
        ):
            try:
                val = sf[key]
                if val:
                    params[key] = str(val)
            except KeyError:
                pass
        if "account" not in params:
            return None
        return snowflake.connector.connect(**params)
    except KeyError as ke:
        st.sidebar.warning(f"Missing secrets key: {ke}")
        return None
    except Exception as exc:
        st.sidebar.error(f"Snowflake connection failed: {exc}")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    st.set_page_config(
        page_title="INSULINTEL Instruction Manager",
        page_icon="🧬",
        layout="wide",
    )

    assembly = load_assembly_config()
    conn = init_connection()

    # ── Sidebar ───────────────────────────────────────────────────────────
    with st.sidebar:
        st.title("🧬 INSULINTEL")
        st.caption("Instruction Manager")

        if conn:
            st.success("Connected to Snowflake", icon="🟢")
        else:
            st.info("Offline — add .streamlit/secrets.toml", icon="🔌")

        st.divider()
        target_type = st.radio(
            "Target", ["Semantic View", "Agent"], horizontal=True,
        )

        if target_type == "Semantic View":
            target = st.selectbox(
                "View", ["SEM_ACTIVITY", "SEM_INSULINTEL", "SEM_NHANES"],
            )
            field = st.selectbox(
                "Field", ["sql_generation", "question_categorization"],
            )
        else:
            target = "INSULINTEL"
            st.text(f"Agent: {target}")
            field = st.selectbox(
                "Field",
                ["orchestration_instructions", "response_instructions"],
            )

        modules = _get_modules(target_type, target, field, assembly)

        st.divider()
        st.subheader("Modules")
        for mod in modules:
            st.caption(f"📄 {mod}")

        st.divider()

        # ── Action buttons ────────────────────────────────────────────────
        c1, c2 = st.columns(2)
        with c1:
            save_btn = st.button(
                "💾 Save Files", use_container_width=True, type="primary",
            )
        with c2:
            deploy_btn = st.button(
                "🚀 Deploy", use_container_width=True, disabled=not conn,
                help="Assemble from editor & deploy to Snowflake",
            )

        c3, c4 = st.columns(2)
        with c3:
            revert_btn = st.button(
                "⏪ Revert", use_container_width=True, disabled=not conn,
                help="Restore the previous deployment (auto-snapshot)",
            )
        with c4:
            commit_btn = st.button(
                "📝 Git Commit", use_container_width=True,
            )

    # ── Handle actions ────────────────────────────────────────────────────
    if save_btn:
        _do_save(modules)
    if deploy_btn and conn:
        _do_deploy(conn, target_type, target, field, assembly)
    if revert_btn and conn:
        _do_revert(conn, target_type, target, field, assembly)
    if commit_btn:
        _do_git_commit()

    # ── Tabs ──────────────────────────────────────────────────────────────
    tab_edit, tab_preview, tab_diff, tab_live, tab_test = st.tabs(
        ["✏️ Editor", "📋 Preview", "🔍 Diff", "☁️ Live", "💬 Test"],
    )
    with tab_edit:
        _render_editor(modules, assembly)
    with tab_preview:
        _render_preview(target_type, target, field, assembly)
    with tab_diff:
        _render_diff(conn, target_type, target, field, assembly)
    with tab_live:
        _render_live(conn, target_type, target, field)
    with tab_test:
        _render_test(conn, target_type, target, field, assembly)


# ═══════════════════════════════════════════════════════════════════════════
# Action handlers
# ═══════════════════════════════════════════════════════════════════════════

def _do_save(modules: list[str]) -> None:
    saved = 0
    for mod in modules:
        key = f"editor_{mod}"
        if key not in st.session_state:
            continue
        original = read_module(mod).get("content", "").strip()
        edited = st.session_state[key].strip()
        if edited != original:
            save_module(mod, st.session_state[key])
            saved += 1
    st.toast(
        f"Saved {saved} module(s)" if saved else "No changes to save",
        icon="💾" if saved else "ℹ️",
    )


def _do_deploy(conn, target_type, target, field, assembly) -> None:
    with st.spinner("Deploying to Snowflake…"):
        # 1. Capture current Snowflake state (pre-deploy snapshot)
        if target_type == "Semantic View":
            previous = get_live_custom_instructions(conn, target)
            if "_error" in previous:
                st.warning(
                    f"⚠️ Could not snapshot current state: {previous['_error']}. "
                    "Deploy will proceed without a revert point."
                )
                previous = {}

            ci: dict[str, str] = {}
            for f in ("sql_generation", "question_categorization"):
                ci[f] = assemble_from_state(target_type, target, f, assembly)

            # 2. Save snapshot before deploying
            if previous:
                save_snapshot(target_type, target, previous, ci, action="deploy")

            result = deploy_semantic_view(conn, target, ci)
        else:
            previous_agent = get_live_agent_instructions(conn)
            if "_error" in previous_agent:
                st.warning(
                    f"⚠️ Could not snapshot current state: {previous_agent['_error']}. "
                    "Deploy will proceed without a revert point."
                )
                previous_agent = {}

            text = assemble_from_state(target_type, target, field, assembly)

            prev_state = {field: previous_agent.get(field, "")}
            new_state = {field: text}

            if previous_agent:
                save_snapshot(target_type, target, prev_state, new_state, action="deploy")

            result = deploy_agent_field(conn, field, text)
    st.toast(result, icon="🚀" if "✅" in result else "❌")


def _do_revert(conn, target_type, target, field, assembly) -> None:
    snapshot = get_latest_snapshot(target)
    if not snapshot:
        st.toast(
            "No deployment snapshot found — nothing to revert to.",
            icon="⚠️",
        )
        return

    previous = snapshot["previous_state"]
    ts_display = format_timestamp(snapshot["timestamp"])

    with st.spinner(f"Reverting to state from {ts_display}…"):
        # Snapshot current state so the revert itself can be undone
        if target_type == "Semantic View":
            current = get_live_custom_instructions(conn, target)
            if "_error" not in current:
                save_snapshot(target_type, target, current, previous, action="revert")
            result = deploy_semantic_view(conn, target, previous)
        else:
            current_agent = get_live_agent_instructions(conn)
            if "_error" not in current_agent:
                cur_state = {field: current_agent.get(field, "")}
                save_snapshot(target_type, target, cur_state, previous, action="revert")
            field_text = previous.get(field, "")
            result = deploy_agent_field(conn, field, field_text)
    st.toast(f"Reverted to {ts_display}: {result}", icon="⏪")


def _do_git_commit() -> None:
    try:
        subprocess.run(
            ["git", "add", "instructions/", "semantic_views/"],
            cwd=str(REPO_ROOT),
            capture_output=True, text=True, timeout=10,
        )
        r = subprocess.run(
            ["git", "commit", "-m",
             "chore: update instructions via admin panel"],
            cwd=str(REPO_ROOT),
            capture_output=True, text=True, timeout=10,
        )
        msg = r.stdout.strip() or r.stderr.strip()
        st.toast(
            msg if msg else "Nothing to commit",
            icon="📝" if r.returncode == 0 else "⚠️",
        )
    except Exception as e:
        st.toast(f"Git error: {e}", icon="❌")


# ═══════════════════════════════════════════════════════════════════════════
# Tab renderers
# ═══════════════════════════════════════════════════════════════════════════

def _render_editor(modules: list[str], assembly: dict) -> None:
    st.header("Module Editor")
    st.caption(
        "Edit individual instruction modules. Click **💾 Save Files** to "
        "persist, then **🚀 Deploy** to push to Snowflake."
    )

    for mod in modules:
        data = read_module(mod)
        content = data.get("content", "")
        version = data.get("version", "")

        targets = get_shared_targets(mod, assembly)
        shared = len(targets) > 1

        label = f"📄 {mod}" + (f"  •  v{version}" if version else "")
        with st.expander(label, expanded=True):
            if shared:
                st.warning(
                    f"⚠️ Shared module — also used by: "
                    f"{', '.join(targets)}"
                )
            st.text_area(
                mod,
                value=content,
                height=min(max(content.count("\n") * 22, 120), 500),
                key=f"editor_{mod}",
                label_visibility="collapsed",
            )


def _render_preview(target_type, target, field, assembly) -> None:
    st.header("Assembled Preview")
    st.caption(
        "Shows assembled text from your **current edits** "
        "(not yet saved to disk)."
    )

    text = assemble_from_state(target_type, target, field, assembly)
    if text:
        st.code(text, language=None, line_numbers=True)
        st.caption(f"{len(text):,} characters")
    else:
        st.info("No instructions assembled for this target / field.")


def _render_diff(conn, target_type, target, field, assembly) -> None:
    st.header("Diff: Repo ↔ Snowflake")

    if not conn:
        st.info("Connect to Snowflake to view diffs.")
        return

    if st.button("🔄 Fetch from Snowflake", key="diff_fetch"):
        with st.spinner("Fetching…"):
            if target_type == "Semantic View":
                st.session_state["live_ci"] = get_live_custom_instructions(
                    conn, target,
                )
            else:
                st.session_state["live_agent"] = get_live_agent_instructions(
                    conn,
                )

    # Repo side (from files, not editor state)
    repo_text = assemble_from_files(target_type, target, field, assembly)

    # Snowflake side
    if target_type == "Semantic View":
        live = st.session_state.get("live_ci", {})
    else:
        live = st.session_state.get("live_agent", {})

    if not live:
        st.caption("Click **Fetch from Snowflake** to load the live state.")
        return

    if "_error" in live:
        st.error(f"Error fetching from Snowflake: {live['_error']}")
        return

    sf_text = live.get(field, "")

    if repo_text.strip() == sf_text.strip():
        st.success("✅ Repo and Snowflake are in sync for this field.")
    else:
        st.warning("⚠️ Differences detected")
        diff = difflib.unified_diff(
            sf_text.splitlines(keepends=True),
            repo_text.splitlines(keepends=True),
            fromfile="☁️  Snowflake (live)",
            tofile="📁 Repo (assembled)",
        )
        st.code("".join(diff), language="diff")

    # Side-by-side view
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("☁️ Snowflake")
        st.text_area(
            "sf", sf_text, height=400, disabled=True,
            label_visibility="collapsed", key="diff_sf",
        )
    with col2:
        st.subheader("📁 Repo")
        st.text_area(
            "repo", repo_text, height=400, disabled=True,
            label_visibility="collapsed", key="diff_repo",
        )


def _render_live(conn, target_type, target, field) -> None:
    st.header("Live Snowflake State")

    if not conn:
        st.info("Connect to Snowflake to view live state.")
        return

    if st.button("🔄 Refresh", key="live_refresh"):
        with st.spinner("Fetching…"):
            if target_type == "Semantic View":
                st.session_state["live_view"] = (
                    get_live_custom_instructions(conn, target)
                )
            else:
                st.session_state["live_agent_view"] = (
                    get_live_agent_instructions(conn)
                )

    if target_type == "Semantic View":
        live = st.session_state.get("live_view", {})
    else:
        live = st.session_state.get("live_agent_view", {})

    if not live:
        st.caption("Click **Refresh** to load the current Snowflake state.")
        return

    if "_error" in live:
        st.error(f"Error: {live['_error']}")
        return

    text = live.get(field, "")
    if text:
        st.code(text, language=None, line_numbers=True)
        st.caption(f"{len(text):,} characters")
    else:
        st.info("No instructions set for this field in Snowflake.")

    # ── Deployment History ────────────────────────────────────────────
    st.divider()
    st.subheader("Deployment History")

    history = list_snapshots(target=target, limit=15)
    if not history:
        st.caption("No deployment snapshots yet. Deploy to start tracking.")
    else:
        for i, snap in enumerate(history):
            summary = snapshot_summary(snap)
            with st.expander(summary, expanded=(i == 0)):
                action = snap.get("action", "deploy")
                fields_changed = list(snap.get("new_state", {}).keys())
                st.caption(
                    f"**Action:** {action.title()}  ·  "
                    f"**Fields:** {', '.join(fields_changed)}"
                )

                prev = snap.get("previous_state", {})
                new = snap.get("new_state", {})
                for fld in fields_changed:
                    prev_text = prev.get(fld, "")
                    new_text = new.get(fld, "")
                    if prev_text != new_text:
                        st.caption(f"**{fld}** — changed")
                        col_a, col_b = st.columns(2)
                        with col_a:
                            st.text_area(
                                "Before", prev_text, height=150,
                                disabled=True, key=f"hist_prev_{i}_{fld}",
                            )
                        with col_b:
                            st.text_area(
                                "After", new_text, height=150,
                                disabled=True, key=f"hist_new_{i}_{fld}",
                            )
                    else:
                        st.caption(f"**{fld}** — no change")


def _render_test(conn, target_type, target, field, assembly) -> None:
    st.header("📱 Test Your Changes")

    st.info(
        "After deploying, open the **InsuLintel app** to test the updated "
        "instructions against the live Cortex Agent.",
        icon="📱",
    )

    st.markdown(
        """
        ### Workflow

        | Step | Action | Button |
        |------|--------|--------|
        | 1 | Edit instruction modules | ✏️ **Editor** tab |
        | 2 | Preview assembled text | 📋 **Preview** tab |
        | 3 | Push to Snowflake | 🚀 **Deploy** (sidebar) |
        | 4 | Test in your app | 📱 Open InsuLintel |
        | 5a | Happy → persist changes | 💾 **Save** → 📝 **Git Commit** |
        | 5b | Not happy → undo | ⏪ **Revert** (sidebar) |

        ### How Snapshots Work

        Every **Deploy** automatically captures the current Snowflake state
        before overwriting.  
        **Revert** restores the captured state — you can always go back.

        View deployment history in the **☁️ Live** tab.

        ---
        *Direct agent testing in this panel is planned for a future release.*
        """
    )


# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    main()
