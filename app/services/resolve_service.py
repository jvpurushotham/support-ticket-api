import time
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.config import settings
from app.models import Ticket


def resolve(db: Session, ticket_id: str, effort_logged: int) -> dict:
    # Two concurrent POST /resolve on the same ticket can both pass quantity > 0 and double-decrement incorrectly.
    # Spec says “Transaction must be atomic.” SELECT ... FOR UPDATE (pessimistic locking) prevents concurrent reads of stale state.
    
    ticket = db.execute(
        select(Ticket).where(Ticket.id == ticket_id).with_for_update()
    ).scalar_one_or_none()

    if not ticket:
        raise ValueError("ticket_not_found")
    
    if ticket.quantity <= 0:
        raise ValueError("out_of_stock")
    
    if effort_logged < ticket.complexity:
        raise ValueError("insufficient_effort", ticket.complexity, effort_logged)
    
    # Decrementing the ticket quantity here ensures a resolved batch is consumed exactly once.
    ticket.quantity -= 1
    if ticket.queue_id is not None:
        # Keep the queue counter in sync with the actual ticket inventory after resolution.
        ticket.queue.current_ticket_count -= 1

    # Overtime is defined as effort logged above the ticket complexity, and it must never be negative.
    overtime_returned = max(0, effort_logged - ticket.complexity)

    db.commit()
    db.refresh(ticket)

    return {
        "ticket": ticket.title,
        "complexity": ticket.complexity,
        "effort_logged": effort_logged,
        "overtime_returned": overtime_returned,
        "remaining_quantity": ticket.quantity,
        "message": "Ticket resolved successfully",
    }


def overtime_breakdown(overtime: int) -> dict:
    blocks = sorted(settings.STANDARD_EFFORT_BLOCKS, reverse=True)
    result: dict[str, int] = {}
    remaining = overtime
    for b in blocks:
        if remaining <= 0:
            break
        count = remaining // b
        if count > 0:
            result[str(b)] = count
            remaining -= count * b
    return {"overtime": overtime, "blocks": result}
