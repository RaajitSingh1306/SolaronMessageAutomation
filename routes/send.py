import logging
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse

from config import Config
from helpers import _append_send_log
from services.contacts import get_phone_number
from services.excel import update_excel_status
from services.messaging import (
    generate_message,
    generate_monsoon_message,
    get_whatsapp_web_url,
    send_whatsapp_messages,
)
from state import (
    SendRequest,
    TestSendRequest,
    _add_job,
    get_send_job,
    update_send_job,
    get_state,
    update_state,
)

logger = logging.getLogger(__name__)
router = APIRouter()

def _do_send(queue: list[dict], job_id: str, *, update_excel: bool = True, gap_seconds: int = 3, manual_mode: bool = True) -> None:
    def progress_callback(current: int, total: int, plant_name: str):
        if get_send_job(job_id):
            update_send_job(job_id,
                status="running",
                current=current,
                total=total,
                current_plant=plant_name,
                manual_mode=manual_mode,
            )

    def cancel_check() -> bool:
        job = get_send_job(job_id)
        return bool(job and job.get("status") == "cancelled")

    def pause_check() -> bool:
        job = get_send_job(job_id)
        return bool(job and job.get("status") == "paused")

    def skip_check() -> bool:
        job = get_send_job(job_id)
        if job and job.get("skip_requested"):
            update_send_job(job_id, skip_requested=False)
            return True
        return False

    def advance_check() -> bool:
        job = get_send_job(job_id)
        if job and job.get("advance_requested"):
            update_send_job(job_id, advance_requested=False)
            return True
        return False

    update_send_job(job_id, status="running", manual_mode=manual_mode)
    try:
        results = send_whatsapp_messages(
            queue,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
            pause_check=pause_check,
            skip_check=skip_check,
            advance_check=advance_check,
            gap_time=gap_seconds,
            manual_mode=manual_mode,
        )
        
        state = get_state()
        sent_plants = results.get("sent_plants", [])
        if sent_plants:
            from services.send_tracker import record_successful_sends
            phone_map = {item["plant_name"]: item.get("phone", "") for item in queue}
            month_str = getattr(state, "month", None) or None
            record_successful_sends(sent_plants, month_str=month_str, phone_map=phone_map)

        _append_send_log(results)

        job_status = "cancelled" if cancel_check() else "done"
        update_send_job(job_id,
            status=job_status,
            sent=results["sent"],
            failed=results["failed"],
            skipped=results.get("skipped", 0),
            sent_plants=results.get("sent_plants", []),
            errors=results["errors"],
        )
        logger.info(
            "Background send job %s %s: %d sent, %d failed, %d skipped.",
            job_id,
            job_status,
            results["sent"],
            results["failed"],
            results.get("skipped", 0),
        )
    except Exception as exc:
        logger.exception("Background send job %s failed: %s", job_id, exc)
        update_send_job(job_id, status="error", error=str(exc))


@router.post("/api/send")
def send_messages(body: SendRequest, background_tasks: BackgroundTasks):
    selected_names = body.plants

    if not selected_names:
        return JSONResponse(
            {"success": False, "message": "No plants selected."}, status_code=400
        )

    state = get_state()
    if not state.classified:
        return JSONResponse(
            {
                "success": False,
                "message": "No plant data loaded. Please fetch data or upload an Excel report first.",
            },
            status_code=400,
        )

    queue: list[dict] = []
    selected_set = set(selected_names)
    added_plants = set()

    for status, plants in state.classified.items():
        for p in plants:
            if p.plant_name not in selected_set or p.plant_name in added_plants:
                continue
            phone = get_phone_number(p.plant_name)
            message = generate_message(p, status, state.month_name, state.year, view_mode=body.view)
            if not phone:
                logger.warning("No phone for '%s' — skipping.", p.plant_name)
                continue
            if not message:
                logger.info(
                    "No message for '%s' (Not Commissioned) — skipping.", p.plant_name
                )
                continue
            added_plants.add(p.plant_name)
            queue.append(
                {
                    "phone": phone,
                    "message": message,
                    "plant_name": p.plant_name,
                    "row_index": getattr(p, "row_index", 0),
                }
            )

    if not queue:
        return {
            "success": False,
            "message": "No sendable plants found (missing phone numbers or no message to send).",
        }

    job_id = str(uuid.uuid4())
    manual_mode = getattr(body, "manual_mode", True)
    if manual_mode is None:
        manual_mode = True

    _add_job(job_id, {
        "status": "queued",
        "total": len(queue),
        "sent": 0,
        "failed": 0,
        "skipped": 0,
        "sent_plants": [],
        "errors": [],
        "manual_mode": manual_mode,
        "gap_seconds": getattr(body, "gap_seconds", 3) or 3,
    })

    gap_seconds = getattr(body, "gap_seconds", 3) or 3
    background_tasks.add_task(_do_send, queue, job_id, gap_seconds=gap_seconds, manual_mode=manual_mode)

    logger.info(
        "Send job %s queued: %d plants to send (manual_mode=%s, gap=%ds).",
        job_id, len(queue), manual_mode, gap_seconds
    )
    return {
        "success": True,
        "message": f"Send started in background for {len(queue)} plants.",
        "job_id": job_id,
        "gap_seconds": gap_seconds,
        "manual_mode": manual_mode,
    }


@router.post("/api/send/cancel")
def cancel_active_send():
    """Cancels any running background WhatsApp send job."""
    from state import _send_jobs, _state_lock
    cancelled_any = False
    with _state_lock:
        for j_id, j_data in _send_jobs.items():
            if j_data.get("status") in ("running", "queued", "paused"):
                j_data["status"] = "cancelled"
                cancelled_any = True
    if cancelled_any:
        return {"success": True, "message": "Active send batch cancelled."}
    return {"success": True, "message": "No active send batch running."}


@router.post("/api/send/pause")
def pause_active_send():
    """Pauses any running background WhatsApp send job without killing the process."""
    from state import _send_jobs, _state_lock
    paused_any = False
    with _state_lock:
        for j_id, j_data in _send_jobs.items():
            if j_data.get("status") in ("running", "queued"):
                j_data["status"] = "paused"
                paused_any = True
    if paused_any:
        return {"success": True, "message": "Execution paused. Click Resume when ready."}
    return {"success": False, "message": "No active send batch running to pause."}


@router.post("/api/send/resume")
def resume_active_send():
    """Resumes a paused background WhatsApp send job."""
    from state import _send_jobs, _state_lock
    resumed_any = False
    with _state_lock:
        for j_id, j_data in _send_jobs.items():
            if j_data.get("status") == "paused":
                j_data["status"] = "running"
                resumed_any = True
    if resumed_any:
        return {"success": True, "message": "Execution resumed!"}
    return {"success": False, "message": "No paused send batch found to resume."}


@router.post("/api/send/skip")
def skip_active_send():
    """Skips the current contact in the active send batch."""
    from state import _send_jobs, _state_lock
    with _state_lock:
        for j_id, j_data in _send_jobs.items():
            if j_data.get("status") in ("running", "paused"):
                j_data["skip_requested"] = True
                return {"success": True, "message": "Skipping current contact..."}
    return {"success": False, "message": "No active send batch running to skip."}


@router.post("/api/send/next")
def next_active_send():
    """Advances to the next contact (e.g. if user clicked Send via mouse in WhatsApp)."""
    from state import _send_jobs, _state_lock
    with _state_lock:
        for j_id, j_data in _send_jobs.items():
            if j_data.get("status") in ("running", "paused"):
                j_data["advance_requested"] = True
                return {"success": True, "message": "Advancing to next contact..."}
    return {"success": False, "message": "No active send batch running to advance."}



@router.get("/api/send-status/{job_id}")
def get_send_status(job_id: str):
    job = get_send_job(job_id)
    if not job:
        return {
            "success": True, 
            "status": "error", 
            "error": "Job expired or backend restarted. Please try again."
        }
    return {"success": True, "job_id": job_id, **job}


@router.post("/api/monsoon")
def trigger_monsoon(background_tasks: BackgroundTasks):
    state = get_state()
    if not state.classified:
        return JSONResponse(
            {
                "success": False,
                "message": "No plant data loaded. Please fetch data or upload an Excel report first.",
            },
            status_code=400,
        )

    monsoon_msg = generate_monsoon_message()
    queue: list[dict] = []

    for plants in state.classified.values():
        for p in plants:
            phone = get_phone_number(p.plant_name)
            if phone:
                queue.append(
                    {"phone": phone, "message": monsoon_msg, "plant_name": p.plant_name}
                )

    if not queue:
        return {"success": False, "message": "No contacts with phone numbers found."}

    job_id = str(uuid.uuid4())
    _add_job(job_id, {
        "status": "queued",
        "total": len(queue),
        "sent": 0,
        "failed": 0,
        "sent_plants": [],
        "errors": [],
    })

    background_tasks.add_task(_do_send, queue, job_id, update_excel=False)

    logger.info(
        "Monsoon send job %s queued: %d contacts.", job_id, len(queue)
    )
    return {
        "success": True,
        "message": f"Monsoon alert send started in background for {len(queue)} contacts.",
        "job_id": job_id,
    }


@router.post("/api/test-send")
def test_send_message(body: Optional[TestSendRequest] = None):
    test_phone = (body.phone.strip() if body and body.phone else "") or Config.TEST_PHONE_NUMBER
    if not test_phone:
        return JSONResponse(
            {
                "success": False,
                "message": "No test phone number configured. Please provide a phone number.",
            },
            status_code=400,
        )

    test_message = (
        body.message.strip()
        if body and body.message
        else (
            "Greetings From Solaron Homes Pvt Ltd,\n\n"
            "Dear User,\n"
            "This is a test message from the Solaron Automated Messaging System.\n"
            "If you received this, the WhatsApp integration is working perfectly!\n\n"
            "Thank You,\n"
            "Team Solaron"
        )
    )

    test_contact = {
        "phone": test_phone,
        "message": test_message,
        "plant_name": "Test User",
    }

    whatsapp_url = get_whatsapp_web_url(test_phone, test_message)

    results = send_whatsapp_messages([test_contact])

    return {
        "success": True,
        "message": f"Test message send attempt complete. Success: {results['sent']}, Failed: {results['failed']}",
        "results": results,
        "whatsapp_url": whatsapp_url,
        "phone": test_phone,
    }
