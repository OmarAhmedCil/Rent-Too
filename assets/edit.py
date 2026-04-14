import streamlit as st
import time
import pandas as pd
from core.utils import *
from conf.constants import *
from core.db import *
from core.auth import get_current_user, get_user_ip
from core.permissions import require_permission


def render_edit_asset():
    require_permission("assets.edit")
    st.header("Edit Asset")
    bc1, bc2 = st.columns([1, 4])
    with bc1:
        if st.button("← Management", key="asset_edit_back_mgmt"):
            st.session_state.pop("assets_edit_target_id", None)
            st.session_state.pop("assets_editing_id", None)
            st.session_state.selected_main = "🏢 Assets"
            st.session_state.selected_sub = "Asset Management"
            st.rerun()
    load_all()
    assets_df = st.session_state.assets_df.copy()

    if assets_df.empty:
        st.info("No assets available to edit.")
        return

    if "assets_edit_target_id" in st.session_state:
        st.session_state["assets_editing_id"] = str(
            st.session_state.pop("assets_edit_target_id")
        )

    aeid = st.session_state.get("assets_editing_id")

    if aeid:
        _m = assets_df[assets_df["id"].astype(str) == str(aeid)]
        if _m.empty:
            st.error("Asset not found or was removed.")
            st.session_state.pop("assets_editing_id", None)
            return
        arow = _m.iloc[0]
        st.caption(f"Editing **{arow.get('name', '')}** · ID `{aeid}`")
    else:
        sorted_names = sorted(assets_df["name"].astype(str).tolist())
        sel_asset_name = st.selectbox(
            "Select asset to edit",
            options=[""] + sorted_names,
            key="edit_sel_asset",
        )
        if not sel_asset_name:
            return
        arow = assets_df[assets_df["name"] == sel_asset_name].iloc[0]

    a_name = st.text_input("Name", value=arow["name"], key="edit_a_name")
    a_cost = st.text_input("Cost center", value=arow["cost_center"], key="edit_a_cost")

    if st.button("Save asset changes", key="save_asset_btn"):
        if not a_name.strip():
            st.error("Asset name cannot be empty.")
        else:
            other_assets = assets_df[assets_df["name"].str.strip() == a_name.strip()]
            if not other_assets.empty and other_assets.iloc[0]["id"] != arow["id"]:
                st.error("Asset name already taken by another asset.")
            else:
                asset_data = {"name": a_name.strip(), "cost_center": a_cost.strip()}
                if update_asset(arow["id"], asset_data):
                    current_user = get_current_user()
                    log_action(
                        user_id=current_user["id"] if current_user else None,
                        user_name=current_user["name"] if current_user else "System",
                        action_type="edit",
                        entity_type="asset",
                        entity_id=arow["id"],
                        entity_name=a_name.strip(),
                        action_details=f"Updated asset: {a_name}",
                        ip_address=get_user_ip(),
                    )
                    st.success("Asset updated.")
                    load_all()
                    st.session_state.selected_main = "🏢 Assets"
                    st.session_state.selected_sub = "Asset Management"
                    st.session_state.pop("assets_editing_id", None)
                    time.sleep(0.3)
                    st.rerun()
                else:
                    st.error("Failed to update asset.")
