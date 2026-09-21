import pytest
from services.classifier import classify_plants, PlantStatus
from services.excel import PlantRecord

def test_classify_plants():
    # Active: current_power_kw > 0 or energy_today > 0
    active_plant = PlantRecord("Plant 1", 10.0, 100.0, 500.0, 0, 0, 0, 0, 0, "", "", 1, current_power_kw=3.5, energy_today=12.0)
    # Not Working: Online communicator (dev_code=1) but 0 today and 0 power while month > 0
    not_working_plant = PlantRecord("Plant 2", 50.0, 100.0, 500.0, 0, 0, 0, 0, 0, "", "", 2, current_power_kw=0.0, energy_today=0.0, device_status_code=1)
    # Offline: dev_code=0 or no month and no today gen with historic total
    offline_plant = PlantRecord("Plant 3", 0.0, 50.0, 200.0, 0, 0, 0, 0, 0, "", "", 3, current_power_kw=0.0, energy_today=0.0, device_status_code=0)
    # Not Commissioned: energy_this_month == 0 AND energy_total == 0
    not_commissioned = PlantRecord("Plant 4", 0.0, 0.0, 0.0, 0, 0, 0, 0, 0, "", "", 4)
    # Fault plant: explicit fault code
    fault_plant = PlantRecord("Plant 5", 20.0, 50.0, 300.0, 0, 0, 0, 0, 0, "", "", 5, fault_code="E023")

    records = [active_plant, not_working_plant, offline_plant, not_commissioned, fault_plant]
    classified = classify_plants(records)

    assert len(classified[PlantStatus.ACTIVE.value]) == 1
    assert classified[PlantStatus.ACTIVE.value][0].plant_name == "Plant 1"

    assert len(classified[PlantStatus.NOT_WORKING.value]) == 2
    assert classified[PlantStatus.NOT_WORKING.value][0].plant_name == "Plant 2"
    assert classified[PlantStatus.NOT_WORKING.value][1].plant_name == "Plant 5"

    assert len(classified[PlantStatus.OFFLINE.value]) == 1
    assert classified[PlantStatus.OFFLINE.value][0].plant_name == "Plant 3"

    assert len(classified[PlantStatus.NOT_COMMISSIONED.value]) == 1
    assert classified[PlantStatus.NOT_COMMISSIONED.value][0].plant_name == "Plant 4"

