"""
Solaron Messaging Hub & CRM CLI
Entry point for managing customer directory, monthly campaigns, dry-runs, and exports.
"""

import sys
from datetime import datetime
import click

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from crm.db import init_crm_db
from crm.queue_manager import (
    seed_customers_from_phone_cache,
    prepare_campaign,
    execute_campaign_dry_run,
    export_campaign_csv,
    get_data_health,
)
from crm.generator import get_monthly_statements, get_offline_plants


@click.group()
def cli():
    """Solaron Messaging & Customer Engagement Hub CLI."""
    pass


@cli.group("crm")
def crm_group():
    """CRM and Campaign commands."""
    pass


@crm_group.command("init")
def crm_init_cmd():
    """Initialize crm_data.db and seed customer directory."""
    init_crm_db()
    count = seed_customers_from_phone_cache()
    health = get_data_health()
    click.echo(f"CRM Initialized. Total customers: {health['total_customers']} (Newly Seeded: {count})")
    click.echo(f"Ready to message: {health['ready_to_message']}, Missing phone: {health['missing_phones']}")


@crm_group.command("health")
def crm_health_cmd():
    """Display current CRM Data Health audit."""
    init_crm_db()
    health = get_data_health()
    click.echo("\n" + "=" * 45)
    click.echo("       SOLARON CRM DATA HEALTH")
    click.echo("=" * 45)
    click.echo(f"  Total Customers:         {health['total_customers']}")
    click.echo(f"  Ready to message:        {health['ready_to_message']}")
    click.echo(f"  Missing phone numbers:   {health['missing_phones']}")
    click.echo(f"  Opted out (do_not_send): {health['opted_out']}")
    click.echo(f"  Unmapped Plants:         {health['unmapped_plants']}")
    click.echo(f"  Total Actionable Issues: {health['total_issues']}")
    click.echo("=" * 45 + "\n")


@crm_group.command("prepare-campaign")
@click.option("--month", type=str, default=None, help="Campaign month in YYYY-MM format")
def prepare_campaign_cmd(month):
    """Generate monthly statements and queue messages in crm_data.db."""
    init_crm_db()
    seed_customers_from_phone_cache()
    if not month:
        now = datetime.now()
        y, m = now.year, now.month
    else:
        parts = month.split("-")
        y, m = int(parts[0]), int(parts[1])

    res = prepare_campaign(y, m)
    click.echo(f"Campaign #{res['campaign_id']} created: {res['campaign_name']}")
    click.echo(f"Total Statements: {res['total_statements']}")
    click.echo(f"Messages Queued:  {res['queued']}")
    click.echo(f"Messages Skipped: {res['skipped']}")


@crm_group.command("dry-run")
@click.option("--campaign-id", type=int, default=None, help="Campaign ID to simulate (defaults to latest)")
def dry_run_cmd(campaign_id):
    """Run console dry-run for pending messages in campaign."""
    init_crm_db()
    from crm.db import CRMSessionLocal
    from crm.models import CampaignLog

    if not campaign_id:
        db = CRMSessionLocal()
        latest = db.query(CampaignLog).order_by(CampaignLog.campaign_id.desc()).first()
        db.close()
        if not latest:
            click.echo("No campaigns found. Run 'prepare-campaign' first.")
            return
        campaign_id = latest.campaign_id

    click.echo(f"Starting dry-run for Campaign #{campaign_id}...")
    res = execute_campaign_dry_run(campaign_id)
    click.echo(f"Simulated {res['simulated_count']} messages successfully.")


@crm_group.command("export")
@click.option("--campaign-id", type=int, default=None, help="Campaign ID to export (defaults to latest)")
def export_cmd(campaign_id):
    """Export campaign messages to CSV for manual WhatsApp dispatch."""
    init_crm_db()
    from crm.db import CRMSessionLocal
    from crm.models import CampaignLog

    if not campaign_id:
        db = CRMSessionLocal()
        latest = db.query(CampaignLog).order_by(CampaignLog.campaign_id.desc()).first()
        db.close()
        if not latest:
            click.echo("No campaigns found. Run 'prepare-campaign' first.")
            return
        campaign_id = latest.campaign_id

    csv_path = export_campaign_csv(campaign_id)
    click.echo(f"Exported campaign #{campaign_id} to:\n{csv_path}")


@crm_group.command("offline")
@click.option("--threshold", type=float, default=24.0, help="Offline hours threshold")
def offline_cmd(threshold):
    """List plants offline longer than threshold."""
    plants = get_offline_plants(threshold)
    click.echo(f"\nFound {len(plants)} plants offline > {threshold}h:")
    for p in plants[:15]:
        click.echo(f"  - {p['plant_name']} ({p['platform']}): {p['hours_offline']}h offline | Customer: {p['customer_name']} | Phone: {p['phone_number']}")
    if len(plants) > 15:
        click.echo(f"  ... and {len(plants) - 15} more.")


@cli.command("run")
@click.option("--host", default="127.0.0.1", help="Host address")
@click.option("--port", default=5000, help="Port number")
def run_app_cmd(host, port):
    """Run the Solaron Messaging Hub web dashboard."""
    from app import run_server
    run_server(host=host, port=port)


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "crm":
        # If 'python cli.py crm' is run without subcommands, run server or display help
        from app import run_server
        run_server()
    else:
        cli()
