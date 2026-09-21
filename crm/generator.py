"""
Solaron CRM Statement Generator
Joins customers (crm_data.db) with generation records (solar_analytics.db / solaron.db)
to generate CustomerMonthlyStatement and yearly milestone datasets.
"""

import os
import json
import sqlite3
import calendar
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Dict, Any, Optional

from config import Config
from .db import CRMSessionLocal
from .models import Customer, MessageQueue


@dataclass
class CustomerMonthlyStatement:
    customer_name: str
    plant_name: str
    plant_id: str
    platform: str
    phone_number: Optional[str]
    opt_in_status: str
    preferred_lang: str
    month_year: str          # "YYYY-MM"
    generation_kwh: float
    savings_inr: float       # generation_kwh × PRICE_PER_UNIT_INR
    co2_saved_kg: float      # generation_kwh × CO2_FACTOR_KG_PER_KWH
    days_in_month: int
    avg_daily_kwh: float
    plant_capacity_kwp: float
    specific_yield: float    # generation_kwh / capacity_kwp
    is_missing_phone: bool
    is_opted_out: bool = False
    customer_id: Optional[int] = None
    message_status: str = "Not Queued"
    performance_rating: Optional[str] = None
    marketing_cta: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _get_analytics_conn():
    """
    Returns a database connection to solar analytics:
    PostgreSQL if DATABASE_URL configured, else read-only SQLite connection.
    """
    db_url = getattr(Config, "DATABASE_URL", None) or os.getenv("DATABASE_URL", "")
    if db_url and (db_url.startswith("postgresql://") or db_url.startswith("postgres://")):
        try:
            import psycopg2
            return psycopg2.connect(db_url)
        except Exception:
            pass

    path = Config.ANALYTICS_DB_PATH
    if path and os.path.exists(path):
        try:
            return sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        except Exception:
            return sqlite3.connect(path)
    return None


def _get_all_monthly_ratings(month_str: str) -> Dict[str, Dict[str, Any]]:
    """Fetch all plant ratings for month_str from Backend Dashboard or direct fallback."""
    backend_url = os.getenv("BACKEND_DASHBOARD_URL", "http://127.0.0.1:8765")
    ratings_map = {}
    try:
        import urllib.request
        import json
        url = f"{backend_url}/api/ratings/monthly/{month_str}"
        req = urllib.request.Request(url, headers={"User-Agent": "Solaron-CRM"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                for r in data.get("ratings", []):
                    key = str(r.get("plant_name", "")).strip().lower()
                    ratings_map[key] = r
                return ratings_map
    except Exception:
        pass

    # Direct calculation fallback from solar_analytics.db
    try:
        analytics_db_path = Config.ANALYTICS_DB_PATH
        if analytics_db_path and os.path.exists(analytics_db_path):
            conn = sqlite3.connect(analytics_db_path)
            cur = conn.cursor()
            cur.execute("SELECT plant_name, specific_yield_kwh_kwp FROM monthly_generation WHERE month = ?", (month_str,))
            rows = cur.fetchall()
            conn.close()
            if rows:
                sys_vals = [float(r[1] or 0.0) for r in rows if r[1] is not None and float(r[1] or 0.0) > 0]
                med = sorted(sys_vals)[len(sys_vals)//2] if sys_vals else 25.0
                for pname, sy in rows:
                    sy_val = float(sy or 0.0)
                    key = str(pname).strip().lower()
                    if sy_val <= 0:
                        rating = "Critical — Act Now"
                        cta = "🚨 Your plant is critically underperforming. Please call us."
                    elif sy_val >= med * 1.15:
                        rating = "Best"
                        cta = "🌟 Your plant is performing excellently. Share the good news!"
                    elif sy_val >= med * 0.95:
                        rating = "Good"
                        cta = "✅ Your plant is doing well. Minor optimizations possible."
                    elif sy_val >= med * 0.70:
                        rating = "Could Be Better"
                        cta = "📊 Your plant is below average. A cleaning may help."
                    else:
                        rating = "Needs Attention"
                        cta = "⚠️ Your plant needs attention. Consider a service visit."
                    ratings_map[key] = {
                        "rating": rating,
                        "specific_yield": sy_val,
                        "marketing_cta": cta
                    }
    except Exception:
        pass

    return ratings_map


def get_monthly_statements(year: int, month: int) -> List[CustomerMonthlyStatement]:
    """
    Joins customers (crm_data.db) with monthly_generation (solar_analytics.db).
    Falls back to solaron.db if solar_analytics.db is unavailable.
    Returns one statement per plant/customer for the given month.
    """
    month_str = f"{year:04d}-{month:02d}"
    days_in_month = calendar.monthrange(year, month)[1]

    # 1. Fetch CRM customers
    crm_db = CRMSessionLocal()
    try:
        customers_list = crm_db.query(Customer).all()
        # Map by plant_id and normalized plant_name
        cust_by_id = {c.plant_id: c for c in customers_list}
        cust_by_name = {c.plant_name.strip().lower(): c for c in customers_list if c.plant_name}

        # 2. Fetch existing queued messages for this month to report message_status
        existing_msgs = crm_db.query(MessageQueue).filter(MessageQueue.month_year == month_str).all()
        status_by_cust = {m.customer_id: m.status for m in existing_msgs if m.customer_id}
        status_by_phone = {m.phone_number: m.status for m in existing_msgs if m.phone_number}
    finally:
        crm_db.close()

    statements: List[CustomerMonthlyStatement] = []
    processed_plant_ids = set()

    # 3. Read from solar_analytics.db
    analytics_conn = _get_analytics_conn()
    gen_records = []
    metadata_map = {}

    if analytics_conn:
        try:
            cur = analytics_conn.cursor()
            # Fetch plants_metadata
            cur.execute("SELECT plant_id, plant_name, source, capacity_kwp, city FROM plants_metadata")
            for r in cur.fetchall():
                pid, pname, src, cap, city = r
                metadata_map[pname.strip().lower()] = {
                    "plant_id": str(pid),
                    "plant_name": pname,
                    "platform": src or "growatt",
                    "capacity_kwp": float(cap or 0.0),
                    "city": city or ""
                }

            # Fetch monthly generation for month_str
            cur.execute("""
                SELECT plant_name, source, capacity_kwp, energy_kwh, avg_daily_kwh, specific_yield_kwh_kwp
                FROM monthly_generation
                WHERE month = ?
            """, (month_str,))
            for r in cur.fetchall():
                pname, src, cap, kwh, avg_daily, spec_yield = r
                gen_records.append({
                    "plant_name": pname,
                    "platform": src,
                    "capacity_kwp": float(cap or 0.0),
                    "energy_kwh": float(kwh or 0.0),
                    "avg_daily_kwh": float(avg_daily or 0.0),
                    "specific_yield": float(spec_yield or 0.0),
                })
        except Exception as e:
            gen_records = []
        finally:
            analytics_conn.close()

    # 4. Fallback to solaron.db if no records found in solar_analytics.db
    if not gen_records:
        solaron_db_path = os.path.join(Config.DATA_FOLDER, "solaron.db")
        if os.path.exists(solaron_db_path):
            try:
                conn = sqlite3.connect(solaron_db_path)
                cur = conn.cursor()
                cur.execute("SELECT platform, records_json FROM monthly_generation WHERE month = ?", (month_str,))
                for src, r_json in cur.fetchall():
                    if r_json:
                        try:
                            items = json.loads(r_json)
                            for it in items:
                                pname = it.get("plant_name", "")
                                kwh = float(it.get("energy_kwh", 0.0) or 0.0)
                                cap = float(it.get("capacity_kwp", 0.0) or 0.0)
                                gen_records.append({
                                    "plant_name": pname,
                                    "platform": src,
                                    "capacity_kwp": cap,
                                    "energy_kwh": kwh,
                                    "avg_daily_kwh": round(kwh / days_in_month, 2) if days_in_month else 0.0,
                                    "specific_yield": round(kwh / cap, 2) if cap > 0 else 0.0,
                                })
                        except Exception:
                            pass
                conn.close()
            except Exception:
                pass

    # 5. Retrieve performance ratings map for this month
    ratings_map = _get_all_monthly_ratings(month_str)

    # Process generation records
    for g in gen_records:
        pname = g["plant_name"]
        norm_name = pname.strip().lower()
        meta = metadata_map.get(norm_name, {})
        plant_id = meta.get("plant_id", norm_name)
        platform = g.get("platform") or meta.get("platform", "growatt")
        capacity = g.get("capacity_kwp") or meta.get("capacity_kwp", 0.0)
        kwh = g.get("energy_kwh", 0.0)

        # Match customer
        cust = cust_by_id.get(plant_id) or cust_by_name.get(norm_name)

        customer_id = cust.customer_id if cust else None
        customer_name = cust.customer_name if cust and cust.customer_name else "UNMAPPED"
        phone = cust.phone_number if cust else None
        opt_in = cust.opt_in_status if cust else "pending"
        lang = cust.preferred_lang if cust else "english"

        # Financials
        savings_inr = round(kwh * Config.PRICE_PER_UNIT_INR, 2)
        co2_saved_kg = round(kwh * Config.CO2_FACTOR_KG_PER_KWH, 2)
        avg_daily = round(kwh / days_in_month, 2) if days_in_month > 0 else 0.0
        specific_yield = round(kwh / capacity, 2) if capacity > 0 else 0.0

        is_missing_phone = not bool(phone and phone.strip())
        is_opted_out = (opt_in == "do_not_send")

        # Determine message status
        msg_status = "Not Queued"
        if customer_id and customer_id in status_by_cust:
            msg_status = status_by_cust[customer_id]
        elif phone and phone in status_by_phone:
            msg_status = status_by_phone[phone]
        elif is_opted_out:
            msg_status = "Opted Out"
        elif is_missing_phone:
            msg_status = "No Phone"

        rating_data = ratings_map.get(norm_name, {})
        stmt = CustomerMonthlyStatement(
            customer_id=customer_id,
            customer_name=customer_name,
            plant_name=pname,
            plant_id=plant_id,
            platform=platform,
            phone_number=phone,
            opt_in_status=opt_in,
            preferred_lang=lang,
            month_year=month_str,
            generation_kwh=kwh,
            savings_inr=savings_inr,
            co2_saved_kg=co2_saved_kg,
            days_in_month=days_in_month,
            avg_daily_kwh=avg_daily,
            plant_capacity_kwp=capacity,
            specific_yield=specific_yield,
            is_missing_phone=is_missing_phone,
            is_opted_out=is_opted_out,
            message_status=msg_status,
            performance_rating=rating_data.get("rating"),
            marketing_cta=rating_data.get("marketing_cta")
        )
        statements.append(stmt)
        processed_plant_ids.add(plant_id)

    # 6. Also include known customers who had 0 or missing generation records this month
    for c in customers_list:
        if c.plant_id not in processed_plant_ids:
            is_missing_phone = not bool(c.phone_number and c.phone_number.strip())
            is_opted_out = (c.opt_in_status == "do_not_send")
            msg_status = "Not Queued"
            if c.customer_id in status_by_cust:
                msg_status = status_by_cust[c.customer_id]
            elif is_opted_out:
                msg_status = "Opted Out"
            elif is_missing_phone:
                msg_status = "No Phone"

            stmt = CustomerMonthlyStatement(
                customer_id=c.customer_id,
                customer_name=c.customer_name or "UNMAPPED",
                plant_name=c.plant_name or f"Plant-{c.plant_id}",
                plant_id=c.plant_id,
                platform=c.platform or "growatt",
                phone_number=c.phone_number,
                opt_in_status=c.opt_in_status or "pending",
                preferred_lang=c.preferred_lang or "english",
                month_year=month_str,
                generation_kwh=0.0,
                savings_inr=0.0,
                co2_saved_kg=0.0,
                days_in_month=days_in_month,
                avg_daily_kwh=0.0,
                plant_capacity_kwp=0.0,
                specific_yield=0.0,
                is_missing_phone=is_missing_phone,
                is_opted_out=is_opted_out,
                message_status=msg_status,
                performance_rating="Critical — Act Now",
                marketing_cta="🚨 Your plant is critically underperforming. Please call us."
            )
            statements.append(stmt)

    # Sort statements: active with generation first, then alphabetical
    statements.sort(key=lambda s: (-s.generation_kwh, s.customer_name))
    return statements


def get_yearly_statements(year: int) -> List[Dict[str, Any]]:
    """
    Returns yearly milestone summaries per customer for a given year.
    Calculates total_kwh, total_savings, best month, and days_powered.
    Aggregates from yearly_generation and monthly_generation in solar_analytics.db.
    Includes all registered customers (filling with 0 if no generation recorded).
    """
    crm_db = CRMSessionLocal()
    try:
        customers = crm_db.query(Customer).all()
        cust_map = {c.plant_name.strip().lower(): c for c in customers if c.plant_name}
        cust_id_map = {c.plant_id: c for c in customers}
    finally:
        crm_db.close()

    results: List[Dict[str, Any]] = []
    seen_plant_names = set()
    analytics_conn = _get_analytics_conn()

    if analytics_conn:
        try:
            cur = analytics_conn.cursor()

            # 1. Best month per plant from monthly_generation
            cur.execute("""
                SELECT plant_name, month, MAX(energy_kwh)
                FROM monthly_generation
                WHERE month LIKE ?
                GROUP BY plant_name
            """, (f"{year}-%",))
            best_months = {r[0].strip().lower(): (r[1], float(r[2] or 0.0)) for r in cur.fetchall()}

            # 2. Fetch explicit yearly generation records if available
            cur.execute("""
                SELECT plant_name, source, capacity_kwp, energy_kwh, avg_monthly_kwh, specific_yield_kwh_kwp
                FROM yearly_generation
                WHERE year = ?
            """, (str(year),))
            rows = cur.fetchall()

            for r in rows:
                pname, src, cap, kwh, avg_m, spec_yield = r
                norm_name = pname.strip().lower()
                seen_plant_names.add(norm_name)
                cust = cust_map.get(norm_name)

                total_kwh = float(kwh or 0.0)
                savings = round(total_kwh * Config.PRICE_PER_UNIT_INR, 2)
                days_powered = round(total_kwh / Config.AVG_HOUSEHOLD_KWH_PER_DAY, 1)

                best_m_info = best_months.get(norm_name, ("N/A", 0.0))
                best_month_label = f"{best_m_info[0]} ({best_m_info[1]:.0f} kWh)" if best_m_info[0] != "N/A" else "N/A"

                results.append({
                    "customer_id": cust.customer_id if cust else None,
                    "customer_name": cust.customer_name if cust else "UNMAPPED",
                    "plant_name": pname,
                    "platform": src,
                    "phone_number": cust.phone_number if cust else None,
                    "opt_in_status": cust.opt_in_status if cust else "pending",
                    "preferred_lang": cust.preferred_lang if cust else "english",
                    "year": year,
                    "total_kwh": total_kwh,
                    "total_savings": savings,
                    "best_month": best_month_label,
                    "days_powered": days_powered,
                    "capacity_kwp": float(cap or 0.0),
                })

            # 3. Aggregate monthly_generation for any plants not in yearly_generation
            cur.execute("""
                SELECT plant_name, source, capacity_kwp, SUM(energy_kwh) as tot_kwh, AVG(energy_kwh) as avg_m
                FROM monthly_generation
                WHERE month LIKE ?
                GROUP BY plant_name
            """, (f"{year}-%",))
            for pname, src, cap, kwh, avg_m in cur.fetchall():
                norm_name = pname.strip().lower()
                if norm_name in seen_plant_names:
                    continue
                seen_plant_names.add(norm_name)
                cust = cust_map.get(norm_name)

                total_kwh = float(kwh or 0.0)
                savings = round(total_kwh * Config.PRICE_PER_UNIT_INR, 2)
                days_powered = round(total_kwh / Config.AVG_HOUSEHOLD_KWH_PER_DAY, 1)

                best_m_info = best_months.get(norm_name, ("N/A", 0.0))
                best_month_label = f"{best_m_info[0]} ({best_m_info[1]:.0f} kWh)" if best_m_info[0] != "N/A" else "N/A"

                results.append({
                    "customer_id": cust.customer_id if cust else None,
                    "customer_name": cust.customer_name if cust else "UNMAPPED",
                    "plant_name": pname,
                    "platform": src,
                    "phone_number": cust.phone_number if cust else None,
                    "opt_in_status": cust.opt_in_status if cust else "pending",
                    "preferred_lang": cust.preferred_lang if cust else "english",
                    "year": year,
                    "total_kwh": total_kwh,
                    "total_savings": savings,
                    "best_month": best_month_label,
                    "days_powered": days_powered,
                    "capacity_kwp": float(cap or 0.0),
                })
        except Exception:
            pass
        finally:
            analytics_conn.close()

    # 4. Also include registered customers who had 0 or missing records for this year
    for c in customers:
        norm = c.plant_name.strip().lower() if c.plant_name else ""
        if norm and norm not in seen_plant_names:
            results.append({
                "customer_id": c.customer_id,
                "customer_name": c.customer_name or "UNMAPPED",
                "plant_name": c.plant_name or f"Plant-{c.plant_id}",
                "platform": c.platform or "growatt",
                "phone_number": c.phone_number,
                "opt_in_status": c.opt_in_status or "pending",
                "preferred_lang": c.preferred_lang or "english",
                "year": year,
                "total_kwh": 0.0,
                "total_savings": 0.0,
                "best_month": "N/A",
                "days_powered": 0.0,
                "capacity_kwp": 0.0,
            })
            seen_plant_names.add(norm)

    results.sort(key=lambda x: (-x["total_kwh"], x["customer_name"]))
    return results


def get_unmapped_plants() -> List[Dict[str, Any]]:
    """
    Returns list of plants in metadata that have no customer record in crm_data.db.
    """
    crm_db = CRMSessionLocal()
    try:
        known_plant_ids = {c.plant_id for c in crm_db.query(Customer.plant_id).all()}
        known_names = {c.plant_name.strip().lower() for c in crm_db.query(Customer.plant_name).all() if c.plant_name}
    finally:
        crm_db.close()

    unmapped = []
    analytics_conn = _get_analytics_conn()

    if analytics_conn:
        try:
            cur = analytics_conn.cursor()
            cur.execute("SELECT plant_id, plant_name, source, capacity_kwp, city FROM plants_metadata")
            for pid, pname, src, cap, city in cur.fetchall():
                pid_str = str(pid)
                if pid_str not in known_plant_ids and pname.strip().lower() not in known_names:
                    unmapped.append({
                        "plant_id": pid_str,
                        "plant_name": pname,
                        "platform": src or "growatt",
                        "capacity_kwp": float(cap or 0.0),
                        "city": city or ""
                    })
        finally:
            analytics_conn.close()

    return unmapped


def get_offline_plants(threshold_hours: float = 24.0) -> List[Dict[str, Any]]:
    """
    Reads inverter_snapshots from solar_analytics.db to identify plants offline > threshold_hours.
    Matches with CRM customer contact details.
    """
    crm_db = CRMSessionLocal()
    try:
        customers = crm_db.query(Customer).all()
        cust_by_name = {c.plant_name.strip().lower(): c for c in customers if c.plant_name}
    finally:
        crm_db.close()

    offline_list = []
    analytics_conn = _get_analytics_conn()

    if analytics_conn:
        try:
            cur = analytics_conn.cursor()
            # Fetch latest snapshot per plant
            cur.execute("""
                SELECT plant_name, source, device_status, timestamp, pac_total_w, last_update_time
                FROM inverter_snapshots
                ORDER BY timestamp DESC
            """)
            seen_plants = set()
            now = datetime.now()

            for pname, src, status, ts_str, pac, last_up in cur.fetchall():
                norm = pname.strip().lower()
                if norm in seen_plants:
                    continue
                seen_plants.add(norm)

                # Parse timestamp safely (support naive and timezone-aware)
                ts = None
                raw_time = last_up or ts_str
                if raw_time:
                    try:
                        ts = datetime.fromisoformat(raw_time.replace("Z", ""))
                        if ts.tzinfo is not None:
                            ts = ts.replace(tzinfo=None)
                    except Exception:
                        pass

                hours_offline = 0.0
                if ts:
                    delta = now - ts
                    hours_offline = max(0.0, delta.total_seconds() / 3600.0)
                else:
                    hours_offline = 999.0

                is_status_offline = (status and status.lower() in ("offline", "disconnected", "fault", "0"))

                if is_status_offline or hours_offline >= threshold_hours:
                    cust = cust_by_name.get(norm)
                    offline_list.append({
                        "plant_name": pname,
                        "platform": src,
                        "customer_id": cust.customer_id if cust else None,
                        "customer_name": cust.customer_name if cust else "UNMAPPED",
                        "phone_number": cust.phone_number if cust else None,
                        "opt_in_status": cust.opt_in_status if cust else "pending",
                        "preferred_lang": cust.preferred_lang if cust else "english",
                        "device_status": status or "offline",
                        "last_update": raw_time or "Unknown",
                        "hours_offline": round(hours_offline, 1),
                        "pac_w": float(pac or 0.0),
                        "alert_status": "Queued" if (cust and cust.phone_number) else "No Customer / Phone"
                    })
        finally:
            analytics_conn.close()

    offline_list.sort(key=lambda x: -x["hours_offline"])
    return offline_list
