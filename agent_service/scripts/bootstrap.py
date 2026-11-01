"""Initialize local configuration without replacing an existing .env."""

import secrets
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import dotenv_values


def main() -> None:
    if sys.version_info[:3] != (3, 11, 9):
        raise SystemExit("Use the project's Python 3.11.9 virtual environment")
    root = Path(__file__).resolve().parents[1]
    destination = root / ".env"
    if destination.exists():
        values = dotenv_values(destination)
        parsed = urlparse(values.get("DATABASE_URL", ""))
        additions = {"POSTGRES_USER": unquote(parsed.username or "citysense"), "POSTGRES_DB": parsed.path.strip("/") or "citysense", "POSTGRES_PASSWORD": unquote(parsed.password or secrets.token_urlsafe(32))}
        missing = {key: value for key, value in additions.items() if key not in values}
        if missing:
            with destination.open("a", encoding="utf-8") as file:
                file.write("\n" + "\n".join(f"{key}={value}" for key, value in missing.items()) + "\n")
        print("Existing .env values preserved; missing Compose variables initialized")
        return
    sample = (root / ".env.example").read_text(encoding="utf-8")
    destination.write_text(
        sample.replace("JWT_SECRET=GENERATE_WITH_BOOTSTRAP", "JWT_SECRET=" + secrets.token_urlsafe(48)).replace("GENERATE_DATABASE_PASSWORD", secrets.token_urlsafe(32)),
        encoding="utf-8",
    )
    print("Created .env with generated JWT secret; no secret values printed")


if __name__ == "__main__":
    main()
