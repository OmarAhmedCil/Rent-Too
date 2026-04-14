import streamlit as st
import time
import pandas as pd
from core.utils import *
from conf.constants import *
from core.db import *
from core.auth import get_current_user, get_user_ip
from core.permissions import require_permission


def render_create_asset():
    require_permission('assets.create')
    st.header("Create Asset")
    load_all()
    assets_df = st.session_state.assets_df.copy()

    with st.form("form_add_asset", clear_on_submit=True):
        st.subheader("Add new asset")
        aname = st.text_input("Asset name")
        acost = st.text_input("Cost center")
        if st.form_submit_button("Save Asset"):
            if not aname.strip():
                st.error("Asset name required.")
            else:
                # Check if name already exists
                if not assets_df[assets_df['name'].str.strip() == aname.strip()].empty:
                    st.error("Asset name already exists.")
                else:
                    nid = next_int_id(assets_df, 101)
                    asset_data = {
                        "id": str(nid),
                        "name": aname.strip(),
                        "cost_center": acost.strip()
                    }
                    if insert_asset(asset_data):
                        # Log action
                        current_user = get_current_user()
                        log_action(
                            user_id=current_user['id'] if current_user else None,
                            user_name=current_user['name'] if current_user else 'System',
                            action_type='create',
                            entity_type='asset',
                            entity_id=str(nid),
                            entity_name=aname.strip(),
                            action_details=f"Created asset: {aname}",
                            ip_address=get_user_ip()
                        )
                        st.success(f"Asset saved: {aname} (ID {nid})")
                        load_all()
                        st.session_state.selected_main = "🏢 Assets"
                        st.session_state.selected_sub = "Asset Management"
                        time.sleep(0.3)
                        st.rerun()
                    else:
                        st.error("Failed to save asset.")
