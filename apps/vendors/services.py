# apps/vendors/services.py (add)
from apps.vendors.repositories import VendorTermsRepository


class VendorTermsService:

    @staticmethod
    def get_current_terms(vendor_id: int):
        return VendorTermsRepository.get_current(vendor_id)
