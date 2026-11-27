"""Views for the Warehouse Management System API.

Endpoints (see README for the full contract):
  POST /api/auth/login/   - JWT login, returns access/refresh + user role
  GET  /api/map/          - 25 locations with occupancy + pallet (any authed user)
  POST /api/load/         - technician/admin: store a pallet at a location
  POST /api/unload/       - technician/admin: return a pallet via A1, out of stock
  GET  /api/shuttle/      - shuttle status from the DB (any authed user)
  GET  /api/dashboard/    - auditor/admin: counts + 7-day history + stocked pallets
  /api/admin/users/       - admin only: user CRUD
  GET  /health/           - no auth
"""
import re

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Location, OccupancySnapshot, Pallet, Profile, Shuttle
from .permissions import IsAdmin, IsAuditorOrAdmin, IsTechnicianOrAdmin, get_role
from .serializers import (
    LocationSerializer,
    OccupancySnapshotSerializer,
    PalletSerializer,
    ShuttleSerializer,
    UserCreateSerializer,
    UserSerializer,
    UserUpdateSerializer,
)

# Storage locations are the 24 non-transfer cells; A1 is the transfer point.
STORAGE_LOCATION_COUNT = 24
CODE_RE = re.compile(r"^[A-E][1-5]$")


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    return Response({"status": "ok"})


@api_view(["POST"])
@permission_classes([AllowAny])
def login(request):
    """POST {username, password} -> 200 {access, refresh, user:{username, role}}."""
    username = request.data.get("username")
    password = request.data.get("password")
    user = authenticate(request, username=username, password=password)
    if user is None:
        return Response(
            {"detail": "Invalid username or password."},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    profile, _ = Profile.objects.get_or_create(
        user=user, defaults={"role": Profile.ROLE_TECHNICIAN}
    )
    refresh = RefreshToken.for_user(user)
    return Response(
        {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {"username": user.username, "role": profile.role},
        }
    )


class MapView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        locations = Location.objects.prefetch_related("pallets").all()
        return Response({"locations": LocationSerializer(locations, many=True).data})


def _resolve_location(code):
    """Return (location, error_response). ``code`` must be a valid grid code
    that exists in the DB; anything else is a 400."""
    if not isinstance(code, str) or not CODE_RE.match(code or ""):
        return None, Response(
            {"detail": f"Invalid location code: {code!r}. Use A1..E5."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        return Location.objects.get(code=code), None
    except Location.DoesNotExist:
        return None, Response(
            {"detail": f"Invalid location code: {code!r}. Use A1..E5."},
            status=status.HTTP_400_BAD_REQUEST,
        )


class LoadView(APIView):
    permission_classes = [IsAuthenticated, IsTechnicianOrAdmin]

    @transaction.atomic
    def post(self, request):
        data = request.data
        pallet_number = (data.get("pallet_number") or "").strip()
        barcode = (data.get("barcode") or "").strip()
        item = (data.get("item") or "").strip()
        quantity = data.get("quantity")
        destination = data.get("destination")

        if not pallet_number:
            return Response({"detail": "pallet_number is required."}, status=400)
        if not barcode:
            return Response({"detail": "barcode is required."}, status=400)
        if not item:
            return Response({"detail": "item is required."}, status=400)
        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            return Response({"detail": "quantity must be a positive integer."}, status=400)
        if quantity <= 0:
            return Response(
                {"detail": "quantity must be greater than 0."}, status=400
            )

        location, err = _resolve_location(destination)
        if err is not None:
            return err
        if location.is_transfer_point:
            return Response(
                {"detail": "A1 is the transfer point and cannot hold a stored pallet."},
                status=400,
            )
        if location.occupied:
            return Response(
                {"detail": f"Location {location.code} is already occupied."},
                status=400,
            )
        if Pallet.objects.filter(pallet_number=pallet_number).exists():
            return Response(
                {"detail": f"Pallet number {pallet_number} already exists."},
                status=400,
            )

        pallet = Pallet.objects.create(
            pallet_number=pallet_number,
            barcode=barcode,
            item=item,
            quantity=quantity,
            location=location,
        )
        result = PalletSerializer(pallet).data
        result["location_detail"] = LocationSerializer(location).data
        return Response(result, status=status.HTTP_201_CREATED)


class UnloadView(APIView):
    permission_classes = [IsAuthenticated, IsTechnicianOrAdmin]

    @transaction.atomic
    def post(self, request):
        code = request.data.get("location")
        location, err = _resolve_location(code)
        if err is not None:
            return err
        if location.is_transfer_point:
            return Response(
                {"detail": "A1 is the transfer point; unload a storage location."},
                status=400,
            )
        pallet = location.pallet
        if pallet is None:
            return Response(
                {"detail": f"Location {location.code} is already free."},
                status=400,
            )
        pallet.location = None  # leaves warehouse stock; row kept for history
        pallet.save(update_fields=["location"])
        return Response(
            {
                "detail": (
                    f"Pallet {pallet.pallet_number} returned via A1 and "
                    f"removed from stock at {location.code}."
                ),
                "location": LocationSerializer(location).data,
            }
        )


class ShuttleView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        shuttle = Shuttle.objects.order_by("id").first()
        if shuttle is None:
            return Response({"detail": "No shuttle configured."}, status=404)
        return Response(ShuttleSerializer(shuttle).data)


class DashboardView(APIView):
    permission_classes = [IsAuthenticated, IsAuditorOrAdmin]

    def get(self, request):
        stocked = Pallet.objects.filter(location__isnull=False).select_related("location")
        occupied = stocked.count()
        history = OccupancySnapshot.objects.order_by("date")[:7]
        return Response(
            {
                "occupied": occupied,
                "free": STORAGE_LOCATION_COUNT - occupied,
                "history": OccupancySnapshotSerializer(history, many=True).data,
                "pallets": PalletSerializer(stocked, many=True).data,
            }
        )


class AdminUsersView(APIView):
    """GET list / POST create. Admin only."""

    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        users = User.objects.prefetch_related("profile").order_by("username")
        return Response(UserSerializer(users, many=True).data)

    def post(self, request):
        serializer = UserCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class AdminUserDetailView(APIView):
    """PATCH role/password / DELETE user. Admin only.

    Guards: never delete the last admin, never delete your own account,
    and never demote the last admin to another role.
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def _get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except (User.DoesNotExist, ValueError, TypeError):
            return None

    def _admin_count(self):
        return Profile.objects.filter(role=Profile.ROLE_ADMIN).count()

    def patch(self, request, user_id):
        target = self._get_user(user_id)
        if target is None:
            return Response({"detail": "User not found."}, status=404)
        serializer = UserUpdateSerializer(target, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)
        new_role = serializer.validated_data.get("role")
        if (
            new_role is not None
            and new_role != Profile.ROLE_ADMIN
            and get_role(target) == Profile.ROLE_ADMIN
            and self._admin_count() <= 1
        ):
            return Response(
                {"detail": "Cannot demote the last admin."}, status=400
            )
        serializer.save()
        # Re-fetch: the guard above cached target.profile, so the in-memory
        # profile would otherwise still show the pre-update role.
        target = User.objects.prefetch_related("profile").get(pk=target.pk)
        return Response(UserSerializer(target).data)

    def delete(self, request, user_id):
        target = self._get_user(user_id)
        if target is None:
            return Response({"detail": "User not found."}, status=404)
        if target.id == request.user.id:
            return Response(
                {"detail": "You cannot delete your own account."}, status=400
            )
        if get_role(target) == Profile.ROLE_ADMIN and self._admin_count() <= 1:
            return Response(
                {"detail": "Cannot delete the last admin."}, status=400
            )
        target.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
