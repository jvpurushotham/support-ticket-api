from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import (
    BulkRemoveBody,
    TicketCreateStandalone,
    TicketResponse,
    TicketDetailResponse,
    TicketComplexityUpdate,
    MessageResponse,
)
from app.services import ticket_service

router = APIRouter()


def _queue_404():
    raise HTTPException(status_code=404, detail="Queue not found")


def _ticket_404():
    raise HTTPException(status_code=404, detail="Ticket not found")


@router.post("/tickets", response_model=TicketResponse, status_code=201)
def create_ticket(data: TicketCreateStandalone, db: Session = Depends(get_db)):
    try:
        ticket = ticket_service.create_ticket(db, data)
        return TicketResponse(
            id=ticket.id,
            title=ticket.title,
            complexity=ticket.complexity,
            quantity=ticket.quantity,
        )
    except ValueError as e:
        if str(e) == "queue_not_found":
            _queue_404()
        if str(e) == "capacity_exceeded":
            raise HTTPException(
                status_code=400,
                detail="Total tickets would exceed queue capacity",
            )
        if str(e) == "invalid_quantity":
            raise HTTPException(status_code=400, detail="Invalid quantity")
        raise


@router.get("/tickets/{ticket_id}", response_model=TicketDetailResponse)
def get_ticket(ticket_id: str, db: Session = Depends(get_db)):
    ticket = ticket_service.get_ticket_by_id(db, ticket_id)
    if not ticket:
        _ticket_404()
    return TicketDetailResponse(
        id=ticket.id,
        title=ticket.title,
        complexity=ticket.complexity,
        quantity=ticket.quantity,
        queue_id=ticket.queue_id,
    )


@router.patch("/tickets/{ticket_id}/complexity", response_model=MessageResponse)
def update_ticket_complexity(
    ticket_id: str, data: TicketComplexityUpdate, db: Session = Depends(get_db)
):
    try:
        ticket_service.update_ticket_complexity(db, ticket_id, data.complexity)
        return MessageResponse(message="Complexity updated successfully")
    except ValueError as e:
        if str(e) == "ticket_not_found":
            _ticket_404()
        raise


@router.delete("/queues/{queue_id}/tickets/{ticket_id}", response_model=MessageResponse)
def remove_ticket_from_queue(
    queue_id: str,
    ticket_id: str,
    quantity: int | None = Query(None, gt=0),
    db: Session = Depends(get_db),
):
    try:
        ticket_service.remove_ticket_quantity(db, queue_id, ticket_id, quantity)
        return MessageResponse(message="Ticket(s) removed successfully")
    except ValueError as e:
        if str(e) == "queue_not_found":
            _queue_404()
        if str(e) == "ticket_not_found":
            _ticket_404()
        raise


@router.delete("/queues/{queue_id}/tickets", response_model=MessageResponse)
def bulk_remove_tickets(
    queue_id: str,
    body: BulkRemoveBody | None = Body(None),
    db: Session = Depends(get_db),
):
    ticket_ids = body.ticket_ids if body else None
    try:
        ticket_service.bulk_remove_tickets(db, queue_id, ticket_ids)
        return MessageResponse(message="Queue cleared successfully")
    except ValueError as e:
        if str(e) == "queue_not_found":
            _queue_404()
        raise
