# Legacy shim — delegate to the real implementation in tabs.email_notifications.
from tabs.email_notifications import render_notification_management

__all__ = ["render_notification_management"]
