# apps/vehicles/repositories.py

# from django.db.models import Q
# from apps.vehicles.models import VehicleListing
# from apps.vendors.models import Vendor

# class VehicleSearchRepository:

#     @staticmethod
#     def search(city_id: int, pickup_datetime, dropoff_datetime):
#         return (
#             VehicleListing.objects
#             .select_related(
#                 "vehicle_type",
#                 "vendor",
#                 "pickup_location",
#                 "pickup_location__city",
#             )
#             .prefetch_related(
#                 "pricing_packages__package_type",
#                 "images",
#             )
#             .filter(
#                 status=VehicleListing.Status.APPROVED,
#                 pickup_location__city_id=city_id,
#                 vendor__status=Vendor.Status.APPROVED,
#             )
#         )



# apps/vehicles/repository.py

from django.db.models import Prefetch
from apps.vehicles.models import (
    VehicleType, VehicleListing, PricingPackage
)
from apps.vendors.models import Vendor


class VehicleSearchRepository:

    @staticmethod
    def search(city_id: int, pickup_datetime, dropoff_datetime):
        # Step 1 — filter listings to only approved ones in this city
        # This becomes a subquery; Django doesn't evaluate it yet
        active_listings = VehicleListing.objects.filter(
            status=VehicleListing.Status.APPROVED,
            pickup_location__city_id=city_id,
            vendor__status=Vendor.Status.APPROVED,
        ).select_related(
            "pickup_location__city",
            "vendor",
        ).prefetch_related(
            Prefetch(
                "pricing_packages",
                # pull package_type + its category in one join
                queryset=PricingPackage.objects.select_related(
                    "package_type__category"
                ).order_by("package_type__sort_order"),
            ),
             "images", 
        )

        # Step 2 — fetch VehicleTypes that have at least one active listing,
        # and attach those filtered listings as `city_listings`
        return (
            VehicleType.objects
            .filter(
                is_published=True,
                listings__in=active_listings,   # existence check (subquery)
            )
            .distinct()
            .prefetch_related(
                Prefetch(
                    "listings",
                    queryset=active_listings,
                    to_attr="city_listings",    # → vehicle_type.city_listings
                ),
            )
            .order_by("brand", "name")
        )