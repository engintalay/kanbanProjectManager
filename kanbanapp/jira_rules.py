"""Jira statü kuralları — views ve models tarafından ortak kullanılır.

`views.is_issue_closed` ile aynı mantık; döngüsel import olmaması için
models.py doğrudan bu modülden okur (models -> views -> models kuralı olmasın).
"""

CLOSED_STATUS_NAMES = {
    "resolved",
    "closed",
    "ready",
    "done",
    "kapatıldı",
    "kapatildi",
    "kapalı",
    "kapali",
    "çözüldü",
    "cozuldu",
    "tamamlandı",
    "tamamlandi",
    "iptal",
    "cancelled",
    "canceled",
    "rejected",
    "bitti",
    "hazır",
    "hazir",
}

CLOSED_STATUS_PATTERNS = (
    "resolved",
    "closed",
    "ready",
    "done",
    "tamamlan",
    "kapatıl",
    "kapatil",
    "kapalı",
    "kapali",
    "çözül",
    "cozul",
    "bitti",
    "hazır",
    "hazir",
    "iptal",
    "cancel",
    "reject",
)


def is_issue_closed(issue_dict: dict) -> bool:
    """Return True if a Jira issue is resolved, closed, or ready."""
    # 1. statusCategory in Jira (e.g. 'done')
    cat = (issue_dict.get("status_category") or "").strip().lower()
    if cat in ("done", "closed"):
        return True

    # 2. resolution set
    if issue_dict.get("resolution"):
        return True

    # 3. status name matching closed / resolved / ready statuses (exact or pattern)
    status_name = (issue_dict.get("status_key") or "").strip().lower()
    if not status_name:
        return False

    if status_name in CLOSED_STATUS_NAMES:
        return True

    for pattern in CLOSED_STATUS_PATTERNS:
        if pattern in status_name:
            return True

    return False
