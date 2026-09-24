import click
from flask.cli import with_appcontext


@click.command('send-daily-reports')
@with_appcontext
def send_daily_reports():
    """Send every daily WhatsApp report that's due. Run on a schedule
    (every ~15 min) — see render.yaml."""
    from app.core.daily_report import run_due_reports
    results = run_due_reports()
    if not results:
        click.echo("Nothing due.")
    for line in results:
        click.echo(line)


def register_cli(app):
    app.cli.add_command(send_daily_reports)
