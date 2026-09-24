import re
import uuid

def generate_uuid():
    return str(uuid.uuid4())


def normalize_phone_number(raw):
    """Strips spaces/dashes/parens so the same number always compares equal
    regardless of how it was typed (Admin > Users) vs. how Firebase reports
    it at login time (always compact, e.g. '+911234567890'). Without this,
    a role assigned to "+91 1234567890" silently never matches the account
    Firebase actually logs the person into, leaving them stuck on
    "awaiting approval" forever. Keeps the leading '+' and digits only —
    doesn't touch the E.164-with-plus convention already used everywhere."""
    if not raw:
        return raw
    return re.sub(r'[^\d+]', '', raw.strip())