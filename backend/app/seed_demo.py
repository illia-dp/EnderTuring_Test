"""Create local demo users without changing existing accounts."""

import os

from sqlmodel import Session

from app import crud
from app.core.db import engine, init_db
from app.models import Role, UserCreate


def main() -> None:
    users = [
        UserCreate(
            email=os.environ[f"DEMO_{role.name}_EMAIL"],
            password=os.environ[f"DEMO_{role.name}_PASSWORD"],
            full_name=f"Demo {role.value}",
            role=role,
        )
        for role in (Role.MANAGER, Role.MEMBER)
    ]
    with Session(engine) as session:
        init_db(session)
        for user in users:
            if not crud.get_user_by_email(session=session, email=user.email):
                crud.create_user(session=session, user_create=user)


if __name__ == "__main__":
    main()
