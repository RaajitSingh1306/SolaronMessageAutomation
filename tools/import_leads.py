import csv
import os
import re


def _clean_phone(raw: str) -> str:
    if not raw:
        return ""
    cleaned = str(raw).strip().strip("'\"").strip()
    digits = "".join(ch for ch in cleaned if ch.isdigit())
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits if digits else cleaned


def main():
    leads_path = None
    for fname in ["Leads.csv", "leads.csv"]:
        p = os.path.join("data", fname)
        if os.path.exists(p):
            leads_path = p
            break

    contacts_path = os.path.join("data", "contacts.csv")

    if not leads_path:
        print("Error: data/Leads.csv or data/leads.csv not found.")
        return

    # First, read existing contacts to preserve any manually added entries
    contacts = {}
    if os.path.exists(contacts_path):
        with open(contacts_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(",", 1)
                if len(parts) >= 2:
                    name = parts[0].strip()
                    phone = _clean_phone(parts[1])
                    if name.lower() != "plant name" and phone:
                        contacts[name.lower()] = (name, phone)

    print(f"Loaded {len(contacts)} existing contacts.")

    # Now read Leads.csv
    total_leads = 0
    added_leads = 0
    skipped_no_phone = 0
    skipped_duplicate = 0

    with open(leads_path, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_leads += 1
            first_name = (row.get("First name") or "").strip()
            last_name = (row.get("Last name") or "").strip()
            mobile = _clean_phone(row.get("Mobile") or "")

            if not mobile:
                skipped_no_phone += 1
                continue

            full_name = f"{first_name} {last_name}".strip() if last_name else first_name
            if not full_name:
                full_name = "Unknown Lead"

            name_key = full_name.lower()
            if name_key in contacts:
                skipped_duplicate += 1
                continue

            contacts[name_key] = (full_name, mobile)
            added_leads += 1

    # Write all to contacts.csv
    with open(contacts_path, "w", encoding="utf-8") as f:
        f.write("Plant Name, Phone Number\n")
        for _, (name, phone) in sorted(contacts.items()):
            f.write(f"{name}, {phone}\n")

    # Reset cache to allow fresh reloads
    cache_path = os.path.join("data", "phone_cache.json")
    if os.path.exists(cache_path):
        try:
            os.remove(cache_path)
            print("Cleared obsolete phone_cache.json.")
        except Exception:
            pass

    print("\n--- Import Summary ---")
    print(f"Total leads in CSV : {total_leads}")
    print(f"Added to contacts  : {added_leads}")
    print(f"Skipped (no phone) : {skipped_no_phone}")
    print(f"Skipped (duplicate): {skipped_duplicate}")
    print(f"Total in contacts  : {len(contacts)}")


if __name__ == "__main__":
    main()

