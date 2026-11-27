"""Models for the Warehouse Management System.

Grid: columns A-E x rows 1-5 = 25 locations (A1..E5). A1 is the transfer
point; the other 24 are storage locations, each holding at most one pallet.
Occupancy is derived from the Pallet -> Location relation, never stored
separately on Location.
"""
from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Location(models.Model):
    """One cell of the 5x5 warehouse grid."""

    code = models.CharField(max_length=3, unique=True)
    is_transfer_point = models.BooleanField(default=False)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.code

    @property
    def pallet(self):
        """The pallet currently stored here, or None (one pallet max)."""
        return self.pallets.filter(location=self).first()

    @property
    def occupied(self):
        return self.pallet is not None


class Pallet(models.Model):
    """A pallet. ``location=None`` means unloaded / removed from stock.

    The row is kept after unload for history; it is never deleted.
    ``pallet_number`` is unique across all time (never reused), so a number
    that was ever loaded cannot be loaded again.
    """

    pallet_number = models.CharField(max_length=64, unique=True)
    barcode = models.CharField(max_length=128)
    item = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    location = models.ForeignKey(
        Location,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pallets",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pallet_number} ({self.item})"

    @property
    def in_stock(self):
        return self.location_id is not None


class Shuttle(models.Model):
    """The single warehouse shuttle. Status/battery are stored in the DB."""

    identifier = models.CharField(max_length=32, unique=True)
    status = models.CharField(max_length=32, default="idle")
    battery_percent = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )

    def __str__(self):
        return self.identifier


class OccupancySnapshot(models.Model):
    """One day's occupied/free storage counts (24 storage locations total).

    History is sample data: the past 6 days are fixed deterministic values
    (see the seed command); today's row is refreshed by the seed to match
    the actual current stocked count. ``free = 24 - occupied`` always.
    """

    date = models.DateField(unique=True)
    occupied = models.IntegerField(validators=[MinValueValidator(0), MaxValueValidator(24)])
    free = models.IntegerField(validators=[MinValueValidator(0), MaxValueValidator(24)])

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return f"{self.date}: {self.occupied} occupied / {self.free} free"


class Profile(models.Model):
    """Role for a Django user. One profile per user."""

    ROLE_ADMIN = "admin"
    ROLE_AUDITOR = "auditor"
    ROLE_TECHNICIAN = "technician"
    ROLE_CHOICES = [
        (ROLE_ADMIN, "Admin"),
        (ROLE_AUDITOR, "Auditor"),
        (ROLE_TECHNICIAN, "Technician"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, default=ROLE_TECHNICIAN)

    def __str__(self):
        return f"{self.user.username} ({self.role})"
