from apps.administrations.models import CancellationPolicy


class CancellationPolicyRepository:

    @staticmethod
    def get_current():
        return (
            CancellationPolicy.objects.filter(is_current=True)
            .prefetch_related("tiers")
            .first()
        )
