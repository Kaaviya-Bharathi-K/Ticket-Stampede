from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.database import SessionLocal, init_db
from app.models import Sale, Ticket


class ResetRequest(BaseModel):
    ticket_count: int = Field(gt=0, description="Number of tickets available in the new sale")


class BuyRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=255)
    request_id: str = Field(min_length=1, max_length=255)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Ticket Stampede API", lifespan=lifespan)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/status", tags=["sale"])
def get_status() -> dict[str, object]:
    with SessionLocal() as session:
        sale = session.scalar(select(Sale).order_by(Sale.id.desc()).limit(1))
        tickets = session.scalars(
            select(Ticket).order_by(Ticket.ticket_number)
        ).all()

        total_tickets = sale.total_tickets if sale is not None else 0
        sold_count = sale.sold_count if sale is not None else 0
        return {
            "total_tickets": total_tickets,
            "sold_count": sold_count,
            "remaining_tickets": total_tickets - sold_count,
            "issued_tickets": [
                {
                    "ticket_number": ticket.ticket_number,
                    "user_id": ticket.user_id,
                    "request_id": ticket.request_id,
                }
                for ticket in tickets
            ],
        }


@app.post("/reset", tags=["sale"])
def reset_sale(request: ResetRequest) -> dict[str, int | str]:
    with SessionLocal.begin() as session:
        session.execute(delete(Ticket))
        session.execute(delete(Sale))
        sale = Sale(total_tickets=request.ticket_count, sold_count=0)
        session.add(sale)
        session.flush()
        response = {
            "message": "New sale started",
            "sale_id": sale.id,
            "total_tickets": sale.total_tickets,
            "sold_count": sale.sold_count,
        }

    return response


@app.post("/buy", tags=["tickets"])
def buy_ticket(request: BuyRequest) -> dict[str, int]:
    try:
        with SessionLocal.begin() as session:
            # All buyers for the active sale serialize on this database row.
            # MySQL holds this lock through commit or rollback.
            sale = session.scalar(
                select(Sale)
                .order_by(Sale.id.desc())
                .limit(1)
                .with_for_update()
            )
            if sale is None:
                raise HTTPException(status_code=404, detail="No active sale")

            # Check idempotency while holding the sale lock so simultaneous
            # requests with the same request_id cannot both issue a ticket.
            existing_ticket = session.scalar(
                select(Ticket).where(Ticket.request_id == request.request_id)
            )
            if existing_ticket is not None:
                return {"ticket_number": existing_ticket.ticket_number}

            if sale.sold_count >= sale.total_tickets:
                raise HTTPException(status_code=409, detail="Sale is sold out")

            last_ticket_number = session.scalar(select(func.max(Ticket.ticket_number)))
            ticket_number = (last_ticket_number or 0) + 1
            session.add(Ticket(
                ticket_number=ticket_number,
                user_id=request.user_id,
                request_id=request.request_id,
            ))
            sale.sold_count += 1
            session.flush()

        return {"ticket_number": ticket_number}
    except IntegrityError as exc:
        # The unique request_id constraint is a final guard if a competing
        # writer reaches the insert by a path that did not share our lock.
        try:
            with SessionLocal() as session:
                existing_ticket = session.scalar(
                    select(Ticket).where(Ticket.request_id == request.request_id)
                )
                if existing_ticket is not None:
                    return {"ticket_number": existing_ticket.ticket_number}
        except SQLAlchemyError as lookup_error:
            raise HTTPException(
                status_code=503, detail="Purchase transaction failed; retry"
            ) from lookup_error
        raise HTTPException(status_code=503, detail="Purchase transaction conflicted; retry") from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Purchase transaction failed; retry") from exc
