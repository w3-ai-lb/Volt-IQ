"""
Shared schema base.

The React frontend consumes camelCase field names (`dueDate`,
`estimatedSavings`, `totalCustomers` …) while Python uses snake_case.
`CamelModel` bridges the two with an automatic alias generator, so a response
arrives with the field names the React pages already read, and **no renaming
is required on either side**.

The names were originally matched against the frontend's `mockData.ts`, which
is how the two halves met in the middle before there was a database. That file
has since been deleted: every page now reads from this API, and `tests/
test_api.py` is what holds the shape steady, by asserting the camelCase keys
of every response against what the pages expect.
"""

from pydantic import BaseModel, ConfigDict


def to_camel(snake: str) -> str:
    head, *tail = snake.split("_")
    return head + "".join(word.capitalize() for word in tail)


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,   # accept snake_case when constructing in Python
        from_attributes=True,    # build straight from ORM objects
    )
