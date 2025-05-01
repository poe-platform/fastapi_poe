import pydantic
import pytest
from fastapi_poe.types import CostItem, PartialResponse, SettingsResponse


class TestSettingsResponse:

    def test_default_response_version(self) -> None:
        response = SettingsResponse()
        assert response.response_version == 1


def test_extra_attrs() -> None:
    with pytest.raises(pydantic.ValidationError):
        PartialResponse(text="hi", replaceResponse=True)  # type: ignore

    resp = PartialResponse(text="a capybara", is_replace_response=True)
    assert resp.is_replace_response is True
    assert resp.text == "a capybara"


def test_cost_item() -> None:
    with pytest.raises(pydantic.ValidationError):
        CostItem(amount_usd_milli_cents=1.5)  # type: ignore

    with pytest.raises(pydantic.ValidationError):
        CostItem(amount_usd_milli_cents="1")  # type: ignore

    with pytest.raises(pydantic.ValidationError):
        CostItem(amount_usd_milli_cents=-2.5)  # type: ignore

    item = CostItem(amount_usd_milli_cents=25)
    assert item.amount_usd_milli_cents == 25
    assert item.description is None
