
ARABIC_MONTHS = {
    1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل",
    5: "مايو", 6: "يونيو", 7: "يوليو", 8: "أغسطس",
    9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر",
}


def format_fees_date_ar(date_value):
    """Return a date formatted in Arabic, e.g. '5 يونيو 2026م'."""
    if not date_value:
        return ""
    return f"{date_value.day} {ARABIC_MONTHS.get(date_value.month, '')} {date_value.year}م"
