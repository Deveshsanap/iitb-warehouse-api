"""Serializers for the Warehouse Management System API."""
from django.contrib.auth.models import User
from rest_framework import serializers

from .models import Location, OccupancySnapshot, Pallet, Profile, Shuttle


class PalletSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Pallet
        fields = ["pallet_number", "barcode", "item", "quantity"]


class LocationSerializer(serializers.ModelSerializer):
    occupied = serializers.BooleanField(read_only=True)
    pallet = PalletSummarySerializer(read_only=True)

    class Meta:
        model = Location
        fields = ["code", "is_transfer_point", "occupied", "pallet"]


class PalletSerializer(serializers.ModelSerializer):
    location = serializers.CharField(source="location.code", read_only=True, default=None)

    class Meta:
        model = Pallet
        fields = ["id", "pallet_number", "barcode", "item", "quantity", "location", "created_at"]


class ShuttleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shuttle
        fields = ["identifier", "status", "battery_percent"]


class OccupancySnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = OccupancySnapshot
        fields = ["date", "occupied", "free"]


class UserSerializer(serializers.ModelSerializer):
    role = serializers.CharField(source="profile.role", read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "role"]


class UserCreateSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=128, write_only=True)
    role = serializers.ChoiceField(choices=Profile.ROLE_CHOICES)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data["username"],
            password=validated_data["password"],
        )
        Profile.objects.create(user=user, role=validated_data["role"])
        return user


class UserUpdateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=Profile.ROLE_CHOICES, required=False)
    password = serializers.CharField(max_length=128, write_only=True, required=False)

    def update(self, instance, validated_data):
        if "role" in validated_data:
            profile, _ = Profile.objects.get_or_create(user=instance)
            profile.role = validated_data["role"]
            profile.save()
        if "password" in validated_data:
            instance.set_password(validated_data["password"])
            instance.save()
        return instance
