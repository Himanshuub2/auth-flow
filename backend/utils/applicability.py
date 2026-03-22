"""Validate applicability_type + applicability_refs for events and documents."""

from fastapi import HTTPException, status


def validate_applicability_refs(applicability_type, refs: dict | list | None) -> None:
    kind = getattr(applicability_type, "value", applicability_type)

    if kind == "ALL":
        if refs is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="applicability_refs must be null when applicability_type is ALL",
            )
        return

    if kind == "DIVISION":
        if not isinstance(refs, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="applicability_refs must be an object for DIVISION",
            )
        keys = set(refs.keys())
        if keys != {"divisions", "designations"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="applicability_refs for DIVISION must contain only 'divisions' and 'designations'",
            )
        divisions = refs["divisions"]
        designations = refs["designations"]
        if not isinstance(divisions, list) or any(
            not isinstance(d, str) or not d.strip() for d in divisions
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="applicability_refs.divisions must be an array of non-empty strings for DIVISION",
            )
        if not isinstance(designations, list) or any(
            not isinstance(d, str) or not d.strip() for d in designations
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="applicability_refs.designations must be an array of non-empty strings for DIVISION",
            )
        if not divisions and not designations:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="applicability_refs for DIVISION must include at least one division or designation",
            )
        return

    if kind == "EMPLOYEE":
        if not isinstance(refs, list):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="applicability_refs must be an array of strings for EMPLOYEE",
            )
        if not refs or any(not isinstance(x, str) or not x.strip() for x in refs):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="applicability_refs must be a non-empty array of non-empty strings for EMPLOYEE",
            )
        return

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported applicability_type: {kind!r}",
    )
