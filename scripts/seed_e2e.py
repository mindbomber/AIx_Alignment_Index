from __future__ import annotations

from sqlalchemy import func, select

from aix.io import load_document
from aix_platform.database import SessionLocal
from aix_platform.orm import (
    Assessment,
    Membership,
    Organization,
    SystemRecord,
    User,
)
from aix_platform.security import hash_password


def main() -> None:
    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(Organization)):
            raise RuntimeError("E2E seed database must be empty")
        organization = Organization(name="AIx Research", slug="aix-research")
        user = User(
            email="owner@example.com",
            display_name="AIx Owner",
            password_hash=hash_password("browser-test-password"),
        )
        db.add_all([organization, user])
        db.flush()
        db.add(
            Membership(
                organization_id=organization.id,
                user_id=user.id,
                role="owner",
            )
        )
        system = SystemRecord(
            organization_id=organization.id,
            name="Customer Support Model",
            kind="ai_system",
            description="Production support assistant",
            metadata_json={"owner": "support"},
            created_by=user.id,
        )
        db.add(system)
        db.flush()
        assessment = load_document("examples/ai_output_assessment.yaml")
        assessment["system"]["name"] = system.name
        db.add(
            Assessment(
                organization_id=organization.id,
                system_id=system.id,
                version=1,
                status="draft",
                input_json=assessment,
                created_by=user.id,
            )
        )
        db.commit()


if __name__ == "__main__":
    main()
