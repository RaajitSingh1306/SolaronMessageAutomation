"""
Solaron CRM API Routes
Provides endpoints for Customer Directory, Statements, Campaigns, Offline Alerts, and Data Health.
"""

import io
import os
import csv
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Response
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from config import Config
from crm.db import get_crm_db
from crm.models import Customer, CampaignLog, MessageQueue
from crm.generator import (
    get_monthly_statements,
    get_yearly_statements,
    get_unmapped_plants,
    get_offline_plants,
    _get_analytics_conn,
)
from crm.queue_manager import (
    get_data_health,
    prepare_campaign,
    prepare_yearly_campaign,
    prepare_offline_alerts,
    get_campaign_messages,
    update_message_status,
    execute_campaign_dry_run,
    export_campaign_csv,
)

router = APIRouter(prefix="/api/crm", tags=["CRM"])


# ── Pydantic Request Models ──

class CustomerCreateUpdate(BaseModel):
    plant_id: Optional[str] = None
    plant_name: Optional[str] = None
    platform: Optional[str] = "growatt"
    customer_name: Optional[str] = None
    phone_number: Optional[str] = None
    opt_in_status: Optional[str] = "active"
    preferred_lang: Optional[str] = "english"
    notes: Optional[str] = None


class CampaignPrepareRequest(BaseModel):
    month: Optional[str] = None  # "YYYY-MM"
    year: Optional[int] = None
    month_num: Optional[int] = None


# ── 1. Customer Directory Endpoints ──

@router.get("/customers")
def list_customers(
    platform: Optional[str] = None,
    opt_in_status: Optional[str] = None,
    has_phone: Optional[str] = None,
    search: Optional[str] = None,
    unmapped_only: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db=Depends(get_crm_db)
):
    """List all customers with filters and pagination."""
    if unmapped_only:
        unmapped = get_unmapped_plants()
        return {
            "customers": unmapped,
            "total": len(unmapped),
            "page": 1,
            "page_size": len(unmapped),
            "is_unmapped_list": True
        }

    query = db.query(Customer)

    if platform:
        query = query.filter(Customer.platform.ilike(f"%{platform}%"))
    if opt_in_status:
        query = query.filter(Customer.opt_in_status == opt_in_status)
    if has_phone == "true":
        query = query.filter(Customer.phone_number.isnot(None), Customer.phone_number != "")
    elif has_phone == "false":
        query = query.filter((Customer.phone_number.is_(None)) | (Customer.phone_number == ""))

    if search:
        term = f"%{search}%"
        query = query.filter(
            (Customer.customer_name.ilike(term)) |
            (Customer.plant_name.ilike(term)) |
            (Customer.phone_number.ilike(term)) |
            (Customer.plant_id.ilike(term))
        )

    total = query.count()
    items = query.order_by(Customer.customer_name.asc()).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "customers": [
            {
                "customer_id": c.customer_id,
                "plant_id": c.plant_id,
                "plant_name": c.plant_name,
                "platform": c.platform,
                "customer_name": c.customer_name,
                "phone_number": c.phone_number,
                "opt_in_status": c.opt_in_status,
                "preferred_lang": c.preferred_lang,
                "notes": c.notes,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.post("/customers")
def create_customer(data: CustomerCreateUpdate, db=Depends(get_crm_db)):
    """Create a new customer or map a plant."""
    if not data.plant_id and not data.plant_name:
        raise HTTPException(status_code=400, detail="Plant ID or Plant Name is required.")

    plant_id = data.plant_id or f"manual-{int(datetime.now().timestamp())}"
    existing = db.query(Customer).filter(Customer.plant_id == plant_id).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Customer with plant_id {plant_id} already exists.")

    cust = Customer(
        plant_id=plant_id,
        plant_name=data.plant_name or plant_id,
        platform=data.platform or "growatt",
        customer_name=data.customer_name or data.plant_name or "New Customer",
        phone_number=data.phone_number,
        opt_in_status=data.opt_in_status or "active",
        preferred_lang=data.preferred_lang or "english",
        notes=data.notes
    )
    db.add(cust)
    db.commit()
    db.refresh(cust)
    return {"success": True, "customer_id": cust.customer_id, "message": "Customer created successfully"}


@router.post("/customers/{customer_id}")
def update_customer(customer_id: int, data: CustomerCreateUpdate, db=Depends(get_crm_db)):
    """Update customer contact info, opt-in status, name, or notes."""
    cust = db.query(Customer).filter(Customer.customer_id == customer_id).first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found.")

    if data.customer_name is not None:
        cust.customer_name = data.customer_name
    if data.phone_number is not None:
        # Standardize phone
        raw = data.phone_number.strip()
        cust.phone_number = raw if raw else None
    if data.opt_in_status is not None:
        cust.opt_in_status = data.opt_in_status
    if data.preferred_lang is not None:
        cust.preferred_lang = data.preferred_lang
    if data.notes is not None:
        cust.notes = data.notes

    db.commit()
    return {"success": True, "message": "Customer updated successfully"}


@router.post("/customers/import")
async def import_customers_csv(file: UploadFile = File(...), db=Depends(get_crm_db)):
    """Bulk import / update customer phone numbers and names from CSV."""
    content = await file.read()
    text = content.decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))

    updated_count = 0
    created_count = 0
    errors = []

    for idx, row in enumerate(reader, start=2):
        plant_id = (row.get("plant_id") or row.get("Plant ID") or "").strip()
        plant_name = (row.get("plant_name") or row.get("Plant Name") or "").strip()
        phone = (row.get("phone_number") or row.get("phone") or row.get("Phone") or "").strip()
        c_name = (row.get("customer_name") or row.get("Name") or "").strip()
        opt_in = (row.get("opt_in_status") or row.get("Opt In") or "active").strip().lower()

        if not plant_id and not plant_name:
            continue

        cust = None
        if plant_id:
            cust = db.query(Customer).filter(Customer.plant_id == plant_id).first()
        if not cust and plant_name:
            cust = db.query(Customer).filter(Customer.plant_name.ilike(plant_name)).first()

        if cust:
            if phone:
                cust.phone_number = phone
            if c_name:
                cust.customer_name = c_name
            if opt_in in ("active", "do_not_send", "pending"):
                cust.opt_in_status = opt_in
            updated_count += 1
        else:
            new_cust = Customer(
                plant_id=plant_id or f"imp-{int(datetime.now().timestamp())}-{idx}",
                plant_name=plant_name or plant_id,
                platform=(row.get("platform") or "growatt").strip(),
                customer_name=c_name or plant_name or "New Customer",
                phone_number=phone if phone else None,
                opt_in_status=opt_in if opt_in in ("active", "do_not_send", "pending") else "pending",
                notes="Imported via CSV"
            )
            db.add(new_cust)
            created_count += 1

    db.commit()
    return {
        "success": True,
        "updated": updated_count,
        "created": created_count,
        "errors": errors
    }


@router.get("/customers/export")
def export_customers_csv(db=Depends(get_crm_db)):
    """Downloads full customers table as CSV."""
    customers = db.query(Customer).order_by(Customer.plant_name.asc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["customer_id", "plant_id", "plant_name", "platform", "customer_name", "phone_number", "opt_in_status", "preferred_lang", "notes"])

    for c in customers:
        writer.writerow([
            c.customer_id,
            c.plant_id,
            c.plant_name or "",
            c.platform or "",
            c.customer_name or "",
            c.phone_number or "",
            c.opt_in_status or "",
            c.preferred_lang or "",
            c.notes or ""
        ])

    output.seek(0)
    response = StreamingResponse(iter([output.getvalue()]), media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=customers_directory.csv"
    return response


# ── 2. Billing & Statements Endpoints ──

@router.get("/statements")
def get_statements(month: Optional[str] = None, year: Optional[int] = None):
    """
    Returns monthly statements or yearly summaries.
    month format: "YYYY-MM"
    year format: YYYY
    """
    if year and not month:
        statements = get_yearly_statements(year)
        total_gen = sum(s["total_kwh"] for s in statements)
        total_savings = sum(s["total_savings"] for s in statements)
        return {
            "granularity": "yearly",
            "year": year,
            "statements": statements,
            "summary": {
                "total_generation_kwh": round(total_gen, 1),
                "total_savings_inr": round(total_savings, 2),
                "total_customers": len(statements)
            }
        }

    # Monthly
    if not month:
        now = datetime.now()
        month = f"{now.year:04d}-{now.month:02d}"

    parts = month.split("-")
    y = int(parts[0])
    m = int(parts[1])

    statements = get_monthly_statements(y, m)
    total_gen = sum(s.generation_kwh for s in statements)
    total_savings = sum(s.savings_inr for s in statements)
    customers_ready = sum(1 for s in statements if not s.is_missing_phone and not s.is_opted_out)
    reports_pending = sum(1 for s in statements if s.message_status in ("Not Queued", "PENDING"))

    return {
        "granularity": "monthly",
        "month": month,
        "statements": [s.to_dict() for s in statements],
        "summary": {
            "total_generation_kwh": round(total_gen, 1),
            "total_savings_inr": round(total_savings, 2),
            "customers_ready": customers_ready,
            "reports_pending": reports_pending,
            "total_statements": len(statements)
        }
    }


# ── 3. Campaign Manager Endpoints ──

@router.post("/campaigns/prepare")
def api_prepare_campaign(req: CampaignPrepareRequest):
    """Generates monthly statements and prepares message_queue entries."""
    if req.month:
        parts = req.month.split("-")
        y = int(parts[0])
        m = int(parts[1])
    elif req.year and req.month_num:
        y = req.year
        m = req.month_num
    else:
        now = datetime.now()
        y = now.year
        m = now.month

    result = prepare_campaign(y, m)
    return {"success": True, **result}


@router.post("/campaigns/prepare-yearly")
def api_prepare_yearly_campaign(year: int = Query(..., ge=2020, le=2030)):
    """Generates yearly milestone recap campaign and prepares message_queue entries."""
    result = prepare_yearly_campaign(year)
    return {"success": True, **result}


@router.get("/campaigns")
def list_campaigns(db=Depends(get_crm_db)):
    """List all campaigns in reverse chronological order."""
    campaigns = db.query(CampaignLog).order_by(CampaignLog.campaign_id.desc()).all()
    return {
        "campaigns": [
            {
                "campaign_id": c.campaign_id,
                "campaign_name": c.campaign_name,
                "month_year": c.month_year,
                "total_customers": c.total_customers,
                "sent_count": c.sent_count,
                "failed_count": c.failed_count,
                "skipped_count": c.skipped_count,
                "status": c.status,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "completed_at": c.completed_at.isoformat() if c.completed_at else None,
            }
            for c in campaigns
        ]
    }


@router.get("/campaigns/{campaign_id}")
def get_campaign_details(campaign_id: int, db=Depends(get_crm_db)):
    """Get campaign details and message list."""
    campaign = db.query(CampaignLog).filter(CampaignLog.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    messages = get_campaign_messages(campaign_id)
    return {
        "campaign": {
            "campaign_id": campaign.campaign_id,
            "campaign_name": campaign.campaign_name,
            "month_year": campaign.month_year,
            "total_customers": campaign.total_customers,
            "sent_count": campaign.sent_count,
            "failed_count": campaign.failed_count,
            "skipped_count": campaign.skipped_count,
            "status": campaign.status,
            "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
            "completed_at": campaign.completed_at.isoformat() if campaign.completed_at else None,
        },
        "messages": messages
    }


@router.post("/campaigns/{campaign_id}/export")
def api_export_campaign(campaign_id: int):
    """Exports campaign messages to a downloadable CSV file."""
    filepath = export_campaign_csv(campaign_id)
    return FileResponse(filepath, media_type="text/csv", filename=f"whatsapp_campaign_{campaign_id}.csv")


@router.post("/campaigns/{campaign_id}/dry-run")
def api_dry_run_campaign(campaign_id: int):
    """Executes a console dry run for pending messages in the campaign."""
    res = execute_campaign_dry_run(campaign_id)
    return {"success": True, **res}


# ── 4. Offline Alerts Endpoints ──

@router.get("/offline")
def list_offline_plants(threshold_hours: float = Query(24.0, ge=1.0)):
    """Lists plants offline > threshold_hours from inverter_snapshots."""
    offline_plants = get_offline_plants(threshold_hours)
    return {
        "threshold_hours": threshold_hours,
        "total_offline": len(offline_plants),
        "plants": offline_plants
    }


@router.post("/offline/prepare-alerts")
def api_prepare_offline_alerts(threshold_hours: float = Query(24.0, ge=1.0)):
    """Prepares offline alerts campaign in message_queue."""
    res = prepare_offline_alerts(threshold_hours)
    return {"success": True, **res}


# ── 5. Data Health Endpoint ──

@router.get("/health")
def api_data_health():
    """Returns data health counts."""
    return get_data_health()


# ── 6. Customer Drill-down & Analytics Overview ──

@router.get("/customers/{customer_id}/full-profile")
def get_customer_full_profile(customer_id: int, db=Depends(get_crm_db)):
    """
    Returns a complete customer profile with:
    - Customer metadata (name, phone, plant, platform)
    - Message history (all campaigns sent to this customer)
    - Generation history (from solar_analytics.db)
    - Aggregate totals (lifetime kWh, savings, CO2)
    """
    cust = db.query(Customer).filter(Customer.customer_id == customer_id).first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")

    # --- Message history ---
    messages = db.query(MessageQueue).filter(
        MessageQueue.customer_id == customer_id
    ).order_by(MessageQueue.queued_at.desc()).all()

    # --- Generation history ---
    monthly_history = []
    total_kwh = 0.0
    analytics_conn = _get_analytics_conn()
    if analytics_conn:
        try:
            adapt = "?" if "sqlite3" in str(type(analytics_conn)) else "%s"
            cur = analytics_conn.cursor()
            cur.execute(
                f"""
                SELECT month, energy_kwh, specific_yield_kwh_kwp, cuf_pct, avg_daily_kwh
                FROM monthly_generation
                WHERE LOWER(TRIM(plant_name)) = LOWER(TRIM({adapt}))
                ORDER BY month DESC
                LIMIT 24
                """,
                (cust.plant_name or "",)
            )
            rows = cur.fetchall()
            for row in rows:
                if hasattr(row, 'keys'):
                    r = dict(row)
                else:
                    keys = ["month", "energy_kwh", "specific_yield_kwh_kwp", "cuf_pct", "avg_daily_kwh"]
                    r = dict(zip(keys, row))
                monthly_history.append(r)
                total_kwh += float(r.get("energy_kwh") or 0.0)
        except Exception:
            pass
        finally:
            analytics_conn.close()

    tariff = float(os.getenv("TARIFF_PER_KWH", str(Config.PRICE_PER_UNIT_INR)))
    co2_factor = float(os.getenv("CO2_KG_PER_KWH", str(Config.CO2_FACTOR_KG_PER_KWH)))

    sent_messages = [m for m in messages if m.status == "SENT"]
    failed_messages = [m for m in messages if m.status in ("FAILED", "ERROR")]

    return {
        "customer": {
            "customer_id": cust.customer_id,
            "customer_name": cust.customer_name,
            "plant_name": cust.plant_name,
            "plant_id": cust.plant_id,
            "platform": cust.platform,
            "phone_number": cust.phone_number,
            "opt_in_status": cust.opt_in_status,
            "preferred_lang": cust.preferred_lang,
        },
        "generation_totals": {
            "total_kwh": round(total_kwh, 1),
            "total_savings_inr": round(total_kwh * tariff, 2),
            "total_co2_kg": round(total_kwh * co2_factor, 1),
            "months_recorded": len(monthly_history),
        },
        "messaging_totals": {
            "total_sent": len(sent_messages),
            "total_failed": len(failed_messages),
            "delivery_rate_pct": round(
                len(sent_messages) / len(messages) * 100, 1
            ) if messages else 0.0,
            "last_message_at": max(
                (m.sent_at.isoformat() for m in sent_messages if m.sent_at), default=None
            ),
        },
        "monthly_history": monthly_history,
        "message_history": [
            {
                "message_id": m.message_id,
                "campaign_id": m.campaign_id,
                "month_year": m.month_year,
                "template_used": m.template_used,
                "status": m.status,
                "sent_at": m.sent_at.isoformat() if m.sent_at else None,
                "error_reason": m.error_reason,
            }
            for m in messages
        ],
    }


@router.get("/analytics/overview")
def get_crm_analytics_overview(db=Depends(get_crm_db)):
    from sqlalchemy import func

    total_customers = db.query(Customer).count()
    active_customers = db.query(Customer).filter(
        Customer.opt_in_status == "active"
    ).count()
    with_phone = db.query(Customer).filter(
        Customer.phone_number.isnot(None),
        Customer.phone_number != ""
    ).count()

    campaigns = db.query(CampaignLog).all()
    total_sent = sum(getattr(c, "sent_count", 0) or 0 for c in campaigns)
    total_failed = sum(getattr(c, "failed_count", 0) or 0 for c in campaigns)
    delivery_rate = (
        round(total_sent / (total_sent + total_failed) * 100, 1)
        if (total_sent + total_failed) > 0 else 0.0
    )

    platform_counts = db.query(
        Customer.platform, func.count(Customer.customer_id)
    ).group_by(Customer.platform).all()

    # Recent campaign performance (last 5)
    recent = sorted(campaigns, key=lambda c: str(c.created_at or ""), reverse=True)[:5]

    return {
        "coverage": {
            "total_customers": total_customers,
            "active_opt_in": active_customers,
            "with_phone_number": with_phone,
            "coverage_pct": round(with_phone / total_customers * 100, 1)
                            if total_customers else 0.0,
        },
        "messaging": {
            "total_campaigns": len(campaigns),
            "total_messages_sent": total_sent,
            "total_failed": total_failed,
            "delivery_rate_pct": delivery_rate,
        },
        "by_platform": {str(p): int(c) for p, c in platform_counts},
        "recent_campaigns": [
            {
                "campaign_id": c.campaign_id,
                "campaign_name": c.campaign_name,
                "sent": c.sent_count,
                "failed": c.failed_count,
                "status": c.status,
            }
            for c in recent
        ],
    }


# ── 7. Full CSV Export Endpoints ──

@router.get("/export/customers-full")
def export_customers_full_csv(db=Depends(get_crm_db)):
    """
    Full customer list with message stats per customer.
    Suitable for Freshworks contact import or Excel analysis.
    """
    customers = db.query(Customer).all()
    messages = db.query(MessageQueue).all()

    stats_map = {}
    for m in messages:
        cid = m.customer_id
        if not cid:
            continue
        if cid not in stats_map:
            stats_map[cid] = {"sent": 0, "failed": 0, "last_sent": None, "campaign_count": set()}
        if m.status == "SENT":
            stats_map[cid]["sent"] += 1
            if not stats_map[cid]["last_sent"] or (m.sent_at and m.sent_at > stats_map[cid]["last_sent"]):
                stats_map[cid]["last_sent"] = m.sent_at
        elif m.status in ("FAILED", "ERROR"):
            stats_map[cid]["failed"] += 1
        if m.campaign_id:
            stats_map[cid]["campaign_count"].add(m.campaign_id)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "customer_id", "plant_id", "plant_name", "platform",
        "customer_name", "phone_number", "opt_in_status", "preferred_lang",
        "messages_sent", "messages_failed", "campaigns_included_in",
        "last_sent_at", "delivery_rate_pct"
    ])
    for c in customers:
        s = stats_map.get(c.customer_id, {})
        total = s.get("sent", 0) + s.get("failed", 0)
        rate = round(s.get("sent", 0) / total * 100, 1) if total > 0 else 0.0
        writer.writerow([
            c.customer_id,
            getattr(c, "plant_id", "") or "",
            c.plant_name or "",
            c.platform or "",
            c.customer_name or "",
            c.phone_number or "",
            c.opt_in_status or "",
            c.preferred_lang or "",
            s.get("sent", 0),
            s.get("failed", 0),
            len(s.get("campaign_count", set())),
            s["last_sent"].isoformat() if s.get("last_sent") else "",
            rate,
        ])

    output.seek(0)
    resp = StreamingResponse(iter([output.getvalue()]), media_type="text/csv")
    resp.headers["Content-Disposition"] = "attachment; filename=solaron_customers_full.csv"
    return resp


@router.get("/export/campaign-performance")
def export_campaign_performance_csv(db=Depends(get_crm_db)):
    """Per-campaign performance export."""
    campaigns = db.query(CampaignLog).order_by(CampaignLog.created_at.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "campaign_id", "campaign_name", "month_year", "platform_filter",
        "template_used", "total_queued", "sent", "failed",
        "delivery_rate_pct", "status", "created_at", "completed_at"
    ])
    for c in campaigns:
        total = (c.sent_count or 0) + (c.failed_count or 0)
        rate = round((c.sent_count or 0) / total * 100, 1) if total > 0 else 0.0
        writer.writerow([
            c.campaign_id,
            c.campaign_name or "",
            getattr(c, "month_year", "") or "",
            getattr(c, "platform_filter", "all") or "all",
            getattr(c, "template_used", "") or "",
            total,
            c.sent_count or 0,
            c.failed_count or 0,
            rate,
            c.status or "",
            c.created_at.isoformat() if c.created_at else "",
            c.completed_at.isoformat() if getattr(c, "completed_at", None) else "",
        ])
    output.seek(0)
    resp = StreamingResponse(iter([output.getvalue()]), media_type="text/csv")
    resp.headers["Content-Disposition"] = "attachment; filename=solaron_campaign_performance.csv"
    return resp


@router.get("/export/generation-by-customer")
def export_generation_by_customer_csv(month: Optional[str] = None, db=Depends(get_crm_db)):
    """
    Per-customer generation data joined with CRM info.
    This is the key report: who generated how much and what we sent them.
    """
    import datetime
    target_month = month or datetime.date.today().strftime("%Y-%m")

    customers = db.query(Customer).all()
    cust_map = {(c.plant_name or "").strip().lower(): c for c in customers}

    analytics_conn = _get_analytics_conn()
    gen_rows = []
    if analytics_conn:
        try:
            adapt = "?" if "sqlite3" in str(type(analytics_conn)) else "%s"
            cur = analytics_conn.cursor()
            cur.execute(
                f"""SELECT plant_name, energy_kwh, specific_yield_kwh_kwp,
                           avg_daily_kwh, cuf_pct, revenue
                    FROM monthly_generation WHERE month = {adapt}""",
                (target_month,)
            )
            gen_rows = cur.fetchall()
        except Exception:
            pass
        finally:
            analytics_conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "plant_name", "platform", "capacity_kwp",
        "customer_name", "phone_number", "opt_in_status",
        "month", "energy_kwh", "specific_yield_kwh_kwp",
        "avg_daily_kwh", "cuf_pct", "estimated_savings_inr",
        "crm_matched"
    ])

    tariff = float(os.getenv("TARIFF_PER_KWH", str(Config.PRICE_PER_UNIT_INR)))

    for row in gen_rows:
        if hasattr(row, "keys"):
            r = dict(row)
        else:
            keys = ["plant_name", "energy_kwh", "specific_yield_kwh_kwp",
                    "avg_daily_kwh", "cuf_pct", "revenue"]
            r = dict(zip(keys, row))

        plant_key = (r["plant_name"] or "").strip().lower()
        cust = cust_map.get(plant_key)
        writer.writerow([
            r.get("plant_name", ""),
            cust.platform if cust else "",
            "",
            cust.customer_name if cust else "UNMAPPED",
            cust.phone_number if cust else "",
            cust.opt_in_status if cust else "",
            target_month,
            r.get("energy_kwh", ""),
            r.get("specific_yield_kwh_kwp", ""),
            r.get("avg_daily_kwh", ""),
            r.get("cuf_pct", ""),
            round(float(r.get("energy_kwh") or 0.0) * tariff, 2),
            "yes" if cust else "no",
        ])

    output.seek(0)
    resp = StreamingResponse(iter([output.getvalue()]), media_type="text/csv")
    resp.headers["Content-Disposition"] = (
        f"attachment; filename=solaron_generation_{target_month}.csv"
    )
    return resp

