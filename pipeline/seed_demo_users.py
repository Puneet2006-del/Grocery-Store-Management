"""Create two demo shopkeepers and give each two of the existing shops.

  delhi@demo.com   Delhi Fresh Mart   Delhi-Central (S01), Delhi-South (S02)
  ncr@demo.com     NCR Grocers        Gurgaon-Sector29 (S03), Noida-Sector18 (S04)
  password for both: demo12345

Safe to run again: existing accounts keep their password; shop ownership is set again.
Run once after db/schema_m5_auth.sql:   python pipeline/seed_demo_users.py
"""
import base64
import hashlib
import os
import sys
from pathlib import Path

from sqlalchemy import bindparam, text

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / "intelligence")]
from db import engine  # noqa: E402

PASSWORD = "demo12345"
DEMOS = [("delhi@demo.com", "Delhi Fresh Mart", ["S01", "S02"]),
         ("ncr@demo.com", "NCR Grocers", ["S03", "S04"])]


def hash_password(password, salt_b64):
    """Same scheme as the Java backend: PBKDF2-HMAC-SHA256, 120,000 rounds, 256-bit key, base64."""
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), base64.b64decode(salt_b64), 120_000, dklen=32)
    return base64.b64encode(key).decode()


def main():
    with engine.begin() as conn:
        for email, name, store_ids in DEMOS:
            row = conn.execute(text("SELECT user_id FROM users WHERE email = :e"), {"e": email}).fetchone()
            if row is None:
                salt = base64.b64encode(os.urandom(16)).decode()
                conn.execute(text("INSERT INTO users (email, display_name, password_salt, password_hash) "
                                  "VALUES (:e, :n, :s, :h)"),
                             {"e": email, "n": name, "s": salt, "h": hash_password(PASSWORD, salt)})
                row = conn.execute(text("SELECT user_id FROM users WHERE email = :e"), {"e": email}).fetchone()
                print(f"Created {email} ({name})")
            else:
                print(f"{email} already exists")
            conn.execute(text("UPDATE stores SET owner_id = :u WHERE store_id IN :ids")
                         .bindparams(bindparam("ids", expanding=True)), {"u": row[0], "ids": store_ids})
            print(f"  owns {', '.join(store_ids)}")
    print(f"\nSign in with either email and the password {PASSWORD}")


if __name__ == "__main__":
    main()
