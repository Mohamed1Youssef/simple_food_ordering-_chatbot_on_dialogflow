import re

def get_str_from_food_dict(food_dict: dict[str, int]) -> str:
    return ", ".join(
        f"{int(quantity)} {food_item}"
        for food_item, quantity in food_dict.items()
    )


def extract_session_id(session_str: str) -> str:
    match = re.search(r"/sessions/([^/]+)", session_str)
    return match.group(1) if match else ""