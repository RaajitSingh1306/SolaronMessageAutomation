# 📲 Solaron Messaging Hub & WhatsApp CRM Engine

> 📖 **Master Project Guide**: For the full dual-dashboard documentation, see the root [README.md](../README.md).  
> For remaining deployment tasks and cloud guides, see [README_REMAINING_WORK.md](../README_REMAINING_WORK.md).

The **Solaron Messaging Hub** is an enterprise customer engagement and CRM platform built for **Solaron Homes Pvt Ltd**. It synchronizes solar generation data across ~485 plants spanning **Growatt ShineServer**, **Sungrow iSolarCloud**, and **SuryaLog Cloud**, maintains customer directory mappings, classifies plant performance into commercial marketing tiers, and delivers personalized WhatsApp billing statements, offline escalation alerts, and yearly milestone recaps via Playwright browser automation or cloud messaging APIs.

---

## 🏗️ System Architecture

```
Growatt ShineServer   +   Sungrow iSolarCloud   +   SuryaLog Cloud
   (REST API)               (Playwright XHR)         (Playwright DOM)
        |                          |                        |
        +--------------------------+------------------------+
                                   v
                             services/
                      fetcher_orchestrator.py   (multi-platform async fetch)
                      report.py                 (energy report builder)
                      classifier.py             (operational plant classifier)
                      scheduler.py              (APScheduler daily & monthly jobs)
                                   |
                                   v
                                crm/
                      models.py         (Customer, MessageQueue, CampaignLog, AlertSendLog)
                      db.py             (Dual SQLite & PostgreSQL connection pooler)
                      generator.py      (monthly statements + ratings integration)
                      queue_manager.py  (campaign preparation, health audit, dry-runs)
                      templates.py      (bilingual EN/HI/MR & rating-aware templates)
                      sender.py         (Playwright WhatsApp Web automation & API stubs)
                                   |
                                   v
                             routes/crm.py
             Full CRM REST API (18+ endpoints, drill-down, CSV exports)
                                   |
                                   v
                          FastAPI Web Portal
       Interactive CRM Dashboard (http://localhost:5000 / http://localhost:8001)
```

---

## 🌟 Key Features

### 1. Unified Customer Directory & Contact Management
- Maps all ~485 solar installations to customer identities, telephone numbers, language preferences (`english`, `hindi`, `marathi`), and opt-in states (`active`, `pending`, `do_not_send`).
- Search, filter by platform, filter by contact availability, and identify unmapped plants.
- Inline contact editing and bulk CSV import (`/api/crm/customers/import`).

### 2. Multi-Resolution Billing & Statement Generation
- **Monthly Statements**: Calculates total generation (kWh), monetary financial savings (₹ INR at local tariff), avoided carbon emissions (kg CO₂), and specific yield.
- **Cross-System Analytics Integration**: Reads directly from `solar_analytics.db` via `SOLAR_ANALYTICS_DB_PATH` or PostgreSQL `DATABASE_URL` with automatic graceful fallback.
- **Yearly Milestones**: Aggregates annual solar generation and translates kWh into "Days Powered" equivalents.

### 3. Rating-Driven Marketing & Tiered Messaging
- Integrates with the **Backend Dashboard Performance Classifier** (`/api/ratings/monthly/{month}`).
- Dynamically selects custom marketing copy and Call-To-Actions (CTAs) based on plant performance:
  - 🟢 **Best**: Congratulatory messaging, top percentile highlight, and referral discount offer.
  - 🔵 **Good**: Positive acknowledgment with seasonal panel cleaning maintenance tips.
  - 🟡 **Could Be Better**: Guidance on water rinsing and shadow/tree inspection to boost yields.
  - 🟠 **Needs Attention / Critical**: Urgent technical service advisory with direct support callback triggers.

### 4. Real-Time Offline Alerts & Anti-Spam Cooldown
- Identifies plants offline beyond a configurable threshold (e.g., 4 or 24 hours).
- **Cooldown Deduplication (`alert_send_log`)**: Tracks alert dispatches to prevent messaging the same customer repeatedly (24-hour cooldown for offline warnings, 6-hour cooldown for active hardware faults).
- Previews and prepares dedicated offline escalation campaigns.

### 5. Automated Campaign Lifecycle & Anti-Ban Controls
- Numbered campaign tracking (`CampaignLog`) with a robust state machine: `PENDING` ➔ `SENT` / `FAILED` / `SKIPPED` / `SIMULATED`.
- **Anti-Ban Controls**: Humanized randomized delay (12–16 seconds between messages) and automatic batch cooling pauses (120 seconds per 18 messages).
- Full console dry-run mode (`execute_campaign_dry_run`) and CSV export for external WhatsApp Business BSP ingestion (Gupshup / Freshworks / AiSensy).

### 6. Dual-Database Support (SQLite & PostgreSQL)
- **Local Dev**: Uses `data/crm_data.db`.
- **Production Cloud**: Configured via `DATABASE_URL` for **Supabase PostgreSQL** with connection pooling (`pool_size=5`, `max_overflow=10`, `pool_pre_ping=True`).

---

## 📁 Project Structure

```
Message Dashboard/
├── app.py                        # FastAPI application entry point, lifespan, static/template mounts
├── cli.py                        # Rich Click CLI for CRM initialization, campaigns, and dry runs
├── config.py                     # Pydantic-settings config (env-aware, frozen-exe safe, path validation)
├── database.py                   # Operational SQLite DB setup
├── helpers.py                    # Phone number normalizer, date helpers, string utilities
├── models.py                     # Operational fleet state models
├── state.py                      # In-memory fleet state singleton
├── crm/
│   ├── db.py                     # SQLAlchemy engine, session maker, dual SQLite/PostgreSQL
│   ├── models.py                 # Customer, MessageQueue, CampaignLog, AlertSendLog models
│   ├── generator.py              # Monthly/yearly statements & backend rating integration
│   ├── queue_manager.py          # Campaign preparation, health audit, dry-runs, exports
│   ├── templates.py              # Template engine (EN/HI/MR, monthly tiers, offline alerts)
│   └── sender.py                 # Playwright WhatsApp Web automation & Cloud API senders
├── routes/
│   ├── crm.py                    # Complete CRM REST API (18+ endpoints)
│   ├── fetch.py                  # Platform scraping trigger endpoints
│   ├── plants.py                 # Plant directory endpoints
│   ├── report.py                 # Energy report endpoints
│   ├── send.py                   # Playwright WhatsApp Web dispatch trigger
│   ├── upload.py                 # File upload endpoints
│   ├── diagnostics.py            # System health diagnostics
│   └── contacts.py               # Phone cache CRUD service
├── migrations/
│   └── add_alert_cooldown.sql    # DDL for alert_send_log cooldown table
├── services/
│   ├── fetcher_orchestrator.py   # Multi-platform async scraping coordinator
│   ├── scheduler.py              # APScheduler daily sync & monthly campaign automation
│   ├── classifier.py             # Operational plant status classifier
│   └── contacts.py               # Phone cache persistence service
├── templates/
│   └── dashboard.html            # Single-page web dashboard UI
├── data/
│   ├── crm_data.db               # SQLite CRM database (customers, queues, campaign logs)
│   └── exports/                  # Exported campaign CSV files
├── render.yaml                   # Cloud deployment definition for Render.com Starter plan
├── requirements.txt              # Python package dependencies
└── .env.example                  # Environment variable configuration template
```

---

## 🔌 Complete CRM REST API Reference

The CRM API is mounted at `/api/crm` and provides full programmatic access:

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/crm/health` | Returns customer count, phone coverage %, unmapped count, and opt-outs |
| `GET` | `/api/crm/customers` | Lists customers with pagination, platform filters, phone filters, and search |
| `POST`| `/api/crm/customers` | Registers a new customer or maps an unlinked solar plant |
| `POST`| `/api/crm/customers/{id}` | Updates customer phone number, name, opt-in status, or language |
| `POST`| `/api/crm/customers/import` | Bulk imports customer contacts and phone numbers from CSV |
| `GET` | `/api/crm/customers/export` | Downloads the customer directory as a CSV |
| `GET` | `/api/crm/customers/{id}/full-profile` | **Full Customer Profile**: contact info, message history, monthly generation, savings, and CO₂ totals |
| `GET` | `/api/crm/analytics/overview`| **Management Overview**: customer coverage %, delivery rates, platform distribution, recent campaigns |
| `GET` | `/api/crm/export/customers-full` | Detailed customer export with per-customer message delivery stats |
| `GET` | `/api/crm/export/campaign-performance` | Campaign performance CSV export with delivery rates |
| `GET` | `/api/crm/export/generation-by-customer` | Joins monthly generation from `solar_analytics.db` with CRM contacts |
| `GET` | `/api/crm/statements` | Generates monthly or yearly statements with total kWh and savings |
| `POST`| `/api/crm/campaigns/prepare` | Prepares a monthly WhatsApp campaign and queues messages in DB |
| `POST`| `/api/crm/campaigns/prepare-yearly` | Prepares an annual milestone campaign and queues messages |
| `GET` | `/api/crm/campaigns` | Lists all past campaigns with queued, sent, and failed tallies |
| `GET` | `/api/crm/campaigns/{id}` | Retrieves campaign details and individual message queues |
| `POST`| `/api/crm/campaigns/{id}/dry-run` | Simulates sending all pending messages to the console |
| `POST`| `/api/crm/campaigns/{id}/export` | Exports campaign messages and phone numbers to a downloadable CSV |
| `GET` | `/api/crm/offline` | Lists plants offline > threshold hours from inverter snapshots |
| `POST`| `/api/crm/offline/prepare-alerts` | Prepares an urgent offline alert campaign with cooldown filtering |

---

## 💬 WhatsApp Message Templates Catalog

Located in `crm/templates.py`, all templates support dynamic interpolation (`{customer_name}`, `{plant_name}`, `{generation_kwh}`, `{savings_inr}`, `{co2_saved_kg}`, `{support_phone}`):

| Template ID | Scenario / Trigger | Supported Languages | Marketing Focus |
| :--- | :--- | :--- | :--- |
| `monthly_standard` | Standard monthly billing statement | English, Hindi, Marathi | Clean energy yield, ₹ savings, CO₂ offsets |
| `monthly_best` | Plant in Top 20% (Best tier) | English, Hindi, Marathi | High praise, 🏆 badge, referral discount CTA |
| `monthly_good` | Plant in 55th–80th percentile | English, Hindi, Marathi | Solid performance, seasonal cleaning tips |
| `monthly_could_better` | Plant in 30th–55th percentile | English, Hindi, Marathi | Mild deficit alert, shading/dust inspection |
| `monthly_needs_attention`| Plant in Bottom 30% / Critical | English, Hindi, Marathi | 🚨 Urgent service advisory, callback request |
| `offline_alert` | Plant offline > threshold hours | English, Hindi | ⚠️ Outage alert, technician notification |
| `yearly_milestone` | Annual generation recap | English, Hindi | 🎉 Annual kWh, equivalent "Days Powered" |

---

## 🚀 Quick Start & CLI Reference

### 1. Installation
```powershell
cd "c:\Users\raaji\Downloads\Solaron\Message Dashboard"
pip install -r requirements.txt
playwright install chromium
```

### 2. Launch the Application
```powershell
# Run with Python
python app.py

# Or run with Uvicorn
python -m uvicorn app:app --host 127.0.0.1 --port 5000
```
Open **[http://127.0.0.1:5000/](http://127.0.0.1:5000/)** in your browser.

### 3. CRM CLI Operations
```powershell
# Initialize CRM database and seed contacts
python cli.py crm init

# Check data health audit
python cli.py crm health

# Prepare campaign for June 2026
python cli.py crm prepare-campaign --month 2026-06

# Execute console dry run preview (no messages sent)
python cli.py crm dry-run

# Export campaign messages to CSV for Gupshup/Freshworks
python cli.py crm export

# List offline installations
python cli.py crm offline --threshold 24
```

---

## 🧪 Testing & Verification

Run the master verification test:
```powershell
cd "c:\Users\raaji\Downloads\Solaron"
python verify_all.py
```
*Result: Validates CRM directory seeding, template rendering across EN/HI/MR, monthly & yearly calculations, campaign preparation lifecycle, dry-run simulation, and all FastAPI routes.*
