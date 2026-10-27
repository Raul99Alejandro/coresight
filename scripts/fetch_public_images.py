"""Download the public core photos listed in IMAGES into data/raw/.

data/raw/ is not in git, so this script is how the dataset is rebuilt.
License and author are read from Wikimedia Commons at download time and
printed as rows for the "Images used" table in data/labels/SOURCES.md.

    .venv\\Scripts\\python scripts\\fetch_public_images.py
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import httpx

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
# Wikimedia's robot policy requires a contact URL in the User-Agent.
USER_AGENT = "CoreSight/0.1 (https://github.com/Raul99Alejandro/coresight) httpx"

# local file name -> Commons file title
IMAGES: dict[str, str] = {
    # Full core boxes (calibration, segmentation, RQD).
    "commons_onkalo_1.jpg": "File:Drill core boxes Onkalo 1.jpg",
    "commons_onkalo_2.jpg": "File:Drill core boxes Onkalo 2.jpg",
    "commons_warren_dolostone_1.jpg": (
        "File:Dolostone (Knox Dolomite, Upper Cambrian; Warren County core, Ohio, USA) 1.jpg"
    ),
    # Close-ups of one or two pieces (Muse Spark descriptions only, not RQD).
    "commons_potter_07.jpg": (
        "File:Polymetallic massive sulfide (Middle Tholeiitic Unit, Kidd-Munro Assemblage, "
        "Neoarchean, 2.711 to 2.719 Ga; drill core at the Potter Mine, east of Timmins, "
        "Ontario, Canada) 7 (32928631057).jpg"
    ),
    "commons_potter_27.jpg": (
        "File:Polymetallic massive sulfide (Middle Tholeiitic Unit, Kidd-Munro Assemblage, "
        "Neoarchean, 2.711 to 2.719 Ga; drill cores at the Potter Mine, east of Timmins, "
        "Ontario, Canada) 27 (46962006025).jpg"
    ),
    "commons_potter_28.jpg": (
        "File:Polymetallic massive sulfide (Middle Tholeiitic Unit, Kidd-Munro Assemblage, "
        "Neoarchean, 2.711 to 2.719 Ga; drill cores at the Potter Mine, east of Timmins, "
        "Ontario, Canada) 28 (47826051212).jpg"
    ),
    "commons_potter_30.jpg": (
        "File:Polymetallic massive sulfide (Middle Tholeiitic Unit, Kidd-Munro Assemblage, "
        "Neoarchean, 2.711 to 2.719 Ga; drill core at the Potter Mine, east of Timmins, "
        "Ontario, Canada) 30 (34001032088).jpg"
    ),
    "commons_potter_32.jpg": (
        "File:Polymetallic massive sulfide (Middle Tholeiitic Unit, Kidd-Munro Assemblage, "
        "Neoarchean, 2.711 to 2.719 Ga; drill core at the Potter Mine, east of Timmins, "
        "Ontario, Canada) 32 (34001038068).jpg"
    ),
    "commons_potter_argillite_2.jpg": (
        "File:Sulfidic argillite & polymetallic massive sulfide (Middle Tholeiitic Unit, "
        "Kidd-Munro Assemblage, Neoarchean, 2.711 to 2.719 Ga; drill cores at the Potter Mine, "
        "east of Timmins, Ontario, Canada) 2 (46959105055).jpg"
    ),
    # Day 8: full boxes of broken core, candidates for the "dramatic" demo sample.
    "commons_breidalsvik.jpg": "File:Drill Cores, in Drill Core Library in Breiðdalsvík.jpg",
    "commons_nts_u12g_1.jpg": (
        "File:CORE SAMPLES, NEVADA TEST SITE - DPLA - db76f1349ca15c6259411296fd16eef3.jpg"
    ),
    "commons_nts_u12g_2.jpg": (
        "File:CORE SAMPLES, NEVADA TEST SITE - DPLA - 5eb8f78b3e71b2e05f1806559ea3b012.jpg"
    ),
    "commons_nts_1981.jpg": (
        "File:CORE SAMPLES, NEVADA TEST SITE - DPLA - 344a80c6542b9421f65b34db561bdfcf.jpg"
    ),
    "commons_diamond_core.jpg": "File:Diamond Core.jpeg",
    "commons_butte_broken_1.jpg": (
        "File:Broken drill core (Butte Mining District, Montana, USA) 1.jpg"
    ),
}


def _plain(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html).strip()


def file_info(client: httpx.Client, title: str) -> dict:
    params = {
        "action": "query",
        "titles": title,
        "prop": "imageinfo",
        "iiprop": "url|size|extmetadata",
        "format": "json",
    }
    page = next(iter(client.get(COMMONS_API, params=params).json()["query"]["pages"].values()))
    if "imageinfo" not in page:
        raise RuntimeError(f"not found on Commons: {title}")
    return page["imageinfo"][0]


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    with httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=120, follow_redirects=True
    ) as client:
        for name, title in IMAGES.items():
            info = file_info(client, title)
            meta = info["extmetadata"]
            target = RAW_DIR / name
            if not target.exists():
                target.write_bytes(client.get(info["url"]).content)
                time.sleep(0.5)
            license_name = meta.get("LicenseShortName", {}).get("value", "?")
            author = _plain(meta.get("Artist", {}).get("value", "?"))
            rows.append(
                f"| `{name}` | [Commons]({info['descriptionurl']}) | {author} "
                f"| {license_name} | none |"
            )
            print(f"{name}: {info['width']}x{info['height']}, {license_name}")
    print("\nRows for data/labels/SOURCES.md:\n")
    print("\n".join(rows))


if __name__ == "__main__":
    main()
