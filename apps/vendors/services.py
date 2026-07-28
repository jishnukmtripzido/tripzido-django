# apps/vendors/services.py
from apps.vendors.repositories import VendorTermsRepository


class VendorTermsService:

    @staticmethod
    def get_current_terms(vendor_id: int):
        return VendorTermsRepository.get_current(vendor_id)

    @staticmethod
    def save_new_version(vendor_id: int, data: dict):
        return VendorTermsRepository.save_new_version(vendor_id, data)
