from collections.abc import Callable, Generator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app import crud
from app.core.config import settings
from app.models import ItemCreate, Role, User, UserCreate
from tests.utils.user import user_authentication_headers
from tests.utils.utils import random_email

API = settings.API_V1_STR
ActorFactory = Callable[[Role], tuple[User, dict[str, str]]]


@pytest.fixture
def actor(client: TestClient, db: Session) -> Generator[ActorFactory]:
    ids = []

    def create(role: Role) -> tuple[User, dict[str, str]]:
        user = crud.create_user(
            session=db,
            user_create=UserCreate(
                email=random_email(), password="test-password", role=role
            ),
        )
        ids.append(user.id)
        headers = user_authentication_headers(
            client=client, email=user.email, password="test-password"
        )
        return user, headers

    yield create
    db.expire_all()
    for user_id in ids:
        if user := db.get(User, user_id):
            db.delete(user)
    db.commit()


def test_admin_can_create_user_and_change_role(
    client: TestClient, actor: ActorFactory
) -> None:
    _, headers = actor(Role.ADMIN)
    manager, manager_headers = actor(Role.MANAGER)
    assert client.get(f"{API}/metrics/", headers=manager_headers).status_code == 200

    response = client.patch(
        f"{API}/users/{manager.id}", headers=headers, json={"role": "member"}
    )
    assert response.status_code == 200
    assert response.json()["role"] == "member"
    assert client.get(f"{API}/metrics/", headers=manager_headers).status_code == 403

    response = client.post(
        f"{API}/users/",
        headers=headers,
        json={"email": random_email(), "password": "test-password", "role": "manager"},
    )
    assert response.status_code == 200
    assert response.json()["role"] == "manager"
    assert (
        client.delete(
            f"{API}/users/{response.json()['id']}", headers=headers
        ).status_code
        == 200
    )


def test_manager_has_read_only_access_and_cannot_access_others_items(
    client: TestClient, db: Session, actor: ActorFactory
) -> None:
    _, headers = actor(Role.MANAGER)
    owner, _ = actor(Role.MEMBER)
    assert client.get(f"{API}/users/", headers=headers).status_code == 200
    assert client.get(f"{API}/metrics/", headers=headers).status_code == 200
    assert (
        client.post(
            f"{API}/users/",
            headers=headers,
            json={"email": random_email(), "password": "test-password"},
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"{API}/users/{owner.id}", headers=headers, json={"role": "admin"}
        ).status_code
        == 403
    )

    item = crud.create_item(
        session=db, item_in=ItemCreate(title="Private"), owner_id=owner.id
    )
    response = client.get(f"{API}/items/", headers=headers)
    assert response.status_code == 200
    assert response.json()["data"] == []
    assert client.get(f"{API}/items/{item.id}", headers=headers).status_code == 403


def test_member_can_update_own_profile_but_cannot_elevate_role(
    client: TestClient, actor: ActorFactory
) -> None:
    _, headers = actor(Role.MEMBER)
    assert client.get(f"{API}/users/", headers=headers).status_code == 403
    assert client.get(f"{API}/metrics/", headers=headers).status_code == 403
    response = client.patch(
        f"{API}/users/me", headers=headers, json={"full_name": "Updated name"}
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == "Updated name"
    assert (
        client.patch(
            f"{API}/users/me", headers=headers, json={"role": "admin"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"{API}/users/signup",
            json={
                "email": random_email(),
                "password": "test-password",
                "role": "admin",
            },
        ).status_code
        == 422
    )
    assert client.get(f"{API}/users/me", headers=headers).json()["role"] == "member"
