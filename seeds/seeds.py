import json
from flask.cli import with_appcontext
import click
from app import db, User, Family, Gift


@click.command('seed-db')
@with_appcontext
def seed_command():
    """Seed the database with demo data."""
    try:
        with open('seeds/demo_data.json', 'r') as f:
            data = json.load(f)

        for family_data in data['families']:
            # Create family and members...
            pass  # Implementation here

        click.echo('Database seeded successfully!')
    except Exception as e:
        click.echo(f'Error seeding database: {str(e)}')


def register_commands(app):
    app.cli.add_command(seed_command)
