# Delete-dialog button colors (st-key-dlg_*). Row Edit/Delete/Create: style.css.
import streamlit as st


def inject_management_hub_button_css() -> None:
    """Lighter red/grey for delete confirmation dialog buttons (no tooltips — avoid help= on buttons)."""
    st.markdown(
        """
<style>
/* Delete dialog: Yes — light coral red */
.stApp [class*="st-key-dlg_ctr_y_"] button,
.stApp [class*="st-key-dlg_lss_y_"] button,
.stApp [class*="st-key-dlg_ast_y_"] button,
.stApp [class*="st-key-dlg_svc_y_"] button,
.stApp [class*="st-key-dlg_usr_y_"] button,
body [class*="st-key-dlg_ctr_y_"] button,
body [class*="st-key-dlg_lss_y_"] button,
body [class*="st-key-dlg_ast_y_"] button,
body [class*="st-key-dlg_svc_y_"] button,
body [class*="st-key-dlg_usr_y_"] button {
    background-color: #f1948a !important;
    color: #ffffff !important;
    border: 1px solid #ec7063 !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
}
.stApp [class*="st-key-dlg_ctr_y_"] button:hover,
.stApp [class*="st-key-dlg_lss_y_"] button:hover,
.stApp [class*="st-key-dlg_ast_y_"] button:hover,
.stApp [class*="st-key-dlg_svc_y_"] button:hover,
.stApp [class*="st-key-dlg_usr_y_"] button:hover,
body [class*="st-key-dlg_ctr_y_"] button:hover,
body [class*="st-key-dlg_lss_y_"] button:hover,
body [class*="st-key-dlg_ast_y_"] button:hover,
body [class*="st-key-dlg_svc_y_"] button:hover,
body [class*="st-key-dlg_usr_y_"] button:hover {
    background-color: #ec7063 !important;
    border-color: #e74c3c !important;
    color: #ffffff !important;
}

/* Cancel / Close — light grey */
.stApp [class*="st-key-dlg_ctr_n_"] button,
.stApp [class*="st-key-dlg_lss_n_"] button,
.stApp [class*="st-key-dlg_ast_n_"] button,
.stApp [class*="st-key-dlg_svc_n_"] button,
.stApp [class*="st-key-dlg_usr_n_"] button,
.stApp [class*="st-key-dlg_usr_self_"] button,
body [class*="st-key-dlg_ctr_n_"] button,
body [class*="st-key-dlg_lss_n_"] button,
body [class*="st-key-dlg_ast_n_"] button,
body [class*="st-key-dlg_svc_n_"] button,
body [class*="st-key-dlg_usr_n_"] button,
body [class*="st-key-dlg_usr_self_"] button {
    background-color: #e8eef2 !important;
    color: #37474f !important;
    border: 1px solid #cfd8dc !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
}
.stApp [class*="st-key-dlg_ctr_n_"] button:hover,
.stApp [class*="st-key-dlg_lss_n_"] button:hover,
.stApp [class*="st-key-dlg_ast_n_"] button:hover,
.stApp [class*="st-key-dlg_svc_n_"] button:hover,
.stApp [class*="st-key-dlg_usr_n_"] button:hover,
.stApp [class*="st-key-dlg_usr_self_"] button:hover,
body [class*="st-key-dlg_ctr_n_"] button:hover,
body [class*="st-key-dlg_lss_n_"] button:hover,
body [class*="st-key-dlg_ast_n_"] button:hover,
body [class*="st-key-dlg_svc_n_"] button:hover,
body [class*="st-key-dlg_usr_n_"] button:hover,
body [class*="st-key-dlg_usr_self_"] button:hover {
    background-color: #dfe7eb !important;
    border-color: #b0bec5 !important;
    color: #263238 !important;
}
</style>
        """,
        unsafe_allow_html=True,
    )


def inject_bulk_action_button_css() -> None:
    """Blue buttons for Distribution bulk-action dialog. Dialogs render under body; primary buttons use baseButton-primary (default red)."""
    st.markdown(
        """
<style>
/* Bulk action — keys dist_bulk_*; match body + .stApp + dialog/modal portals */
body [class*="st-key-dist_bulk_"] button,
.stApp [class*="st-key-dist_bulk_"] button,
[role="dialog"] [class*="st-key-dist_bulk_"] button,
[data-testid="stDialog"] [class*="st-key-dist_bulk_"] button,
[data-testid="stModal"] [class*="st-key-dist_bulk_"] button,
body [class*="st-key-dist_bulk_"] [data-testid="baseButton-primary"],
.stApp [class*="st-key-dist_bulk_"] [data-testid="baseButton-primary"],
[role="dialog"] [class*="st-key-dist_bulk_"] [data-testid="baseButton-primary"],
[data-testid="stDialog"] [class*="st-key-dist_bulk_"] [data-testid="baseButton-primary"],
[data-testid="stModal"] [class*="st-key-dist_bulk_"] [data-testid="baseButton-primary"],
body [class*="st-key-dist_bulk_"] [data-testid="baseButton-secondary"],
.stApp [class*="st-key-dist_bulk_"] [data-testid="baseButton-secondary"],
[role="dialog"] [class*="st-key-dist_bulk_"] [data-testid="baseButton-secondary"],
[data-testid="stDialog"] [class*="st-key-dist_bulk_"] [data-testid="baseButton-secondary"],
[data-testid="stModal"] [class*="st-key-dist_bulk_"] [data-testid="baseButton-secondary"] {
    background-color: #3498db !important;
    color: #ffffff !important;
    border: 1px solid #2980b9 !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
}
body [class*="st-key-dist_bulk_"] button:hover,
.stApp [class*="st-key-dist_bulk_"] button:hover,
[role="dialog"] [class*="st-key-dist_bulk_"] button:hover,
[data-testid="stDialog"] [class*="st-key-dist_bulk_"] button:hover,
[data-testid="stModal"] [class*="st-key-dist_bulk_"] button:hover {
    background-color: #2980b9 !important;
    border-color: #1f618d !important;
    color: #ffffff !important;
}
body [class*="st-key-dist_bulk_"] button p,
body [class*="st-key-dist_bulk_"] button span,
.stApp [class*="st-key-dist_bulk_"] button p,
.stApp [class*="st-key-dist_bulk_"] button span,
[role="dialog"] [class*="st-key-dist_bulk_"] button p,
[role="dialog"] [class*="st-key-dist_bulk_"] button span,
[data-testid="stDialog"] [class*="st-key-dist_bulk_"] button p,
[data-testid="stDialog"] [class*="st-key-dist_bulk_"] button span,
[data-testid="stModal"] [class*="st-key-dist_bulk_"] button p,
[data-testid="stModal"] [class*="st-key-dist_bulk_"] button span {
    color: #ffffff !important;
}
body [class*="st-key-dist_bulk_"] button:disabled,
.stApp [class*="st-key-dist_bulk_"] button:disabled,
[role="dialog"] [class*="st-key-dist_bulk_"] button:disabled,
[data-testid="stDialog"] [class*="st-key-dist_bulk_"] button:disabled,
[data-testid="stModal"] [class*="st-key-dist_bulk_"] button:disabled {
    background-color: #aed6f1 !important;
    border-color: #85c1e9 !important;
    color: #1b4f72 !important;
    opacity: 0.9 !important;
}
</style>
        """,
        unsafe_allow_html=True,
    )
