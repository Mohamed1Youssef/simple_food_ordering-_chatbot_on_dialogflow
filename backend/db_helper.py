"""
PostgreSQL database helper for the food-ordering chatbot.

Original project:
Dhaval Patel — Codebasics YouTube Channel

Converted from MySQL to PostgreSQL.
"""

from decimal import Decimal
import os

from dotenv import load_dotenv
import  psycopg
from psycopg import Connection
from psycopg.errors import DatabaseError

# Load DB_* variables from a local .env file, if present, before
# DB_CONFIG is built. Real secrets belong in .env, not source control.
load_dotenv()


# ------------------------------------------------------------
# Database configuration
# ------------------------------------------------------------

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "food_ordering_chatbot"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "your_postgresql_password"),
}


def get_connection() -> Connection:
    """
    Create and return a new PostgreSQL database connection.

    A new connection is created when a database operation is performed
    instead of keeping one global connection open permanently.
    """
    return psycopg.connect(**DB_CONFIG)


# ------------------------------------------------------------
# Save a complete order (atomic)
# ------------------------------------------------------------

def save_order(order: dict[str, int]) -> int:
    """
    Save a completed order to PostgreSQL as a single transaction.

    Generates a new order ID, inserts every food item, and creates
    the tracking record, all on one connection. If any step fails,
    the whole transaction rolls back, so a failure partway through
    never leaves a partial order behind.

    Returns:
        The new order ID when successful.
        -1 when saving fails.
    """

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT get_next_order_id();")
                order_id = cursor.fetchone()[0]

                for food_item, quantity in order.items():
                    cursor.execute(
                        "CALL insert_order_item(%s, %s, %s)",
                        (food_item, quantity, order_id),
                    )

                cursor.execute(
                    """
                    INSERT INTO order_tracking (order_id, status)
                    VALUES (%s, %s)
                    ON CONFLICT (order_id)
                    DO UPDATE SET status = EXCLUDED.status;
                    """,
                    (order_id, "confirmed"),
                )

        print(f"Order {order_id} was saved successfully.")
        return order_id

    except DatabaseError as error:
        print(f"Database error while saving order: {error}")
        return -1

    except Exception as error:
        print(f"Unexpected error while saving order: {error}")
        return -1


# ------------------------------------------------------------
# Insert or update an order item
# ------------------------------------------------------------

def insert_order_item(
    food_item: str,
    quantity: int,
    order_id: int
) -> int:
    """
    Call the PostgreSQL insert_order_item procedure.

    The database procedure adds a new item to the order. If the same item
    already exists in that order, the procedure increases its quantity.

    Returns:
        1 when the operation succeeds.
        -1 when the operation fails.
    """

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "CALL insert_order_item(%s, %s, %s)",
                    (food_item, quantity, order_id),
                )

        print(
            f"Successfully added {quantity} × {food_item} "
            f"to order {order_id}."
        )

        return 1

    except DatabaseError as error:
        print(f"Database error while inserting order item: {error}")
        return -1

    except Exception as error:
        print(f"Unexpected error while inserting order item: {error}")
        return -1


# ------------------------------------------------------------
# Insert or update order tracking
# ------------------------------------------------------------

def insert_order_tracking(
    order_id: int,
    status: str = "confirmed"
) -> int:
    """
    Insert an order into the order_tracking table.

    If the order already exists, its status is updated.

    Returns:
        1 when successful.
        -1 when unsuccessful.
    """

    query = """
        INSERT INTO order_tracking (order_id, status)
        VALUES (%s, %s)
        ON CONFLICT (order_id)
        DO UPDATE SET status = EXCLUDED.status;
    """

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, (order_id, status))

        print(
            f"Tracking information for order {order_id} "
            f"was saved with status: {status}."
        )

        return 1

    except DatabaseError as error:
        print(f"Database error while saving order tracking: {error}")
        return -1

    except Exception as error:
        print(f"Unexpected error while saving order tracking: {error}")
        return -1


# ------------------------------------------------------------
# Finalize an order
# ------------------------------------------------------------

def finalize_order(order_id: int) -> int:
    """
    Call the PostgreSQL finalize_order procedure.

    This marks an existing order as confirmed in the tracking table.

    Returns:
        1 when successful.
        -1 when unsuccessful.
    """

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "CALL finalize_order(%s)",
                    (order_id,),
                )

        print(f"Order {order_id} was finalized successfully.")
        return 1

    except DatabaseError as error:
        print(f"Database error while finalizing order: {error}")
        return -1

    except Exception as error:
        print(f"Unexpected error while finalizing order: {error}")
        return -1


# ------------------------------------------------------------
# Get the total price of an order
# ------------------------------------------------------------

def get_total_order_price(order_id: int) -> Decimal | None:
    """
    Return the total price of an order.

    The PostgreSQL function returns -1 when the order does not exist.

    Returns:
        Decimal containing the order total when found.
        None when the order does not exist or an error occurs.
    """

    query = """
        SELECT get_total_order_price(%s);
    """

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, (order_id,))
                result = cursor.fetchone()

        if result is None:
            return None

        total_price = result[0]

        if total_price is None or total_price == Decimal("-1.00"):
            return None

        return total_price

    except DatabaseError as error:
        print(f"Database error while getting order total: {error}")
        return None

    except Exception as error:
        print(f"Unexpected error while getting order total: {error}")
        return None


# ------------------------------------------------------------
# Get the next available order ID
# ------------------------------------------------------------

def get_next_order_id() -> int | None:
    """
    Get the next available order ID using the PostgreSQL function
    created in the database script.

    Returns:
        The next available integer order ID.
        None when an error occurs.
    """

    query = """
        SELECT get_next_order_id();
    """

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query)
                result = cursor.fetchone()

        if result is None:
            return None

        return result[0]

    except DatabaseError as error:
        print(f"Database error while generating order ID: {error}")
        return None

    except Exception as error:
        print(f"Unexpected error while generating order ID: {error}")
        return None


# ------------------------------------------------------------
# Get order status
# ------------------------------------------------------------

def get_order_status(order_id: int) -> str | None:
    """
    Fetch the current status of an order.

    Returns:
        The order status when found.
        None when the order does not exist or an error occurs.
    """

    query = """
        SELECT status
        FROM order_tracking
        WHERE order_id = %s;
    """

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, (order_id,))
                result = cursor.fetchone()

        if result is None:
            return None

        return result[0]

    except DatabaseError as error:
        print(f"Database error while fetching order status: {error}")
        return None

    except Exception as error:
        print(f"Unexpected error while fetching order status: {error}")
        return None


# ------------------------------------------------------------
# Get the complete details of an order
# ------------------------------------------------------------

def get_order_details(order_id: int) -> list[dict]:
    """
    Return all food items belonging to an order.

    Example returned value:

    [
        {
            "item": "Pizza",
            "quantity": 2,
            "unit_price": Decimal("8.00"),
            "total_price": Decimal("16.00")
        }
    ]
    """

    query = """
        SELECT
            food_items.name,
            orders.quantity,
            food_items.price,
            orders.total_price
        FROM orders
        JOIN food_items
            ON food_items.item_id = orders.item_id
        WHERE orders.order_id = %s
        ORDER BY food_items.name;
    """

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, (order_id,))
                rows = cursor.fetchall()

        return [
            {
                "item": row[0],
                "quantity": row[1],
                "unit_price": row[2],
                "total_price": row[3],
            }
            for row in rows
        ]

    except DatabaseError as error:
        print(f"Database error while getting order details: {error}")
        return []

    except Exception as error:
        print(f"Unexpected error while getting order details: {error}")
        return []


# ------------------------------------------------------------
# Remove an item from an order
# ------------------------------------------------------------

def remove_order_item(
    food_item: str,
    order_id: int
) -> int:
    """
    Remove a food item completely from an existing order.

    Returns:
        1 when the item was removed.
        0 when the item was not present in the order.
        -1 when an error occurs.
    """

    query = """
        DELETE FROM orders
        WHERE order_id = %s
          AND item_id = (
              SELECT item_id
              FROM food_items
              WHERE LOWER(name) = LOWER(TRIM(%s))
          );
    """

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, (order_id, food_item))
                deleted_rows = cursor.rowcount

        if deleted_rows == 0:
            print(
                f"{food_item} was not found in order {order_id}."
            )
            return 0

        print(
            f"{food_item} was removed from order {order_id}."
        )
        return 1

    except DatabaseError as error:
        print(f"Database error while removing order item: {error}")
        return -1

    except Exception as error:
        print(f"Unexpected error while removing order item: {error}")
        return -1


# ------------------------------------------------------------
# Check database connection
# ------------------------------------------------------------

def test_connection() -> bool:
    """
    Test whether Python can connect to PostgreSQL.
    """

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT version();")
                version = cursor.fetchone()

        if version:
            print("PostgreSQL connection successful.")
            print(version[0])

        return True

    except Exception as error:
        print(f"PostgreSQL connection failed: {error}")
        return False


# ------------------------------------------------------------
# Local testing
# ------------------------------------------------------------

if __name__ == "__main__":
    test_connection()

    next_order_id = get_next_order_id()
    print(f"Next order ID: {next_order_id}")

    if next_order_id is not None:
        insert_order_item("Pizza", 2, next_order_id)
        insert_order_item("Burger", 1, next_order_id)
        insert_order_item("French Fries", 2, next_order_id)

        print("Order details:")
        print(get_order_details(next_order_id))

        total = get_total_order_price(next_order_id)
        print(f"Total order price: ${total}")

        finalize_order(next_order_id)

        status = get_order_status(next_order_id)
        print(f"Order status: {status}")