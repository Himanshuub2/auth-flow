def format_user_owner(
    organization_vertical: str | None,
    division_cluster: str | None,
    department: str | None,
) -> str | None:
    ov = (organization_vertical or "").strip()
    dc = (division_cluster or "").strip()
    dept = (department or "").strip()
    if not ov and not dc and not dept:
        return None
    return f"{ov}/{dc}/{dept}"
