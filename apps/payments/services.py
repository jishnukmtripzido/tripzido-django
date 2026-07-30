from apps.payments.repositories import VendorPayoutRepository


class VendorPayoutService:

    @staticmethod
    def get_for_vendor(vendor_id: int):
        return VendorPayoutRepository.get_for_vendor(vendor_id)

    @staticmethod
    def get_detail_for_vendor(payout_id: int, vendor_id: int):
        return VendorPayoutRepository.get_detail_for_vendor(payout_id, vendor_id)
