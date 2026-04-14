# Download data hub: navigate to each export page (sidebar shows this hub only).
import streamlit as st

from core.permissions import has_permission, require_permission

DOWNLOAD_MAIN = "\U0001f4e5 Download Data"

# permission, sidebar sub-page title, card description, stable Streamlit key, section id
_HUB_EXPORTS = [
    (
        "download.contracts",
        "Download Contracts",
        "Filter contracts and export CSV.",
        "dl_hub_contracts",
        "master",
    ),
    (
        "download.lessors",
        "Download Lessors",
        "Filter lessors and export CSV.",
        "dl_hub_lessors",
        "master",
    ),
    (
        "download.assets",
        "Download Assets",
        "Assets and stores with filters.",
        "dl_hub_assets",
        "master",
    ),
    (
        "download.services",
        "Download Services",
        "Service catalog: id, name, description, currency.",
        "dl_hub_services",
        "master",
    ),
    (
        "download.distribution",
        "Download Distribution",
        "One row per lessor per month (split from contract-month totals).",
        "dl_hub_distribution",
        "distribution_payments",
    ),
    (
        "download.distribution",
        "Download Distribution (contract month)",
        "One row per contract per rent month — no lessor split.",
        "dl_hub_distribution_contract_month",
        "distribution_payments",
    ),
    (
        "download.service_distribution",
        "Download Service Distribution",
        "Service lines by contract and month.",
        "dl_hub_service_dist",
        "distribution_payments",
    ),
    (
        "download.payments",
        "Download Payments",
        "Payment lines: gross, due, tax, withholding, CSV.",
        "dl_hub_payments",
        "distribution_payments",
    ),
]

_SECTIONS = [
    (
        "master",
        "Master data",
        "Contracts, lessors, assets, and services — reference exports.",
    ),
       (
        "distribution_payments",
        "Distribution and payments",
        "Contract-month schedules (per lessor or contract grain), service distribution, and payment exports.",
    ),
]


def _nav(sub: str) -> None:
    st.session_state.selected_main = DOWNLOAD_MAIN
    st.session_state.selected_sub = sub
    st.rerun()


def _export_card(title: str, description: str, button_key: str) -> None:
    with st.container(border=True):
        st.markdown(
            f'<p style="margin:0 0 0.35rem 0;font-size:1rem;font-weight:600;'
            f'color:#0f172a;line-height:1.3">{title}</p>',
            unsafe_allow_html=True,
        )
        st.caption(description)
        if st.button(
            "Open export",
            use_container_width=True,
            key=button_key,
        ):
            _nav(title)


def _render_section(heading: str, intro: str, cards: list) -> None:
    if not cards:
        return
    st.markdown(f"#### {heading}")
    st.caption(intro)
    for i in range(0, len(cards), 2):
        row = cards[i : i + 2]
        cols = st.columns(len(row))
        for col, (title, description, btn_key) in zip(cols, row):
            with col:
                _export_card(title, description, btn_key)


def render_download_management():
    require_permission("download.view")
    st.markdown("## Reports Center")
    st.caption(
        "Permission-controlled exports. Open a report to filter data and download CSV."
    )

    by_section: dict[str, list[tuple[str, str, str]]] = {}
    for perm, title, desc, key, sec in _HUB_EXPORTS:
        if not has_permission(perm):
            continue
        by_section.setdefault(sec, []).append((title, desc, key))

    visible_blocks = [
        (heading, intro, by_section[sid])
        for sid, heading, intro in _SECTIONS
        if by_section.get(sid)
    ]

    if not visible_blocks:
        st.info(
            "No download permissions are assigned to your role yet. "
            "Ask an administrator if you need exports."
        )
        return

    for idx, (heading, intro, cards) in enumerate(visible_blocks):
        _render_section(heading, intro, cards)
        if idx < len(visible_blocks) - 1:
            st.divider()
