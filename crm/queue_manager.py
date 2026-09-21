"""
Solaron CRM Queue Manager
Handles campaign lifecycle, message preparation, dispatch tracking,
data health auditing, and initial customer migration.
"""

import os
import csv
import calendar
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from config import Config
from .db import CRMSessionLocal
from .models import Customer, MessageQueue, CampaignLog
from .generator import get_monthly_statements, get_yearly_statements, get_offline_plants, get_unmapped_plants
from .templates import render
from .sender import ConsoleSender


def _utc_now():
    return datetime.now(timezone.utc)


def get_data_health() -> Dict[str, Any]:
    """
    Computes data health metrics:
    - unmapped_plants: plants in metadata with no customer record
    - missing_phones: customers with empty phone numbers
    - opted_out: customers with opt_in_status == 'do_not_send'
    - ready_to_message: customers with phone + active opt-in
    """
    db = CRMSessionLocal()
    try:
        customers = db.query(Customer).all()
        total_customers = len(customers)

        missing_phones = 0
        opted_out = 0
        ready_to_message = 0

        for c in customers:
            has_phone = bool(c.phone_number and c.phone_number.strip())
            is_active = (c.opt_in_status == "active")
            is_opted_out = (c.opt_in_status == "do_not_send")

            if not has_phone:
                missing_phones += 1
            if is_opted_out:
                opted_out += 1
            if has_phone and is_active:
                ready_to_message += 1

        unmapped = get_unmapped_plants()
        unmapped_count = len(unmapped)

        total_issues = unmapped_count + missing_phones + opted_out

        return {
            "total_customers": total_customers,
            "unmapped_plants": unmapped_count,
            "missing_phones": missing_phones,
            "opted_out": opted_out,
            "ready_to_message": ready_to_message,
            "total_issues": total_issues,
        }
    finally:
        db.close()


def prepare_campaign(year: int, month: int) -> Dict[str, Any]:
    """
    Prepares a monthly statement campaign for year and month.
    Generates statements, renders templates, and inserts into message_queue.
    """
    month_str = f"{year:04d}-{month:02d}"
    month_name = calendar.month_name[month]
    statements = get_monthly_statements(year, month)

    db = CRMSessionLocal()
    try:
        # Create CampaignLog
        campaign = CampaignLog(
            campaign_name=f"Monthly Billing — {month_name} {year}",
            month_year=month_str,
            total_customers=len(statements),
            status="DRAFT",
            created_at=_utc_now()
        )
        db.add(campaign)
        db.flush()  # assign campaign_id

        queued_count = 0
        skipped_count = 0

        for s in statements:
            # Check conditions
            has_phone = bool(s.phone_number and s.phone_number.strip())
            is_active = (s.opt_in_status == "active")
            is_opted_out = (s.opt_in_status == "do_not_send")

            # Determine dynamic template based on performance rating
            rating = (s.performance_rating or "").lower()
            if "best" in rating:
                tpl_key = "monthly_best"
            elif "good" in rating:
                tpl_key = "monthly_good"
            elif "could be better" in rating:
                tpl_key = "monthly_could_better"
            elif "needs attention" in rating or "critical" in rating:
                tpl_key = "monthly_needs_attention"
            else:
                tpl_key = "monthly_standard"

            # Determine rendered text
            try:
                msg_text = render(
                    tpl_key,
                    s,
                    lang=s.preferred_lang,
                    month_name=month_name,
                    year=year,
                    performance_rating=s.performance_rating or "Good",
                    marketing_cta=s.marketing_cta or "",
                )
            except Exception:
                try:
                    msg_text = render("monthly_standard", s, lang=s.preferred_lang, month_name=month_name, year=year)
                    tpl_key = "monthly_standard"
                except Exception:
                    msg_text = f"Hello {s.customer_name}! Your solar plant {s.plant_name} generated {s.generation_kwh:.1f} kWh in {month_name} {year}."
                    tpl_key = "monthly_standard"

            if is_opted_out:
                queue_item = MessageQueue(
                    campaign_id=campaign.campaign_id,
                    customer_id=s.customer_id,
                    phone_number=s.phone_number,
                    message_text=msg_text,
                    template_used=tpl_key,
                    month_year=month_str,
                    status="SKIPPED",
                    error_reason="Customer opted out (do_not_send)",
                    queued_at=_utc_now()
                )
                skipped_count += 1
            elif not has_phone:
                queue_item = MessageQueue(
                    campaign_id=campaign.campaign_id,
                    customer_id=s.customer_id,
                    phone_number="",
                    message_text=msg_text,
                    template_used=tpl_key,
                    month_year=month_str,
                    status="SKIPPED",
                    error_reason="Missing phone number",
                    queued_at=_utc_now()
                )
                skipped_count += 1
            elif is_active:
                queue_item = MessageQueue(
                    campaign_id=campaign.campaign_id,
                    customer_id=s.customer_id,
                    phone_number=s.phone_number,
                    message_text=msg_text,
                    template_used=tpl_key,
                    month_year=month_str,
                    status="PENDING",
                    queued_at=_utc_now()
                )
                queued_count += 1
            else:
                # pending opt-in
                queue_item = MessageQueue(
                    campaign_id=campaign.campaign_id,
                    customer_id=s.customer_id,
                    phone_number=s.phone_number,
                    message_text=msg_text,
                    template_used=tpl_key,
                    month_year=month_str,
                    status="SKIPPED",
                    error_reason="Opt-in status pending confirmation",
                    queued_at=_utc_now()
                )
                skipped_count += 1


            db.add(queue_item)

        campaign.skipped_count = skipped_count
        db.commit()

        return {
            "campaign_id": campaign.campaign_id,
            "campaign_name": campaign.campaign_name,
            "month_year": month_str,
            "total_statements": len(statements),
            "queued": queued_count,
            "skipped": skipped_count
        }
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def prepare_offline_alerts(threshold_hours: float = 24.0) -> Dict[str, Any]:
    """
    Identifies plants offline > threshold_hours and queues alert messages.
    """
    offline_plants = get_offline_plants(threshold_hours)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    db = CRMSessionLocal()
    try:
        campaign = CampaignLog(
            campaign_name=f"Offline Plant Alerts — {now_str}",
            month_year=datetime.now().strftime("%Y-%m"),
            total_customers=len(offline_plants),
            status="DRAFT",
            created_at=_utc_now()
        )
        db.add(campaign)
        db.flush()

        queued_count = 0
        skipped_count = 0

        for p in offline_plants:
            has_phone = bool(p["phone_number"] and p["phone_number"].strip())
            is_active = (p["opt_in_status"] == "active")
            is_opted_out = (p["opt_in_status"] == "do_not_send")
            lang = p.get("preferred_lang") or "english"

            msg_text = render(
                "offline_alert",
                {
                    "customer_name": p["customer_name"],
                    "plant_name": p["plant_name"],
                    "hours_offline": p["hours_offline"]
                },
                lang=lang
            )

            if is_opted_out:
                status = "SKIPPED"
                err = "Customer opted out"
                skipped_count += 1
            elif not has_phone:
                status = "SKIPPED"
                err = "Missing customer or phone number"
                skipped_count += 1
            elif is_active:
                status = "PENDING"
                err = None
                queued_count += 1
            else:
                status = "SKIPPED"
                err = "Opt-in status pending"
                skipped_count += 1

            queue_item = MessageQueue(
                campaign_id=campaign.campaign_id,
                customer_id=p.get("customer_id"),
                phone_number=p.get("phone_number") or "",
                message_text=msg_text,
                template_used="offline_alert",
                month_year=datetime.now().strftime("%Y-%m"),
                status=status,
                error_reason=err,
                queued_at=_utc_now()
            )
            db.add(queue_item)

        campaign.skipped_count = skipped_count
        db.commit()

        return {
            "campaign_id": campaign.campaign_id,
            "campaign_name": campaign.campaign_name,
            "total_offline": len(offline_plants),
            "queued": queued_count,
            "skipped": skipped_count
        }
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def prepare_yearly_campaign(year: int) -> Dict[str, Any]:
    """
    Prepares a yearly milestone recap campaign for a given year.
    Generates yearly summaries, renders templates, and inserts into message_queue.
    """
    statements = get_yearly_statements(year)
    year_str = str(year)

    db = CRMSessionLocal()
    try:
        campaign = CampaignLog(
            campaign_name=f"Yearly Milestone Recap — {year}",
            month_year=year_str,
            total_customers=len(statements),
            status="DRAFT",
            created_at=_utc_now()
        )
        db.add(campaign)
        db.flush()

        queued_count = 0
        skipped_count = 0

        for s in statements:
            phone = s.get("phone_number")
            has_phone = bool(phone and phone.strip())
            opt_in = s.get("opt_in_status", "pending")
            is_active = (opt_in == "active")
            is_opted_out = (opt_in == "do_not_send")
            total_kwh = s.get("total_kwh", 0.0)

            # Skip plants with 0 generation for yearly milestones
            if total_kwh <= 0.0:
                continue

            lang = s.get("preferred_lang") or "english"
            try:
                msg_text = render(
                    "yearly_milestone",
                    {
                        "customer_name": s["customer_name"],
                        "plant_name": s["plant_name"],
                        "total_kwh": total_kwh,
                        "year": year,
                        "days_powered": s.get("days_powered", 0.0),
                        "total_savings": s.get("total_savings", 0.0)
                    },
                    lang=lang
                )
            except Exception:
                msg_text = f"Congratulations {s['customer_name']}! Your solar plant {s['plant_name']} generated {total_kwh:.0f} kWh in {year}."

            if is_opted_out:
                status = "SKIPPED"
                err = "Customer opted out (do_not_send)"
                skipped_count += 1
            elif not has_phone:
                status = "SKIPPED"
                err = "Missing phone number"
                skipped_count += 1
            elif is_active:
                status = "PENDING"
                err = None
                queued_count += 1
            else:
                status = "SKIPPED"
                err = "Opt-in status pending confirmation"
                skipped_count += 1

            queue_item = MessageQueue(
                campaign_id=campaign.campaign_id,
                customer_id=s.get("customer_id"),
                phone_number=phone or "",
                message_text=msg_text,
                template_used="yearly_milestone",
                month_year=year_str,
                status=status,
                error_reason=err,
                queued_at=_utc_now()
            )
            db.add(queue_item)

        campaign.skipped_count = skipped_count
        db.commit()

        return {
            "campaign_id": campaign.campaign_id,
            "campaign_name": campaign.campaign_name,
            "year": year,
            "total_statements": len(statements),
            "queued": queued_count,
            "skipped": skipped_count
        }
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def get_campaign_messages(campaign_id: int) -> List[Dict[str, Any]]:
    """Fetches all message items for a specific campaign with customer details."""
    db = CRMSessionLocal()
    try:
        results = []
        messages = db.query(MessageQueue).filter(MessageQueue.campaign_id == campaign_id).all()
        cust_ids = [m.customer_id for m in messages if m.customer_id]
        customers = {c.customer_id: c for c in db.query(Customer).filter(Customer.customer_id.in_(cust_ids)).all()}

        for m in messages:
            cust = customers.get(m.customer_id)
            results.append({
                "message_id": m.message_id,
                "campaign_id": m.campaign_id,
                "customer_id": m.customer_id,
                "customer_name": cust.customer_name if cust else "Unknown",
                "plant_name": cust.plant_name if cust else "Unknown",
                "platform": cust.platform if cust else "growatt",
                "phone_number": m.phone_number,
                "message_text": m.message_text,
                "template_used": m.template_used,
                "month_year": m.month_year,
                "status": m.status,
                "error_reason": m.error_reason,
                "queued_at": m.queued_at.isoformat() if m.queued_at else None,
                "sent_at": m.sent_at.isoformat() if m.sent_at else None
            })
        return results
    finally:
        db.close()


def update_message_status(message_id: int, status: str, error_reason: Optional[str] = None):
    """Updates status for a single message."""
    db = CRMSessionLocal()
    try:
        msg = db.query(MessageQueue).filter(MessageQueue.message_id == message_id).first()
        if msg:
            msg.status = status
            if error_reason:
                msg.error_reason = error_reason
            if status in ("SENT", "SIMULATED"):
                msg.sent_at = _utc_now()
            db.commit()
    finally:
        db.close()


def execute_campaign_dry_run(campaign_id: int) -> Dict[str, Any]:
    """Simulates sending all PENDING messages in the campaign using ConsoleSender."""
    db = CRMSessionLocal()
    try:
        campaign = db.query(CampaignLog).filter(CampaignLog.campaign_id == campaign_id).first()
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found.")

        pending_msgs = db.query(MessageQueue).filter(
            MessageQueue.campaign_id == campaign_id,
            MessageQueue.status == "PENDING"
        ).all()

        sender = ConsoleSender()
        simulated_count = 0

        for msg in pending_msgs:
            res = sender.send(msg.phone_number, msg.message_text)
            if res.get("success"):
                msg.status = "SIMULATED"
                msg.sent_at = _utc_now()
                simulated_count += 1

        campaign.sent_count = (campaign.sent_count or 0) + simulated_count
        campaign.status = "COMPLETED" if len(pending_msgs) == simulated_count else "RUNNING"
        campaign.completed_at = _utc_now()
        db.commit()

        return {
            "campaign_id": campaign_id,
            "simulated_count": simulated_count,
            "total_pending": len(pending_msgs)
        }
    finally:
        db.close()


def export_campaign_csv(campaign_id: int) -> str:
    """Exports campaign messages to a downloadable CSV file."""
    db = CRMSessionLocal()
    try:
        campaign = db.query(CampaignLog).filter(CampaignLog.campaign_id == campaign_id).first()
        messages = db.query(MessageQueue).filter(MessageQueue.campaign_id == campaign_id).all()
        cust_ids = [m.customer_id for m in messages if m.customer_id]
        customers = {c.customer_id: c for c in db.query(Customer).filter(Customer.customer_id.in_(cust_ids)).all()}

        exports_dir = os.path.join(Config.DATA_FOLDER, "exports")
        os.makedirs(exports_dir, exist_ok=True)
        filename = f"whatsapp_campaign_export_{campaign_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        filepath = os.path.join(exports_dir, filename)

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["phone_number", "message_text", "customer_name", "plant_name", "status", "error_reason"])
            for m in messages:
                cust = customers.get(m.customer_id)
                writer.writerow([
                    m.phone_number or "",
                    m.message_text or "",
                    cust.customer_name if cust else "",
                    cust.plant_name if cust else "",
                    m.status or "",
                    m.error_reason or ""
                ])

        return filepath
    finally:
        db.close()


def seed_customers_from_phone_cache():
    """
    One-time migration:
    Populates Customer table in crm_data.db from:
    1. solar_analytics.db plants_metadata
    2. solaron.db phone_cache
    3. plants_with_contacts.csv / contacts.csv
    Ensures the CRM directory is pre-populated out of the box!
    """
    db = CRMSessionLocal()
    try:
        existing_count = db.query(Customer).count()
        if existing_count > 0:
            return existing_count

        phone_map = {}
        # 1. Read from solaron.db phone_cache
        solaron_db_path = os.path.join(Config.DATA_FOLDER, "solaron.db")
        if os.path.exists(solaron_db_path):
            try:
                import sqlite3
                conn = sqlite3.connect(solaron_db_path)
                cur = conn.cursor()
                cur.execute("SELECT plant_name, phone_number FROM phone_cache WHERE phone_number IS NOT NULL")
                for pname, pnum in cur.fetchall():
                    if pname and pnum:
                        phone_map[pname.strip().lower()] = str(pnum).strip()
                conn.close()
            except Exception:
                pass

        # 2. Read from CSVs if available
        csv_candidates = [
            os.path.join(Config.DATA_FOLDER, "plants_with_contacts.csv"),
            os.path.join(Config.DATA_FOLDER, "contacts.csv"),
            os.path.join(Config.BASE_DIR, "plants_with_contacts.csv"),
        ]
        for csv_path in csv_candidates:
            if os.path.exists(csv_path):
                try:
                    with open(csv_path, "r", encoding="utf-8-sig", errors="ignore") as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            pname = row.get("plant_name") or row.get("Plant Name") or row.get("plant")
                            phone = row.get("phone") or row.get("phone_number") or row.get("Phone Number") or row.get("Mobile")
                            if pname and phone:
                                phone_map[pname.strip().lower()] = str(phone).strip()
                except Exception:
                    pass

        # 3. Read metadata plants from solar_analytics.db
        plants_to_seed = []
        analytics_db = Config.ANALYTICS_DB_PATH
        if analytics_db and os.path.exists(analytics_db):
            try:
                import sqlite3
                conn = sqlite3.connect(f"file:{analytics_db}?mode=ro", uri=True)
                cur = conn.cursor()
                cur.execute("SELECT plant_id, plant_name, source, city FROM plants_metadata")
                for pid, pname, src, city in cur.fetchall():
                    plants_to_seed.append({
                        "plant_id": str(pid),
                        "plant_name": pname,
                        "platform": src or "growatt",
                        "city": city or ""
                    })
                conn.close()
            except Exception:
                pass

        # 4. If no plants in analytics db, fallback to plants from phone_map
        if not plants_to_seed:
            for idx, (pname, phone) in enumerate(phone_map.items(), start=1):
                plants_to_seed.append({
                    "plant_id": f"P-{idx:04d}",
                    "plant_name": pname,
                    "platform": "growatt",
                    "city": ""
                })

        # 5. Insert Customers into crm_data.db
        inserted = 0
        seen_pids = set()
        for p in plants_to_seed:
            pid = p["plant_id"]
            if pid in seen_pids:
                continue
            seen_pids.add(pid)

            pname = p["plant_name"]
            phone = phone_map.get(pname.strip().lower())
            
            # Format phone to E.164 if 10 digits
            formatted_phone = None
            if phone:
                clean_digits = "".join(filter(str.isdigit, phone))
                if len(clean_digits) == 10:
                    formatted_phone = f"+91{clean_digits}"
                elif len(clean_digits) == 12 and clean_digits.startswith("91"):
                    formatted_phone = f"+{clean_digits}"
                else:
                    formatted_phone = f"+{clean_digits}" if clean_digits else None

            # Customer name default: cleaned plant name if looks like a person's name
            c_name = pname
            opt_in = "active" if formatted_phone else "pending"

            cust = Customer(
                plant_id=pid,
                plant_name=pname,
                platform=p["platform"],
                customer_name=c_name,
                phone_number=formatted_phone,
                opt_in_status=opt_in,
                preferred_lang="english",
                notes=f"Auto-imported. Location: {p.get('city', '')}"
            )
            db.add(cust)
            inserted += 1

        db.commit()
        return inserted
    finally:
        db.close()
