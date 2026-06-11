from rest_framework import serializers


class CancellationTierSerializer(serializers.Serializer):
    hours_before_pickup = serializers.IntegerField()
    refund_percentage = serializers.IntegerField()
    label = serializers.CharField()
    description = serializers.CharField()


class CancellationPolicySerializer(serializers.Serializer):
    rules = CancellationTierSerializer(many=True)
    note = serializers.CharField()
