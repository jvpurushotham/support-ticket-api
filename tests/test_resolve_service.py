import unittest

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.db import Base, engine
from app.main import app
from app.models import Ticket
from app.services import resolve_service, ticket_service


class DummyTicket:
    def __init__(self):
        self.id = "ticket-1"
        self.title = "Test ticket"
        self.complexity = 40
        self.quantity = 2
        self.queue_id = None
        self.queue = None


class DummyResult:
    def __init__(self, ticket):
        self._ticket = ticket

    def scalar_one_or_none(self):
        return self._ticket


class DummyDB:
    def __init__(self, ticket):
        self.ticket = ticket

    def execute(self, *args, **kwargs):
        return DummyResult(self.ticket)

    def commit(self):
        pass

    def refresh(self, ticket):
        pass


class ResolveServiceTests(unittest.TestCase):
    def test_resolve_returns_overtime_and_updates_quantity(self):
        db = DummyDB(DummyTicket())

        result = resolve_service.resolve(db, "ticket-1", 70)

        self.assertEqual(result["remaining_quantity"], 1)
        self.assertEqual(result["overtime_returned"], 30)

    def test_update_ticket_complexity_updates_ticket(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        session = Session()

        try:
            ticket = Ticket(title="Test", complexity=10, quantity=1)
            session.add(ticket)
            session.commit()
            session.refresh(ticket)

            ticket_service.update_ticket_complexity(session, ticket.id, 25)
            session.refresh(ticket)

            self.assertEqual(ticket.complexity, 25)
            self.assertIsNotNone(ticket.updated_at)
        finally:
            session.close()
            Base.metadata.drop_all(bind=engine)

    def test_delete_queue_with_tickets_returns_bad_request(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

        with TestClient(app) as client:
            queue_resp = client.post('/queues', json={'name': 'Billing', 'capacity': 10})
            self.assertEqual(queue_resp.status_code, 201)

            queue_id = queue_resp.json()['id']
            add_resp = client.post(
                f'/queues/{queue_id}/tickets',
                json={'title': 'Login Error', 'complexity': 40, 'quantity': 1},
            )
            self.assertEqual(add_resp.status_code, 201)

            delete_resp = client.delete(f'/queues/{queue_id}')
            self.assertEqual(delete_resp.status_code, 400)
            self.assertIn('Queue has tickets', delete_resp.text)

        Base.metadata.drop_all(bind=engine)

    def test_create_ticket_with_invalid_quantity_returns_bad_request(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

        with TestClient(app) as client:
            queue_resp = client.post('/queues', json={'name': 'Billing', 'capacity': 10})
            self.assertEqual(queue_resp.status_code, 201)

            queue_id = queue_resp.json()['id']
            add_resp = client.post(
                f'/queues/{queue_id}/tickets',
                json={'title': 'Login Error', 'complexity': 40, 'quantity': 0},
            )
            self.assertEqual(add_resp.status_code, 422)

        Base.metadata.drop_all(bind=engine)

    def tearDown(self):
        Base.metadata.drop_all(bind=engine)


if __name__ == "__main__":
    unittest.main()
