"""Seed demo data reproducibly.

Usage:
    python manage.py seed_demo

Reads demo credentials from the environment (supplied by the evaluator):
    EVAL_ADMIN_USERNAME / EVAL_ADMIN_PASSWORD
    EVAL_AUDITOR_USERNAME / EVAL_AUDITOR_PASSWORD
    EVAL_TECHNICIAN_USERNAME / EVAL_TECHNICIAN_PASSWORD

When an env var is absent, the local-dev default is used: the demo
username (demo_admin / demo_auditor / demo_technician) as both username
and password. These defaults are for local development ONLY and must
never be used for the hosted demo -- the evaluator supplies real,
distinct passwords for hosted accounts.

Idempotent: running twice never duplicates users, locations, the shuttle,
snapshots or sample pallets, and never deletes non-demo data. Existing
demo users are updated in place (password + role), so re-running the
seed after the evaluator changes EVAL_* values applies the new password.
"""
import os
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from warehouse.models import Location, OccupancySnapshot, Pallet, Profile, Shuttle

# Fixed deterministic history for the 6 days before today (occupied counts
# out of 24 storage locations). No randomness, no dependence on wall-clock
# time beyond the calendar date itself. Today's row is set to the actual
# current stocked count after the sample pallets are seeded, so the chart's
# last point always agrees with the live dashboard.
PAST_OCCUPIED = [2, 4, 3, 5, 4, 6]

SAMPLE_PALLETS = [
    # (pallet_number, barcode, item, quantity, location_code)
    ("PLT-1001", "BC-1001", "Cardboard Boxes", 120, "B2"),
    ("PLT-1002", "BC-1002", "Bottled Water", 48, "C3"),
    ("PLT-1003", "BC-1003", "Spare Parts Kit", 25, "D1"),
    ("PLT-1004", "BC-1004", "Office Chairs", 10, "E4"),
    ("PLT-1005", "BC-1005", "Paper Reams", 200, "A3"),
]

DEMO_ACCOUNTS = [
    ("EVAL_ADMIN_USERNAME", "EVAL_ADMIN_PASSWORD", "demo_admin", Profile.ROLE_ADMIN),
    ("EVAL_AUDITOR_USERNAME", "EVAL_AUDITOR_PASSWORD", "demo_auditor", Profile.ROLE_AUDITOR),
    ("EVAL_TECHNICIAN_USERNAME", "EVAL_TECHNICIAN_PASSWORD", "demo_technician", Profile.ROLE_TECHNICIAN),
]


class Command(BaseCommand):
    help = "Seed demo users, locations, shuttle, history and sample pallets (idempotent)."

    def handle(self, *args, **options):
        # 1. Locations: 25 cells, A1..E5. A1 is the transfer point.
        for col in "ABCDE":
            for row in range(1, 6):
                code = f"{col}{row}"
                Location.objects.update_or_create(
                    code=code, defaults={"is_transfer_point": code == "A1"}
                )
        self.stdout.write("Locations: 25 (A1 transfer point, 24 storage).")

        # 2. Shuttle (single row; created once, never overwritten).
        Shuttle.objects.get_or_create(
            identifier="SH-01", defaults={"status": "idle", "battery_percent": 87}
        )
        self.stdout.write("Shuttle: SH-01 (idle, 87%).")

        # 3. Sample pallets (created only if the pallet number is absent).
        locations = {loc.code: loc for loc in Location.objects.all()}
        created = 0
        for number, barcode, item, qty, code in SAMPLE_PALLETS:
            _, was_created = Pallet.objects.get_or_create(
                pallet_number=number,
                defaults={
                    "barcode": barcode,
                    "item": item,
                    "quantity": qty,
                    "location": locations[code],
                },
            )
            created += int(was_created)
        self.stdout.write(f"Sample pallets: {created} created, 5 total expected.")

        # 4. Occupancy history: 7 days ending today.
        today = date.today()
        for i, occupied in enumerate(PAST_OCCUPIED):
            day = today - timedelta(days=6 - i)
            OccupancySnapshot.objects.update_or_create(
                date=day,
                defaults={"occupied": occupied, "free": 24 - occupied},
            )
        stocked = Pallet.objects.filter(location__isnull=False).count()
        OccupancySnapshot.objects.update_or_create(
            date=today, defaults={"occupied": stocked, "free": 24 - stocked}
        )
        self.stdout.write(
            f"Occupancy history: 7 days ending {today} (today: {stocked} occupied)."
        )

        # 5. Demo accounts (create or update in place; never duplicated).
        for user_env, pass_env, default_name, role in DEMO_ACCOUNTS:
            username = os.environ.get(user_env) or default_name
            password = os.environ.get(pass_env) or default_name
            user, _ = User.objects.update_or_create(username=username, defaults={})
            user.set_password(password)
            user.is_active = True
            user.save()
            Profile.objects.update_or_create(user=user, defaults={"role": role})
            self.stdout.write(f"Demo user: {username} ({role}).")

        self.stdout.write(self.style.SUCCESS("Seed complete."))
