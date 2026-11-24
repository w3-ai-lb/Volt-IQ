"""
Staff of the electricity provider: office staff and field employees.

WHERE THIS CAME FROM
--------------------
The CRM web app and the Flutter field app used to keep employees in their own
Supabase project (tables `employees` and `employee_subscriber_assignments`).
In the unified VoltIQ system they live here, in the same database as the
subscribers they serve, so one backend answers every app.

HOW AN EMPLOYEE SIGNS IN
------------------------
Customers sign in with their own customer record. Since Stage 2 an
employee who may sign in has a row in `users` (app/models/user.py), linked
through `account_id`, with the role that matches their job:

    employee.role      ->  users.role
    admin              ->  admin
    office_staff       ->  staff
    field_employee     ->  field

Staff accounts are not in `customers` at all, so they can never appear in
customer counts, segments or forecasts.
"""

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# Job role (CRM vocabulary) -> sign-in role (customers.role).
ACCOUNT_ROLE_FOR = {
    "admin": "admin",
    "office_staff": "staff",
    "field_employee": "field",
}

EMPLOYEE_ROLES = frozenset(ACCOUNT_ROLE_FOR)

# Every sign-in role allowed to open the CRM.
STAFF_ACCOUNT_ROLES = frozenset({"admin", "staff", "field"})


class Employee(Base):
    __tablename__ = "employees"

    employee_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(40))

    # 'admin' | 'office_staff' | 'field_employee'
    role: Mapped[str] = mapped_column(String(20), default="field_employee", nullable=False)
    department: Mapped[str | None] = mapped_column(String(60))
    zone_name: Mapped[str | None] = mapped_column(String(80))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # The sign-in account, when this employee may sign in.
    account_id: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("users.user_id", ondelete="SET NULL"), unique=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    assignments = relationship(
        "EmployeeAssignment", back_populates="employee", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Employee {self.employee_id} {self.full_name} {self.role}>"


class EmployeeAssignment(Base):
    """
    Which employee is responsible for which subscriber (meter reading rounds,
    collection). One responsible employee per subscriber, hence the unique key.
    """

    __tablename__ = "employee_assignments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    employee_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("employees.employee_id", ondelete="CASCADE"), nullable=False, index=True
    )
    subscriber_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("subscribers.subscriber_id", ondelete="CASCADE"), nullable=False
    )

    employee = relationship("Employee", back_populates="assignments")

    __table_args__ = (UniqueConstraint("subscriber_id", name="uq_assignment_subscriber"),)
