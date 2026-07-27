from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

import db_helper
import generic_helper


app = FastAPI(
    title="Food Ordering Chatbot API",
    version="1.0.0",
)


# Temporary order storage:
#
# {
#     "dialogflow-session-id": {
#         "Pizza": 2,
#         "Burger": 1
#     }
# }
#
# This is acceptable for local learning and testing.
# It should not be used as permanent production storage.
inprogress_orders: dict[str, dict[str, int]] = {}


def create_response(message: str) -> JSONResponse:
    """
    Create a Dialogflow-compatible webhook response.
    """
    return JSONResponse(
        content={
            "fulfillmentText": message
        }
    )


@app.get("/")
def health_check() -> dict[str, str]:
    """
    Simple endpoint for checking that the API is running.

    Dialogflow will send webhook requests using POST.
    """
    return {
        "status": "running",
        "message": "Food-ordering chatbot API is available.",
    }


@app.post("/")
async def handle_request(request: Request) -> JSONResponse:
    """
    Receive and process Dialogflow webhook requests.
    """

    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        return create_response(
            "Sorry, I received an invalid request."
        )

    query_result = payload.get("queryResult", {})

    intent_data = query_result.get("intent", {})
    intent = intent_data.get("displayName", "")

    parameters = query_result.get("parameters", {})

    # Dialogflow provides a session path such as:
    #
    # projects/project-id/agent/sessions/session-id
    #
    # It is safer to use this field directly instead of depending
    # on outputContexts[0].
    session_path = payload.get("session", "")
    session_id = generic_helper.extract_session_id(session_path)

    if not session_id:
        return create_response(
            "Sorry, I could not identify your conversation session. "
            "Please start again."
        )

    intent_handler_dict = {
        "add.order - context:ongoing-order": add_to_order,
        "remove.order - context:ongoing-order": remove_from_order,
        "complete.order - context:ongoing-order": complete_order,
        "track.order - context:ongoing-order": track_order,
    }

    handler = intent_handler_dict.get(intent)

    if handler is None:
        return create_response(
            "Sorry, I cannot process that request. "
            'You can say "New Order" or "Track Order".'
        )

    try:
        # Handlers perform blocking DB I/O, so run them off the event
        # loop thread — otherwise one slow request would stall every
        # other concurrent webhook call.
        return await run_in_threadpool(handler, parameters, session_id)

    except Exception as error:
        print(
            f"Unexpected error while handling intent "
            f"'{intent}': {error}"
        )

        return create_response(
            "Sorry, something went wrong while processing your request. "
            "Please try again."
        )


def save_to_db(order: dict[str, int]) -> int:
    """
    Save a completed in-progress order to PostgreSQL.

    Returns:
        The new order ID when successful.
        -1 when saving fails.
    """

    if not order:
        return -1

    return db_helper.save_order(order)


def complete_order(
    parameters: dict[str, Any],
    session_id: str
) -> JSONResponse:
    """
    Complete the user's current order and save it to PostgreSQL.
    """

    del parameters  # This intent does not currently use parameters.

    if session_id not in inprogress_orders:
        return create_response(
            "I'm having trouble finding your current order. "
            "Please start a new order."
        )

    order = inprogress_orders[session_id]

    if not order:
        return create_response(
            "Your order is empty. Please add at least one item "
            "before completing it."
        )

    order_id = save_to_db(order)

    if order_id == -1:
        # Do not delete the temporary order when database saving fails.
        # This allows the user to retry.
        return create_response(
            "Sorry, I couldn't process your order because of a "
            "backend error. Please try completing the order again."
        )

    # Delete the temporary order now that it is safely saved. This must
    # happen before any further DB calls that could fail — otherwise a
    # retry would re-save the same items under a brand-new order ID.
    del inprogress_orders[session_id]

    order_total = db_helper.get_total_order_price(order_id)

    if order_total is None:
        return create_response(
            f"Your order was placed with order ID {order_id}, "
            "but I could not retrieve its total price."
        )

    return create_response(
        f"Awesome! Your order has been placed successfully. "
        f"Your order ID is {order_id}. "
        f"Your total is ${order_total:.2f}. "
        f"You can pay when your order is delivered."
    )


def add_to_order(
    parameters: dict[str, Any],
    session_id: str
) -> JSONResponse:
    """
    Add food items and quantities to the current temporary order.
    """

    food_items = parameters.get("food-item", [])
    quantities = parameters.get("number", [])

    # Dialogflow usually returns lists for list entities,
    # but this also handles a single returned value.
    if isinstance(food_items, str):
        food_items = [food_items]

    if isinstance(quantities, (int, float)):
        quantities = [quantities]

    if not food_items or not quantities:
        return create_response(
            "Please mention both the food items and their quantities. "
            'For example, say "Two pizzas and one burger."'
        )

    if len(food_items) != len(quantities):
        return create_response(
            "Sorry, I couldn't match every food item with a quantity. "
            "Please specify one quantity for each item."
        )

    current_order = inprogress_orders.setdefault(
        session_id,
        {},
    )

    invalid_items: list[str] = []

    for food_item, quantity in zip(food_items, quantities):
        food_item = str(food_item).strip()

        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            invalid_items.append(food_item)
            continue

        if not food_item or quantity <= 0:
            invalid_items.append(food_item)
            continue

        # Increase the existing quantity instead of replacing it.
        #
        # Example:
        # Existing order: 2 pizzas
        # User says: Add 1 pizza
        # New order: 3 pizzas
        current_order[food_item] = (
            current_order.get(food_item, 0) + quantity
        )

    if not current_order:
        return create_response(
            "I couldn't add those items. Please specify valid food "
            "items and quantities."
        )

    order_str = generic_helper.get_str_from_food_dict(
        current_order
    )

    if invalid_items:
        invalid_str = ", ".join(
            item for item in invalid_items if item
        )

        return create_response(
            f"So far, you have: {order_str}. "
            f"I couldn't add these items correctly: {invalid_str}. "
            "Would you like anything else?"
        )

    return create_response(
        f"So far, you have: {order_str}. "
        "Would you like anything else?"
    )


def remove_from_order(
    parameters: dict[str, Any],
    session_id: str
) -> JSONResponse:
    """
    Remove one or more food items from the current order.
    """

    if session_id not in inprogress_orders:
        return create_response(
            "I'm having trouble finding your current order. "
            "Please start a new order."
        )

    food_items = parameters.get("food-item", [])

    if isinstance(food_items, str):
        food_items = [food_items]

    if not food_items:
        return create_response(
            "Please tell me which item you want to remove."
        )

    current_order = inprogress_orders[session_id]

    removed_items: list[str] = []
    missing_items: list[str] = []

    for item in food_items:
        item = str(item).strip()

        if item in current_order:
            del current_order[item]
            removed_items.append(item)
        else:
            missing_items.append(item)

    response_parts: list[str] = []

    if removed_items:
        response_parts.append(
            f"Removed {', '.join(removed_items)} from your order."
        )

    if missing_items:
        response_parts.append(
            f"Your current order does not contain "
            f"{', '.join(missing_items)}."
        )

    if not current_order:
        response_parts.append(
            "Your order is now empty."
        )
    else:
        order_str = generic_helper.get_str_from_food_dict(
            current_order
        )

        response_parts.append(
            f"Your current order contains: {order_str}."
        )

    fulfillment_text = " ".join(response_parts)

    return create_response(fulfillment_text)


def track_order(
    parameters: dict[str, Any],
    session_id: str
) -> JSONResponse:
    """
    Retrieve an order's current tracking status.
    """

    del session_id  # Tracking currently does not require session state.

    # Dialogflow sends the order ID under the "number" parameter
    # (a @sys.number entity), not "order_id".
    raw_order_id = parameters.get("number")

    # Support a list in case Dialogflow returns the parameter
    # as a list rather than a single value.
    if isinstance(raw_order_id, list):
        raw_order_id = raw_order_id[0] if raw_order_id else None

    try:
        order_id = int(raw_order_id)
    except (TypeError, ValueError):
        return create_response(
            "Please provide a valid numeric order ID."
        )

    if order_id <= 0:
        return create_response(
            "Please provide a valid order ID greater than zero."
        )

    order_status = db_helper.get_order_status(order_id)

    if order_status:
        return create_response(
            f"The status of order {order_id} is: {order_status}."
        )

    return create_response(
        f"I couldn't find an order with ID {order_id}."
    )

