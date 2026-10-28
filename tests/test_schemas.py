from app.schemas import CreateCallRequest

def test_create_call_request_accepts_from_alias():
    payload = CreateCallRequest.model_validate({
        "from": "+15550000001",
        "to": "+15550000002",
        "metadata": {"source": "test"},
    })
    assert payload.from_number == "+15550000001"
    assert payload.to == "+15550000002"
    assert payload.metadata == {"source": "test"}
