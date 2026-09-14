"""The tool definitions the model is sent (T-CHAT-0; CHAT-5, design.md §4).

No database: these are declarations, and what is worth asserting about them is
that they say what the code behind them actually enforces.

The one that matters most is
``test_the_create_tool_schema_tracks_the_endpoints_schema``. A hand-written
``input_schema`` and a Pydantic model are two descriptions of the same
argument list, and when they disagree the model omits a field it was never
told about, every create comes back ``is_error``, and no HTTP test notices
anything at all.
"""

from __future__ import annotations

from app.api.schemas.service_request import ServiceRequestCreate
from app.chat.tools import (
    CREATE_SERVICE_REQUEST,
    GET_REQUEST_STATUS,
    TOOL_DEFINITIONS,
    available_tools,
)

# design.md §4's table, as the names it fixes. Two, since T-CHAT-0b: CHAT-5
# says "no FAQ-search tool", and this is the assertion that keeps one from
# reappearing — an extra definition here is a tool offered to the model.
EXPECTED_TOOLS = {CREATE_SERVICE_REQUEST, GET_REQUEST_STATUS}


def test_design_md_s_two_tools_are_defined_and_no_others() -> None:
    assert set(TOOL_DEFINITIONS) == EXPECTED_TOOLS


def test_every_definition_is_shaped_the_way_the_messages_api_expects() -> None:
    for name, definition in TOOL_DEFINITIONS.items():
        assert definition["name"] == name, "the key and the name must agree"
        assert definition["description"].strip()
        schema = definition["input_schema"]
        assert schema["type"] == "object"
        assert schema["properties"]
        assert schema["required"]


def test_every_argument_carries_a_description() -> None:
    """The model reads these; a bare type is a parameter it will guess at.

    design.md §2 notes that a Haiku-class model may infer a missing parameter
    rather than ask, which makes per-argument wording part of the tool's
    correctness rather than polish.
    """
    for definition in TOOL_DEFINITIONS.values():
        for field, schema in definition["input_schema"]["properties"].items():
            assert schema.get("description", "").strip(), (
                f"{definition['name']}.{field} has no description"
            )


def test_the_create_tool_schema_tracks_the_endpoints_schema() -> None:
    """CHAT-5, as the property that keeps it true: one schema, not two.

    Derived from ``ServiceRequestCreate`` rather than transcribed from it, so a
    field added to the HTTP body appears here without anyone remembering to add
    it — and so this assertion is about the derivation rather than about today's
    three fields.
    """
    generated = ServiceRequestCreate.model_json_schema()
    schema = TOOL_DEFINITIONS[CREATE_SERVICE_REQUEST]["input_schema"]

    assert schema["required"] == generated["required"]
    assert set(schema["properties"]) == set(generated["properties"])
    for field, expected in generated["properties"].items():
        actual = dict(schema["properties"][field])
        # The description is the only thing added on top (it is prompt copy,
        # which has no business in the published OpenAPI document).
        actual.pop("description", None)
        assert actual == expected


def test_the_create_tool_exposes_no_identity_argument() -> None:
    """CHAT-7 at the schema level: there is no field to spoof.

    The runtime guarantee is asserted against a real row in
    ``tests/api/test_chat.py``. This one is about the surface the model is
    shown — a ``user_id`` argument that was ignored would still be an argument
    a model would fill in, and a reader would have to check the handler to find
    out it meant nothing.
    """
    for name in (CREATE_SERVICE_REQUEST, GET_REQUEST_STATUS):
        properties = TOOL_DEFINITIONS[name]["input_schema"]["properties"]
        assert not {"user_id", "requestor_id", "assignee", "assignee_id", "role"} & set(
            properties
        )


def test_the_class_name_and_docstring_do_not_leak_into_the_schema() -> None:
    """Pydantic titles a schema after its class and copies the docstring in.

    Both describe an HTTP request body — ``ServiceRequestCreate``, "``POST
    /service-requests`` body" — which tells a model nothing it can use and
    something slightly wrong about what it is doing.
    """
    schema = TOOL_DEFINITIONS[CREATE_SERVICE_REQUEST]["input_schema"]
    assert "title" not in schema
    assert "description" not in schema


def test_available_tools_offers_every_defined_tool_in_a_stable_order() -> None:
    """Since T-CHAT-0b the offered list and the definitions cannot differ.

    Membership used to be conditional, which is what made "defined" and
    "offered" two separate things worth asserting separately. They are one
    thing now, and this pins that: a definition added without being offered is
    a tool the model never sees, which is the quiet half of the old bug.
    """
    assert [tool["name"] for tool in available_tools()] == [
        CREATE_SERVICE_REQUEST,
        GET_REQUEST_STATUS,
    ]
    assert {tool["name"] for tool in available_tools()} == set(TOOL_DEFINITIONS)
    assert available_tools() == available_tools()
