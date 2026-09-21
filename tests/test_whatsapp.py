import pytest
from unittest.mock import patch
from services.messaging import send_whatsapp_messages

@patch("services.messaging.whatsapp._send_whatsapp_instantly")
@patch("services.messaging.whatsapp.time.sleep")
def test_send_whatsapp_messages(mock_sleep, mock_send):
    message_queue = [
        {"plant_name": "Plant A", "phone": "9876543210", "message": "Msg A"},
        {"plant_name": "Plant B", "phone": "9876543211", "message": "Msg B"},
    ]
    
    results = send_whatsapp_messages(message_queue)
    
    assert results["sent"] == 2
    assert results["failed"] == 0
    assert len(results["sent_plants"]) == 2
    
    assert mock_send.call_count == 2
    calls = mock_send.call_args_list
    assert calls[0].kwargs["phone_no"] == "+919876543210"
    assert calls[0].kwargs["message"] == "Msg A"
    assert calls[0].kwargs["is_first"] is True
    assert calls[1].kwargs["phone_no"] == "+919876543211"
    assert calls[1].kwargs["message"] == "Msg B"
    assert calls[1].kwargs["is_first"] is False


@patch("services.messaging.whatsapp._send_whatsapp_instantly")
@patch("services.messaging.whatsapp.time.sleep")
def test_send_whatsapp_messages_failure(mock_sleep, mock_send):
    message_queue = [
        {"plant_name": "Plant A", "phone": "9876543210", "message": "Msg A"},
    ]
    
    mock_send.side_effect = Exception("Browser error")
    
    results = send_whatsapp_messages(message_queue)
    
    assert results["sent"] == 0
    assert results["failed"] == 1
    assert len(results["errors"]) == 1
    assert "Browser error" in results["errors"][0]


@patch("services.messaging.whatsapp._send_whatsapp_instantly")
@patch("services.messaging.whatsapp.time.sleep")
def test_send_whatsapp_messages_manual_skip_and_cancel(mock_sleep, mock_send):
    message_queue = [
        {"plant_name": "Plant A", "phone": "9876543210", "message": "Msg A"},
        {"plant_name": "Plant B", "phone": "9876543211", "message": "Msg B"},
        {"plant_name": "Plant C", "phone": "9876543212", "message": "Msg C"},
    ]
    
    # Simulate: Plant A is sent, Plant B is skipped, Plant C is cancelled
    mock_send.side_effect = ["sent", "skipped", "cancelled"]
    
    results = send_whatsapp_messages(message_queue, manual_mode=True)
    
    assert results["sent"] == 1
    assert results["skipped"] == 1
    assert results["failed"] == 0
    assert results["sent_plants"] == ["Plant A"]
    assert mock_send.call_count == 3


