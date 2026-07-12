from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import (
    InsufficientEffortError,
    OutOfStockError,
    ResolveRequest,
    ResolveResponse,
    OvertimeBreakdownResponse,
)
from app.services import resolve_service

router = APIRouter()


@router.post("/resolve", response_model=ResolveResponse)
def resolve_ticket(data: ResolveRequest, db: Session = Depends(get_db)):
    try:
        result = resolve_service.resolve(db, data.ticket_id, data.effort_logged)
        return ResolveResponse(**result)
    except ValueError as e:
        if e.args and e.args[0] == "ticket_not_found":
            raise HTTPException(status_code=404, detail="Ticket not found")
        if e.args and e.args[0] == "out_of_stock":
            raise HTTPException(
                status_code=400,
                detail=OutOfStockError().model_dump(),
            )
        
        # Spec expects HTTP 400 with {"error": "Insufficient effort logged", "required": 40, "logged": 30}. Instead clients get HTTP 500.
        # Exception matching must use e.args[0] or typed exceptions — str(e) is unreliable for multi-argument ValueError.
        if e.args and e.args[0] == "insufficient_effort":
            required, logged = e.args[1], e.args[2]
            raise HTTPException(
                status_code=400,
                detail=InsufficientEffortError(required=required, logged=logged).model_dump(),
            )
        
        raise


@router.get("/resolve/overtime-breakdown", response_model=OvertimeBreakdownResponse)
def overtime_breakdown(overtime: int = Query(..., ge=0)):
    result = resolve_service.overtime_breakdown(overtime)
    return OvertimeBreakdownResponse(**result)
