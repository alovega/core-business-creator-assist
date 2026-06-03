from pony.orm import commit, db_session

from app.businesses.models import Business
from app.conversations.models import Conversation
from app.customers.models import Customer
from app.testing.helpers import add_business_member, auth_headers, create_business, register_user
from app.users.models import User


def _create_customer_record(app, *, business_id: int, name: str, phone_number: str) -> int:
    with app.app_context():

        @db_session
        def _create():
            business = Business.get(id=business_id)
            customer = Customer(
                business=business,
                name=name,
                phone_number=phone_number,
                normalized_phone_number=phone_number.replace(" ", ""),
                source="manual",
                tags_json=[],
                status="active",
            )
            commit()
            return customer.id

        return _create()


def _create_conversation_record(
    app,
    *,
    business_id: int,
    customer_id: int,
    status: str = "open",
    channel: str = "whatsapp",
    unread_count: int = 0,
    priority: str = "normal",
    tags: list[str] | None = None,
) -> int:
    with app.app_context():

        @db_session
        def _create():
            business = Business.get(id=business_id)
            customer = Customer.get(id=customer_id, business=business)
            conversation = Conversation(
                business=business,
                customer=customer,
                channel=channel,
                status=status,
                unread_count=unread_count,
                priority=priority,
                tags_json=tags or [],
            )
            commit()
            return conversation.id

        return _create()


class TestConversationReadEndpoints:
    def test_list_and_detail_are_business_scoped(self, client, app, owner_client):
        _, owner_token = owner_client
        with app.app_context():

            @db_session
            def _business_id():
                return User.get(email="owner@example.com").current_business_id

            business_id = _business_id()

        customer_id = _create_customer_record(
            app,
            business_id=business_id,
            name="Primary Customer",
            phone_number="+12025550111",
        )
        conversation_id = _create_conversation_record(
            app,
            business_id=business_id,
            customer_id=customer_id,
            unread_count=2,
        )

        listed = client.get("/api/conversations", headers=auth_headers(owner_token))
        assert listed.status_code == 200
        payload = listed.get_json()
        assert payload["total"] == 1
        assert payload["conversations"][0]["id"] == conversation_id

        detail = client.get(
            f"/api/conversations/{conversation_id}",
            headers=auth_headers(owner_token),
        )
        assert detail.status_code == 200
        assert detail.get_json()["conversation"]["customer_id"] == customer_id

    def test_filters_status_unread_priority_tag_search(self, client, app, owner_client):
        _, owner_token = owner_client
        with app.app_context():

            @db_session
            def _business_id():
                return User.get(email="owner@example.com").current_business_id

            business_id = _business_id()

        alpha_customer_id = _create_customer_record(
            app,
            business_id=business_id,
            name="Alice Search",
            phone_number="+14155550001",
        )
        beta_customer_id = _create_customer_record(
            app,
            business_id=business_id,
            name="Bob Search",
            phone_number="+14155550002",
        )
        _create_conversation_record(
            app,
            business_id=business_id,
            customer_id=alpha_customer_id,
            status="pending",
            unread_count=3,
            priority="high",
            tags=["vip"],
        )
        _create_conversation_record(
            app,
            business_id=business_id,
            customer_id=beta_customer_id,
            status="open",
            unread_count=0,
            priority="normal",
            tags=["new"],
        )

        pending = client.get(
            "/api/conversations?status=pending",
            headers=auth_headers(owner_token),
        )
        assert pending.status_code == 200
        assert pending.get_json()["total"] == 1

        unread = client.get("/api/conversations?unread=true", headers=auth_headers(owner_token))
        assert unread.status_code == 200
        assert unread.get_json()["total"] == 1

        tagged = client.get("/api/conversations?tag=vip", headers=auth_headers(owner_token))
        assert tagged.status_code == 200
        assert tagged.get_json()["total"] == 1

        searched = client.get(
            "/api/conversations?search=alice",
            headers=auth_headers(owner_token),
        )
        assert searched.status_code == 200
        assert searched.get_json()["total"] == 1


class TestConversationMutations:
    def test_assign_unassign_mark_read_and_status_actions(self, client, app, owner_client):
        _, owner_token = owner_client
        register_user(client, email="assignee@example.com")

        with app.app_context():

            @db_session
            def _business_id():
                return User.get(email="owner@example.com").current_business_id

            business_id = _business_id()

        add_business_member(app, "assignee@example.com", business_id, role="staff")
        customer_id = _create_customer_record(
            app,
            business_id=business_id,
            name="Mutable Customer",
            phone_number="+33123456789",
        )
        conversation_id = _create_conversation_record(
            app,
            business_id=business_id,
            customer_id=customer_id,
            unread_count=7,
        )

        with app.app_context():

            @db_session
            def _membership_id():
                return User.get(email="assignee@example.com").active_membership_for(
                    business_id
                ).id

            membership_id = _membership_id()

        assigned = client.post(
            f"/api/conversations/{conversation_id}/assign",
            json={"membership_id": membership_id},
            headers=auth_headers(owner_token),
        )
        assert assigned.status_code == 200
        assert assigned.get_json()["conversation"]["assigned_membership_id"] == membership_id

        marked = client.post(
            f"/api/conversations/{conversation_id}/mark-read",
            headers=auth_headers(owner_token),
        )
        assert marked.status_code == 200
        assert marked.get_json()["conversation"]["unread_count"] == 0

        closed = client.post(
            f"/api/conversations/{conversation_id}/close",
            headers=auth_headers(owner_token),
        )
        assert closed.status_code == 200
        assert closed.get_json()["conversation"]["status"] == "closed"

        reopened = client.post(
            f"/api/conversations/{conversation_id}/reopen",
            headers=auth_headers(owner_token),
        )
        assert reopened.status_code == 200
        assert reopened.get_json()["conversation"]["status"] == "open"

        unassigned = client.post(
            f"/api/conversations/{conversation_id}/unassign",
            headers=auth_headers(owner_token),
        )
        assert unassigned.status_code == 200
        assert unassigned.get_json()["conversation"]["assigned_membership_id"] is None

        patched = client.patch(
            f"/api/conversations/{conversation_id}",
            json={"status": "pending", "priority": "urgent", "tags": ["vip", "renewal"]},
            headers=auth_headers(owner_token),
        )
        assert patched.status_code == 200
        assert patched.get_json()["conversation"]["status"] == "pending"
        assert patched.get_json()["conversation"]["priority"] == "urgent"


class TestConversationRbacAndIsolation:
    def test_support_can_view_but_cannot_assign(self, client, app, owner_client):
        _, owner_token = owner_client
        register_user(client, email="support-conv@example.com")
        with app.app_context():

            @db_session
            def _business_id():
                return User.get(email="owner@example.com").current_business_id

            business_id = _business_id()

        add_business_member(app, "support-conv@example.com", business_id, role="support")
        support_token = client.post(
            "/api/auth/login",
            json={"email": "support-conv@example.com", "password": "securepass123"},
        ).get_json()["access_token"]

        customer_id = _create_customer_record(
            app,
            business_id=business_id,
            name="Support Customer",
            phone_number="+49891234567",
        )
        conversation_id = _create_conversation_record(
            app,
            business_id=business_id,
            customer_id=customer_id,
        )

        can_view = client.get("/api/conversations", headers=auth_headers(support_token))
        assert can_view.status_code == 200

        cannot_assign = client.post(
            f"/api/conversations/{conversation_id}/assign",
            json={"membership_id": 99999},
            headers=auth_headers(support_token),
        )
        assert cannot_assign.status_code == 403

        owner_view = client.get(
            f"/api/conversations/{conversation_id}",
            headers=auth_headers(owner_token),
        )
        assert owner_view.status_code == 200

    def test_user_cannot_access_conversation_from_another_business(
        self, client, app, owner_client
    ):
        _, owner_token = owner_client
        with app.app_context():

            @db_session
            def _business_id():
                return User.get(email="owner@example.com").current_business_id

            first_business_id = _business_id()

        customer_id = _create_customer_record(
            app,
            business_id=first_business_id,
            name="Tenant One Customer",
            phone_number="+390212345678",
        )
        conversation_id = _create_conversation_record(
            app,
            business_id=first_business_id,
            customer_id=customer_id,
        )

        outsider = register_user(client, email="outsider-conv@example.com")
        outsider_token = outsider.get_json()["access_token"]
        create_business(client, outsider_token)

        forbidden = client.get(
            f"/api/conversations/{conversation_id}",
            headers=auth_headers(outsider_token),
        )
        assert forbidden.status_code == 404

        forbidden_list = client.get(
            "/api/conversations",
            headers=auth_headers(outsider_token),
        )
        assert forbidden_list.status_code == 200
        assert forbidden_list.get_json()["total"] == 0

        owner_still_access = client.get(
            f"/api/conversations/{conversation_id}",
            headers=auth_headers(owner_token),
        )
        assert owner_still_access.status_code == 200
