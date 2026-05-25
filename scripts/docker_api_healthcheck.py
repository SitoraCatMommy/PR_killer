"""HTTP health for Docker Compose (slim image without curl)."""
import sys
import urllib.error
import urllib.request


def main() -> None:
    try:
        urllib.request.urlopen("http://127.0.0.1:8000/api/v1/health", timeout=5).read()
    except (OSError, urllib.error.URLError):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
