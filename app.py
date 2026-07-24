import re
from pathlib import Path

import streamlit as st

SLIDES_DIR = Path(__file__).parent / "POSTER_SABRE2026"


def natural_key(path: Path) -> list:
    """Sort Slide1, Slide2, ..., Slide10 in human order."""
    return [int(t) if t.isdigit() else t.lower()
            for t in re.split(r"(\d+)", path.name)]


def find_slides() -> list[Path]:
    if not SLIDES_DIR.exists():
        return []
    return sorted(SLIDES_DIR.glob("Slide*.png"), key=natural_key)


def main() -> None:
    st.set_page_config(page_title="PEMSE Poster", layout="wide")

    slides = find_slides()

    st.title("PEMSE - SABRE 2026 Poster")

    if not slides:
        st.warning(f"No slides found in `{SLIDES_DIR}`. Add files named "
                   f"`Slide1.png`, `Slide2.png`, ...")
        return

    for slide in slides:
        st.image(str(slide), caption=slide.name, use_container_width=True)


if __name__ == "__main__":
    main()
