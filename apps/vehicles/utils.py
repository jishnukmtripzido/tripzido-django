from decimal import Decimal


def format_duration(total_hours) -> str:
    """e.g. '2 months', '2 weeks', '1 day 6 hours', '45 minutes'.

    Months are approximated as 30 days since hours don't map onto
    calendar months cleanly — fine for a human-readable label, not
    meant for billing math.
    """
    if not isinstance(total_hours, Decimal):
        total_hours = Decimal(str(total_hours))

    total_minutes = int((total_hours * 60).to_integral_value())
    months, rem = divmod(total_minutes, 30 * 24 * 60)
    weeks, rem = divmod(rem, 7 * 24 * 60)
    days, rem = divmod(rem, 24 * 60)
    hours, minutes = divmod(rem, 60)

    parts = []
    if months:
        parts.append(f"{months} month{'s' if months != 1 else ''}")
    if weeks:
        parts.append(f"{weeks} week{'s' if weeks != 1 else ''}")
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")

    return " ".join(parts) if parts else "0 minutes"
