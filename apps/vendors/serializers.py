# apps/vendors/serializers.py (add)
from rest_framework import serializers


class VendorTermsSerializer(serializers.Serializer):
    vendor_id = serializers.IntegerField()
    version = serializers.IntegerField()
    terms_items = serializers.ListField(child=serializers.CharField(), default=list)
    security_deposit_note = serializers.CharField(allow_blank=True)
    operating_hours_note = serializers.CharField(allow_blank=True)
    distance_limit_note = serializers.CharField(allow_blank=True)
    excess_charge_note = serializers.CharField(allow_blank=True)
    late_penalty_note = serializers.CharField(allow_blank=True)
