from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Ticket, Queue
from app.schemas import TicketBulkEntry, TicketCreate, TicketCreateStandalone


def create_ticket(db: Session, data: TicketCreateStandalone) -> Ticket:
    # Rejecting non-positive quantities early prevents invalid ticket batches from entering the database.
    if data.quantity <= 0:
        raise ValueError("invalid_quantity")

    if data.queue_id:
        queue = db.query(Queue).filter(Queue.id == data.queue_id).first()

        if not queue:
            raise ValueError("queue_not_found")

        if queue.current_ticket_count + data.quantity > queue.capacity:
            raise ValueError("capacity_exceeded")

        # With MAX_TICKETS_PER_QUEUE=10, adding 5 tickets when count is 0 fails because 5 < 10 is true. Valid adds are rejected; invalid ones can slip through when total is already ≥ 10.
        # Capacity limits must reject when usage exceeds the limit (>), not when it is below it (<). That is the standard guard-clause pattern for resource limits.
        
        if queue.current_ticket_count + data.quantity > settings.MAX_TICKETS_PER_QUEUE:
            raise ValueError("capacity_exceeded")

        ticket = Ticket(
            title=data.title,
            complexity=data.complexity,
            queue_id=data.queue_id,
            quantity=data.quantity,
        )
        db.add(ticket)
        queue.current_ticket_count += data.quantity
    else:
        ticket = Ticket(
            title=data.title,
            complexity=data.complexity,
            queue_id=None,
            quantity=data.quantity,
        )
        db.add(ticket)

    db.commit()
    db.refresh(ticket)
    return ticket


def add_ticket_to_queue(db: Session, queue_id: str, data: TicketCreate) -> Ticket:
    # This guard keeps invalid payloads out of the queue workflow before any state changes happen.
    if data.quantity <= 0:
        raise ValueError("invalid_quantity")

    queue = db.query(Queue).filter(Queue.id == queue_id).first()
    if not queue:
        raise ValueError("queue_not_found")
    if queue.current_ticket_count + data.quantity > queue.capacity:
        raise ValueError("capacity_exceeded")

    if queue.current_ticket_count + data.quantity > settings.MAX_TICKETS_PER_QUEUE:
        raise ValueError("capacity_exceeded")

    ticket = Ticket(
        title=data.title,
        complexity=data.complexity,
        queue_id=queue_id,
        quantity=data.quantity,
    )

    db.add(ticket)
    queue.current_ticket_count += data.quantity
    db.commit()
    db.refresh(ticket)
    return ticket


# No capacity check → queue can be overfilled.
# current_ticket_count never updated → counter drifts from reality.
# Per-ticket commit() → partial writes on failure.
# Invalid quantity <= 0 silently skipped instead of rejected (Pydantic already validates, but service layer should not hide bad data).

# Spec requires validating total new quantity before insert. Counters must stay in sync with actual data. One commit = atomicity.

def bulk_add_tickets(db: Session, queue_id: str, entries: list[TicketBulkEntry]) -> int:
    queue = db.query(Queue).filter(Queue.id == queue_id).first()
    if not queue:
        raise ValueError("queue_not_found")

    if not entries:
        return 0

    total_new_quantity = sum(e.quantity for e in entries)
    if total_new_quantity <= 0:
        raise ValueError("invalid_quantity")

    if queue.current_ticket_count + total_new_quantity > queue.capacity:
        raise ValueError("capacity_exceeded")

    if queue.current_ticket_count + total_new_quantity > settings.MAX_TICKETS_PER_QUEUE:
        raise ValueError("capacity_exceeded")

    try:
        # Creating all tickets in one transaction keeps the queue state consistent and avoids partial inserts.
        added = 0
        for e in entries:
            if e.quantity <= 0:
                raise ValueError("invalid_quantity")

            ticket = Ticket(
                title=e.title,
                complexity=e.complexity,
                queue_id=queue_id,
                quantity=e.quantity,
            )

            db.add(ticket)
            added += 1

        queue.current_ticket_count += total_new_quantity
        db.commit()
        return added
    except Exception:
        db.rollback()
        raise


def list_tickets_by_queue(db: Session, queue_id: str) -> list[Ticket]:
    queue = db.query(Queue).filter(Queue.id == queue_id).first()
    if not queue :
        raise ValueError("queue_not_found")
    return list(queue.tickets)


def get_ticket_by_id(db: Session, ticket_id: str) -> Ticket | None:
    return db.query(Ticket).filter(Ticket.id == ticket_id).first()


def update_ticket_complexity(db: Session, ticket_id: str, complexity: int) -> None:
    ticket = get_ticket_by_id(db, ticket_id)

    if not ticket:
        raise ValueError("ticket_not_found")

    # updated_at stays frozen at creation time. Auditing and “last modified” semantics break.
    # Updating the complexity and timestamp together ensures the ticket reflects the latest change.
    # Any mutation should refresh updated_at. The model already has onupdate=datetime.utcnow — overwriting it defeats that.
    
    ticket.complexity = complexity
    ticket.updated_at = datetime.now(timezone.utc)
    db.commit()


def remove_ticket_quantity(
    db: Session, queue_id: str, ticket_id: str, quantity: int | None
) -> None:
    queue = db.query(Queue).filter(Queue.id == queue_id).first()
    if not queue:
        raise ValueError("queue_not_found")
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id, Ticket.queue_id == queue_id).first()
    if not ticket:
        raise ValueError("ticket_not_found")
    if quantity is not None:
        to_remove = min(quantity, ticket.quantity)
        ticket.quantity -= to_remove
        queue.current_ticket_count -= to_remove
        if ticket.quantity <= 0:
            db.delete(ticket)
    else:
        queue.current_ticket_count -= ticket.quantity
        db.delete(ticket)
    db.commit()


def bulk_remove_tickets(
    db: Session, queue_id: str, ticket_ids: list[str] | None
) -> None:
    queue = db.query(Queue).filter(Queue.id == queue_id).first()
    if not queue:
        raise ValueError("queue_not_found")
    if ticket_ids is not None and len(ticket_ids) > 0:
        tickets = db.query(Ticket).filter(
            Ticket.queue_id == queue_id,
            Ticket.id.in_(ticket_ids),
        ).all()
        for ticket in tickets:
            queue.current_ticket_count -= ticket.quantity
            db.delete(ticket)
    else:
        for ticket in list(queue.tickets):
            queue.current_ticket_count -= ticket.quantity
            db.delete(ticket)
    db.commit()
