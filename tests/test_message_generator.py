from services.messaging import generate_message, generate_monsoon_message
from services.excel.parser import PlantRecord

def test_generate_message_with_savings():
    record = PlantRecord(
        plant_name="John Doe",
        energy_this_month=150.5,
        energy_this_year=0,
        energy_total=1000.0,
        income_this_month=0,
        income_total=0,
        co2_this_month=0,
        co2_total=0,
        savings=1500.0,
        message_status="",
        nut_bolts="",
        row_index=1
    )
    
    msg = generate_message(record, "Active", "July", "2026")
    
    assert "July 2026" in msg
    assert "150 units" in msg
    from config import Config
    expected_savings = round(record.energy_this_month * Config.PRICE_PER_UNIT)
    assert str(expected_savings) in msg
    assert "Greetings From Solaron Homes Pvt Ltd" in msg
    assert "Team Solaron" in msg

def test_generate_message_without_savings():
    record = PlantRecord(
        plant_name="Jane Doe",
        energy_this_month=200.0,
        energy_this_year=0,
        energy_total=2000.0,
        income_this_month=0,
        income_total=0,
        co2_this_month=0,
        co2_total=0,
        savings=0.0,
        message_status="",
        nut_bolts="",
        row_index=1
    )
    
    msg = generate_message(record, "Active", "August", "2026")
    
    assert "August 2026" in msg
    assert "200 units" in msg
    # Should not contain the savings line
    assert "अतिरिक्त" not in msg # Additional money line

def test_generate_monsoon_message():
    msg = generate_monsoon_message()
    
    assert "monsoon season" in msg.lower()
    assert "Team Solaron" in msg

def test_generate_multi_period_messages():
    record = PlantRecord(
        plant_name="Multi Test Plant",
        energy_this_month=300.0,
        energy_this_year=3600.0,
        energy_total=10000.0,
        income_this_month=0,
        income_total=0,
        co2_this_month=0,
        co2_total=0,
        savings=3000.0,
        message_status="",
        nut_bolts="",
        row_index=1,
        capacity_kwp=5.0,
        energy_today=25.0,
        yearly_history={"2025": 3500.0, "2026": 3600.0},
    )
    
    # Daily
    msg_daily = generate_message(record, "Active", view_mode="daily", date_str="03 Sep 2026")
    assert "25 units today" in msg_daily
    assert "03 Sep 2026" in msg_daily

    # Weekly
    msg_weekly = generate_message(record, "Active", view_mode="weekly")
    assert "approximately 69 units this week" in msg_weekly

    # Yearly
    msg_yearly = generate_message(record, "Active", year="2026", view_mode="yearly")
    assert "3600 units in the year 2026" in msg_yearly
