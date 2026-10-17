def filter_person(record: dict):
    """Rule 6: people are GitHub handles only; name/company/email never enter the graph (AC-9)."""
    login = record.get("login") or record.get("github")
    return {"login": login} if login else None
