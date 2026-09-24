from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Sale(Base):
    __tablename__ = "sale"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    total_tickets: Mapped[int] = mapped_column(Integer, nullable=False)
    sold_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (UniqueConstraint("request_id", name="uq_tickets_request_id"),)

    ticket_number: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    request_id: Mapped[str] = mapped_column(String(255), nullable=False)
