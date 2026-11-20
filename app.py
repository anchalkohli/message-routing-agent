"""Streamlit workspace for the Message Routing Agent portfolio project."""
import hashlib
import os
import logging
import sqlite3
from pathlib import Path

import streamlit as st

from routing_agent import REGIONS, RULE_TYPES, run_agent, search_routes
from routing_files import (
    draft_csv, format_mt, load_routing_files, message_intervals, read_local_files, review_batch,
)

from routing_operations import check_production, log_review

LOGGER = logging.getLogger(__name__)
SAMPLES = Path(__file__).with_name("samples")
PROMPTS = (
    "Find NAM MT103 for DEMOUS33 and its copy route. Then review recreating the specific RR1.",
    "Review adding a NAM RR1 for DEMOUS55 MT103 to GCN 0101.",
    "Review adding a NAM route for DEMOUS55 MT103.",
)


@st.cache_data(max_entries=2)
def sample_files():
    return load_routing_files((SAMPLES / "fininrout.csv").read_bytes(),
                              (SAMPLES / "artrules.csv").read_bytes())


def evidence(dataset, row):
    primary, copy = st.columns(2)
    with primary:
        st.markdown(f"**FININROUT · Line {row['line']}**")
        st.code(dataset.route_source[row["line"]], language="text")
    with copy:
        st.markdown("**ARTRULES**")
        if row["copy_routing_found"] != "Yes":
            st.write("ARTRULES unavailable." if dataset.copies is None else "No matching copy route.")
        for match in row["artrules"]:
            st.caption(f"Line {match['line']} · Copy GCN {match['copy_gcn']}")
            st.code(dataset.copy_source[match["line"]], language="text")


def show_search(dataset, region, dataset_key):
    st.subheader("Find routing rules")
    with st.form("route_search"):
        a, b, c, d = st.columns(4)
        bic = a.text_input("Destination BIC")
        mt = b.text_input("Message type", placeholder="103, 200 TO 209")
        sender = c.text_input("Sender BIC")
        gcn = d.text_input("Destination GCN")
        wildcard = st.checkbox("Include wildcard")
        submitted = st.form_submit_button("Search routes", type="primary")
    if submitted:
        try:
            result = search_routes(region, bic.strip().upper() or None, message_intervals(mt),
                                   wildcard, sender.strip().upper() or None, gcn.strip() or None,
                                   rules=dataset.rules, copy_rules=dataset.copies)
            st.session_state.search = (dataset_key, result["matches"])
        except ValueError as error:
            st.session_state.pop("search", None)
            st.error(str(error))
    current = st.session_state.get("search")
    if current is None or current[0] != dataset_key:
        return
    matches = current[1]
    if not matches:
        st.info("No matching routing rules.")
        return
    a, b, c = st.columns(3)
    a.metric("Matches", len(matches))
    b.metric("Copy routes found", sum(row["copy_routing_found"] == "Yes" for row in matches)
             if dataset.copies is not None else "Unavailable")
    c.metric("Catch-All rules", sum(row["catch_all"] for row in matches))
    digest = hashlib.sha256(repr((dataset_key, matches)).encode()).hexdigest()[:16]
    left, right = st.columns(2)
    size = left.selectbox("Results per page", (25, 50, 100))
    page_count = (len(matches) + size - 1) // size
    page = right.number_input("Page", min_value=1, max_value=page_count, value=1,
                              key=f"page-{digest}-{size}")
    rows = matches[(page - 1) * size:page * size]
    grid = [{
        "Line": row["line"], "Type": row["rule_type"], "Destination BIC": row["bic"],
        "Message type": format_mt(row["first_mt"], row["last_mt"]), "Destination GCN": row["gcn"],
        "Sender BIC": row["sender"] or "", "Copy routing found": row["copy_routing_found"],
    } for row in rows]
    selected = st.dataframe(grid, hide_index=True, use_container_width=True,
                            on_select="rerun", selection_mode="single-row",
                            key=f"matches-{digest}-{size}-{page}").selection.rows
    st.caption("Select a row to inspect its FININROUT and ARTRULES records.")
    evidence(dataset, rows[selected[0] if selected else 0])


def show_review(dataset, region, dataset_key, audit=None):
    st.subheader("Review a proposed rule")
    form_key = f"review_rule-{dataset_key[0]}-{region}" if audit else "review_rule"
    with st.form(form_key):
        a, b, c = st.columns(3)
        kind = a.selectbox("Rule type", RULE_TYPES)
        bic = b.text_input("Proposed destination BIC")
        mt = c.text_input("Proposed message types", placeholder="103, 200 TO 209")
        a, b = st.columns(2)
        gcn = a.text_input("Proposed destination GCN", placeholder="0101")
        sender = b.text_input("Proposed sender BIC (optional)")
        if audit:
            reference = st.text_input("Change reference / BRD number", max_chars=80)
            comment = st.text_area("Review comment", max_chars=500)
        submitted = st.form_submit_button("Review proposal", type="primary")
    if submitted:
        try:
            proposal = {
                "region": region, "kind": kind, "bic": bic.strip().upper(),
                "message_types": mt.strip(), "gcn": gcn.strip(),
                "sender": sender.strip().upper() or None,
            }
            result = review_batch(**proposal, rules=dataset.rules)
            if audit:
                result["review_id"] = log_review(
                    audit, dataset_key[0], reference, comment, proposal, result
                )
            st.session_state.review = (dataset_key, result)
        except ValueError as error:
            st.session_state.pop("review", None)
            st.error(str(error))
        except sqlite3.Error:
            st.session_state.pop("review", None)
            LOGGER.exception("Could not persist a routing review")
            st.error("The audit database could not save this review. Try again after service is restored.")
    current = st.session_state.get("review")
    if current is None or current[0] != dataset_key:
        return
    result = current[1]
    review_id = result.get("review_id")
    if review_id:
        st.caption(f"Audit review ID {review_id} · Dataset {dataset_key[0][:12]}")
    if result["status"] == "Blocked":
        st.error("Proposal blocked")
        for item in result["findings"]:
            with st.expander(f"{item['type']} · MT {item['requested_mt']} · FININROUT line {item['line']}"):
                st.code(dataset.route_source[item["line"]], language="text")
        return
    st.success("Proposal passed validation. Draft ready for review.")
    draft = draft_csv(result["draft_rules"])
    st.code(draft, language="text")
    filename = f"routing_draft_{dataset_key[0][:12]}_{review_id}.csv" if review_id else "routing_draft.csv"
    st.download_button("Download draft CSV", draft, filename, "text/csv")


def show_assistant():
    st.subheader("Ask about routing")
    st.caption("The hosted model uses the bundled fictional rules. Enter fictional data only.")
    example = st.selectbox("Interview example", PROMPTS)
    with st.form("agent_request"):
        custom = st.text_area("Your question (optional)", max_chars=2000,
                              placeholder="Leave blank to run the selected example.")
        submitted = st.form_submit_button("Run assistant", type="primary")
    if submitted:
        st.session_state.pop("agent_result", None)
        if not os.environ.get("OPENAI_API_KEY") or not os.environ.get("OPENAI_MODEL"):
            st.info("Set OPENAI_API_KEY and OPENAI_MODEL before starting Streamlit to enable model tool calling.")
        else:
            try:
                with st.spinner("Checking routing evidence…"):
                    answer, trace = run_agent(custom.strip() or example)
                st.session_state.agent_result = answer, trace
            except (RuntimeError, ValueError) as error:
                st.error(str(error))
    if "agent_result" in st.session_state:
        answer, trace = st.session_state.agent_result
        st.write(answer)
        with st.expander(f"Tool trace · {len(trace)} calls"):
            st.json(trace)


def production_workspace():
    try:
        dataset, revision, audit = check_production()
    except (ValueError, OSError, sqlite3.Error):
        st.session_state.pop("review", None)
        st.session_state.pop("search", None)
        LOGGER.exception("Production readiness check failed")
        st.error("Routing data or the audit database is unavailable. Contact the service operator.")
        return
    regions = tuple(region for region in REGIONS if any(rule.region == region for rule in dataset.rules))
    region = st.sidebar.selectbox("Region", regions)
    st.sidebar.caption(f"Active dataset {revision[:12]}")
    st.sidebar.button("Reload active release")
    search, review = st.tabs(["Rule search", "Draft review"])
    with search:
        show_search(dataset, region, (revision, region))
    with review:
        show_review(dataset, region, (revision, region), audit)


def main():
    st.set_page_config(page_title="Message Routing Agent", layout="wide")
    st.title("Message Routing Agent")
    st.caption("Search routing rules, check copy routes, and review proposed changes.")
    profile = os.environ.get("ROUTING_MODE", "demo").strip().lower()
    if profile == "production":
        production_workspace()
        return
    if profile != "demo":
        st.error("Invalid ROUTING_MODE. Select demo or production in the service configuration.")
        return
    mode = st.sidebar.radio("Dataset", ["Bundled sample", "Local directory"])
    region = st.sidebar.selectbox("Region", REGIONS)
    dataset = None
    signature = "sample"
    if mode == "Bundled sample":
        dataset = sample_files()
    else:
        directory = os.environ.get("ROUTING_DATA_DIR", "").strip()
        if directory:
            st.sidebar.caption(f"Reading from {directory}")
            st.sidebar.button("Reload files")
            try:
                route_bytes, copy_bytes = read_local_files(directory)
                dataset = load_routing_files(route_bytes, copy_bytes)
                signature = (hashlib.sha256(route_bytes).hexdigest(),
                             hashlib.sha256(copy_bytes).hexdigest() if copy_bytes is not None else None)
            except (ValueError, OSError) as error:
                st.sidebar.error(str(error))
        else:
            st.sidebar.info("Set ROUTING_DATA_DIR before launching the app to load your local CSVs.")
    search, review, assistant = st.tabs(["Rule search", "Draft review", "Routing assistant"])
    if dataset is None:
        search.info("Load a routing CSV to search.")
        review.info("Load a routing CSV to review proposals.")
    elif mode == "Local directory" and dataset.rules and not any(
            rule.region == region for rule in dataset.rules):
        st.warning(f"No FININROUT records for {region}. Regions in this file: "
                   + ", ".join(sorted({rule.region for rule in dataset.rules})))
    else:
        with search:
            show_search(dataset, region, (signature, region))
        with review:
            show_review(dataset, region, (signature, region))
    with assistant:
        show_assistant()


if __name__ == "__main__":
    main()
