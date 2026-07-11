# apps/vendors/repositories.py (add)
from apps.vendors.models import VendorTerms


class VendorTermsRepository:

    @staticmethod
    def get_current(vendor_id: int):
        return VendorTerms.objects.filter(vendor_id=vendor_id, is_current=True).first()
