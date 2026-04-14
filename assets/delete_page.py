import streamlit as st
import time
import pandas as pd
from core.utils import *
from conf.constants import *
from core.db import *
from core.auth import get_current_user, get_user_ip
from core.permissions import require_permission


def render_delete_asset():
    require_permission('assets.delete')
    st.header("Delete Asset")
    load_all()
    assets_df = st.session_state.assets_df.copy()

    if assets_df.empty:
        st.info("No assets available to delete.")
        return

    st.dataframe(assets_df[['name','cost_center']], use_container_width=True)
    sel_asset_name = st.selectbox("Select asset by name", options=[""] + assets_df['name'].tolist(), key="delete_sel_asset")
    if sel_asset_name:
        arow = assets_df[assets_df['name'] == sel_asset_name].iloc[0]
        st.markdown("---")
        st.warning(f"⚠️ You are about to delete asset: **{arow['name']}** (ID: {arow['id']})")
        st.write(f"**Cost Center:** {arow.get('cost_center', 'N/A')}")
        
        st.markdown("---")
        st.error("⚠️ **WARNING:** This action cannot be undone.")
        
        confirm_text = st.text_input("Type 'DELETE' to confirm", key="delete_asset_confirm")
        
        if st.button("Delete Asset", key="delete_asset_btn", type="primary"):
            if confirm_text != "DELETE":
                st.error("Please type 'DELETE' to confirm deletion.")
            else:
                if delete_asset(arow['id']):
                    # Log action
                    current_user = get_current_user()
                    log_action(
                        user_id=current_user['id'] if current_user else None,
                        user_name=current_user['name'] if current_user else 'System',
                        action_type='delete',
                        entity_type='asset',
                        entity_id=arow['id'],
                        entity_name=arow['name'],
                        action_details=f"Deleted asset: {arow['name']}",
                        ip_address=get_user_ip()
                    )
                    st.success(f"Asset deleted (ID {arow['id']})")
                    load_all()
                    st.session_state.selected_main = "🏢 Assets"
                    st.session_state.selected_sub = "Asset Management"
                    time.sleep(0.3)
                    st.rerun()
                else:
                    st.error("Failed to delete asset.")
