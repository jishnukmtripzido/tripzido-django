from apps.administrations.repositories import CancellationPolicyRepository


class CancellationPolicyService:

    @staticmethod
    def _auto_label(min_h: int, max_h: int | None) -> str:
        if max_h is None:
            return f"More than {min_h} hours before pickup"
        if min_h == 0:
            return f"Less than {max_h} hours before pickup"
        return f"{min_h} – {max_h} hours before pickup"

    @staticmethod
    def _auto_description(refund: int) -> str:
        if refund == 100:
            return "Full refund of advance payment."
        if refund == 0:
            return "No refund."
        return f"{refund}% refund of advance payment."

    @staticmethod
    def get_current_policy() -> dict | None:
        policy = CancellationPolicyRepository.get_current()
        if policy is None:
            return None

        tiers = sorted(policy.tiers.all(), key=lambda t: -t.min_hours_before_pickup)

        rules = []
        for tier in tiers:
            min_h = tier.min_hours_before_pickup
            max_h = tier.max_hours_before_pickup
            refund = int(tier.refund_percentage)

            rules.append(
                {
                    "hours_before_pickup": min_h,
                    "refund_percentage": refund,
                    "label": tier.label
                    or CancellationPolicyService._auto_label(min_h, max_h),
                    "description": tier.description
                    or CancellationPolicyService._auto_description(refund),
                }
            )

        return {
            "rules": rules,
            "note": policy.refund_note,
        }
