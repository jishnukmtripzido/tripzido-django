# apps/vendors/repositories.py
from apps.vendors.models import VendorTerms


class VendorTermsRepository:

    @staticmethod
    def get_current(vendor_id: int):
        return VendorTerms.objects.filter(vendor_id=vendor_id, is_current=True).first()

    @staticmethod
    def save_new_version(vendor_id: int, data: dict) -> VendorTerms:
        """
        Reuses VendorTerms.save()'s own versioning logic rather than
        reimplementing it: fetching the current row (if any) and
        mutating its fields before calling .save() triggers the
        "if self.pk is not None" branch on the model, which bumps
        version, detaches the pk, and inserts a brand-new row — so
        this never overwrites history, only adds to it. A vendor's
        first-ever save (no current row yet) falls through to a fresh
        VendorTerms(vendor_id=...) instance instead, which the model's
        own save() already handles correctly (stays at version=1).
        """
        current = VendorTerms.objects.filter(
            vendor_id=vendor_id, is_current=True
        ).first()
        terms = current or VendorTerms(vendor_id=vendor_id)
        for field, value in data.items():
            setattr(terms, field, value)
        terms.save()
        return terms
