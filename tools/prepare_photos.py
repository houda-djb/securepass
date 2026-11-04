"""Turn the pictures you downloaded into the right size and put them where the site expects them.

How to use (from the project root, with the virtual environment active):

    1. Make a folder called  photos_in  next to this project's files.
    2. Save your downloads in it. Name each file after its place, for example  alger.jpg,
       istanbul.png, algeria.webp  (any of jpg, jpeg, png, webp; upper or lower case).
    3. Run:   python tools/prepare_photos.py
    4. The script writes 1600 x 1200 JPEG files (under about 400 KB) into
       app/static/img/destinations/  and  app/static/img/destinations/countries/.
       A file named hero.* goes in as the 1920 x 1080 home-page picture.

It tells you which places still have no picture and which file names it did not recognise.
Nothing outside photos_in and the two destination folders is touched.
"""
import re
import sys
import unicodedata
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.seed import AIRPORTS, COUNTRIES  # noqa: E402

SOURCE = ROOT / "photos_in"
CITY_DIR = ROOT / "app" / "static" / "img" / "destinations"
COUNTRY_DIR = CITY_DIR / "countries"
EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_BYTES = 400 * 1024


# Other ways people name a file. Matching is on the start of the file name, accents ignored.
ALIASES = {
    "algiers": "alger", "algier": "alger", "saudi": "saudi-arabia", "turk": "turkey",
    "turkiye": "turkey", "greec": "greece", "u emirate": "united-arab-emirates",
    "uae": "united-arab-emirates", "emirates": "united-arab-emirates", "uk": "united-kingdom",
    "usa": "united-states", "us": "united-states", "kl": "kuala-lumpur", "newyork": "new-york",
}


def simple(text: str) -> str:
    """Lower case, no accents, only letters and digits separated by single spaces."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def find_place(stem: str, known: dict[str, str]) -> str | None:
    """The place a file name starts with, so 'Paris, Eiffel Tower' is paris. Longest match wins."""
    text = simple(stem)
    best = None
    for word, slug in known.items():
        if text == word or text.startswith(word + " "):
            if best is None or len(word) > best[0]:
                best = (len(word), slug)
    return best[1] if best else None


def save_jpeg(image: Image.Image, target: Path, size: tuple[int, int]) -> int:
    """Crop to the wanted shape, shrink, and lower the quality until the file is small enough."""
    image = ImageOps.exif_transpose(image).convert("RGB")
    image = ImageOps.fit(image, size, Image.LANCZOS, centering=(0.5, 0.45))
    target.parent.mkdir(parents=True, exist_ok=True)
    for quality in (88, 82, 76, 70, 64, 58):
        image.save(target, "JPEG", quality=quality, optimize=True, progressive=True)
        if target.stat().st_size <= MAX_BYTES:
            break
    return target.stat().st_size


def main() -> int:
    if not SOURCE.is_dir():
        print(f"Create the folder {SOURCE} and put your downloaded pictures in it first.")
        return 1

    cities = {a[4] for a in AIRPORTS}
    countries = {c[0] for c in COUNTRIES}
    known = {simple(slug): slug for slug in cities | countries | {"hero"}}
    known.update({simple(a[1]): a[4] for a in AIRPORTS})
    known.update({simple(c[1]): c[0] for c in COUNTRIES})
    known.update({simple(k): v for k, v in ALIASES.items()})
    done, unknown = set(), []

    for path in sorted(SOURCE.iterdir()):
        if path.suffix.lower() not in EXTENSIONS:
            continue
        name = find_place(path.stem, known) or ""
        try:
            with Image.open(path) as image:
                if name == "hero":
                    size = save_jpeg(image, CITY_DIR / "hero.jpg", (1920, 1080))
                    done.add("hero")
                elif name in cities:
                    size = save_jpeg(image, CITY_DIR / f"{name}.jpg", (1600, 1200))
                    done.add(name)
                elif name in countries:
                    size = save_jpeg(image, COUNTRY_DIR / f"{name}.jpg", (1600, 1200))
                    done.add(f"country:{name}")
                else:
                    unknown.append(path.name)
                    continue
        except OSError:
            print(f"Could not read {path.name}: is it really a picture?")
            continue
        print(f"ok  {path.name}  ->  {size // 1024} KB")

    print()
    if unknown:
        print("Not recognised (rename them to a place name from docs/PHOTOS.md):", ", ".join(unknown))
    missing_cities = sorted(c for c in cities if c not in done)
    missing_countries = sorted(c for c in countries if f"country:{c}" not in done)
    print(f"Cities with a picture: {len(cities) - len(missing_cities)} of {len(cities)}")
    print(f"Countries with a picture: {len(countries) - len(missing_countries)} of {len(countries)}")
    if missing_cities:
        print("Cities still missing:", ", ".join(missing_cities))
    if missing_countries:
        print("Countries still missing:", ", ".join(missing_countries))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
