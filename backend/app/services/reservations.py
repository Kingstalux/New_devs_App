from decimal import Decimal
from typing import Dict, Any, List, Optional

async def calculate_total_revenue(
    property_id: str,
    tenant_id: str,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """
    Aggregates revenue from database, optionally limited to one calendar month.

    Month boundaries are taken in the property's own timezone, so a stay that
    checks in at 00:30 on 1 March in Paris counts toward March even though it
    is still 29 February in UTC.

    Returns None when the property does not exist for this tenant.
    Raises if the database is unavailable, so callers never receive stand-in figures.
    """
    from sqlalchemy import text
    from app.core.database_pool import db_pool

    await db_pool.initialize()
    if not db_pool.session_factory:
        raise RuntimeError("Database pool not available")

    # Start from the tenant's own property so a property ID owned by another
    # tenant yields no row, while a property with no bookings still returns zero.
    query = text("""
        SELECT
            p.id AS property_id,
            COALESCE(SUM(r.total_amount), 0) AS total_revenue,
            COUNT(r.id) AS reservation_count
        FROM properties p
        LEFT JOIN reservations r
            ON r.property_id = p.id
            AND r.tenant_id = p.tenant_id
            AND (
                CAST(:month AS INTEGER) IS NULL
                OR (
                    r.check_in_date >= (make_timestamp(:year, :month, 1, 0, 0, 0) AT TIME ZONE p.timezone)
                    AND r.check_in_date < ((make_timestamp(:year, :month, 1, 0, 0, 0) + INTERVAL '1 month') AT TIME ZONE p.timezone)
                )
            )
        WHERE p.id = :property_id AND p.tenant_id = :tenant_id
        GROUP BY p.id
    """)

    async with db_pool.get_session() as session:
        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "month": month,
            "year": year
        })
        row = result.fetchone()

    if row is None:
        return None

    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "month": month,
        "year": year,
        "total": str(Decimal(str(row.total_revenue))),
        "currency": "USD",
        "count": row.reservation_count
    }
