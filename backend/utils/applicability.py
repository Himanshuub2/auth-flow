"""Validate applicability_type + applicability_refs for events and documents.

Refs shape:
- ALL       -> refs must be None
- DIVISION  -> refs is a list of non-empty division strings, e.g. ["div1", "div2"]
- EMPLOYEE  -> refs is a list of non-empty employee identifiers, e.g. ["a@x.com", "b@x.com"]

DIVISION can only be set via the bulk applicability flow. Document/event save
endpoints pass ``allow_division=False`` to reject it.
"""

from fastapi import HTTPException, status

MAX_APPLICABILITY_COUNT = 1500
def _validate_string_array(refs, kind_label: str) -> None:
    if not isinstance(refs, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"applicability_refs must be an array of strings for {kind_label}",
        )
    if len(refs) > MAX_APPLICABILITY_COUNT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"applicability_refs must be less than {MAX_APPLICABILITY_COUNT} for {kind_label}",
        )
    if not refs or any(not isinstance(x, str) or not x.strip() for x in refs):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"applicability_refs must be a non-empty array of non-empty strings for {kind_label}",
        )


def validate_applicability_refs(
    applicability_type,
    refs: list | None,
    *,
    allow_division: bool = True,
) -> None:
    kind = getattr(applicability_type, "value", applicability_type)

    if kind == "ALL":
        if refs is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="applicability_refs must be null when applicability_type is ALL",
            )
        return

    if kind == "DIVISION":
        if not allow_division:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="DIVISION applicability can only be set via bulk applicability upload",
            )
        _validate_string_array(refs, "DIVISION")
        return

    if kind == "EMPLOYEE":
        _validate_string_array(refs, "EMPLOYEE")
        return

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported applicability_type: {kind!r}",
    )
