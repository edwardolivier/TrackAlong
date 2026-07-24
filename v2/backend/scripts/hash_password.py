"""
Generate an argon2 hash for the single app password.

    python scripts/hash_password.py

Prompts for a password (hidden input) and prints the hash. Set the output as the
APP_PASSWORD_HASH environment variable (Cloud Run) or GitHub Actions secret. The
plaintext password is never stored anywhere.
"""
import getpass

from argon2 import PasswordHasher


def main() -> None:
    pw = getpass.getpass("New app password: ")
    if len(pw) < 8:
        raise SystemExit("Password must be at least 8 characters.")
    if getpass.getpass("Confirm password: ") != pw:
        raise SystemExit("Passwords do not match.")

    print()
    print("APP_PASSWORD_HASH:")
    print(PasswordHasher().hash(pw))


if __name__ == "__main__":
    main()
