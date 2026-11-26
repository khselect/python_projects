"""docs/interactive-guide.src.html + docs/screenshots/*.png → docs/interactive-guide.html (단일 파일).

스크린샷을 1200px JPEG로 줄여 base64로 넣는다 — 인터넷 없이 열리고, sielain.com 개발자료에
파일 하나로 올릴 수 있게. 스크린샷을 다시 찍었으면 이 스크립트만 다시 실행한다.

    python docs/build_interactive_guide.py
"""

import base64
import io
import re
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
SRC = HERE / "interactive-guide.src.html"
OUT = HERE / "interactive-guide.html"
WIDTH = 1200


def data_uri(png: Path) -> str:
    im = Image.open(png).convert("RGB")
    if im.width > WIDTH:
        im = im.resize((WIDTH, round(im.height * WIDTH / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=74, optimize=True, progressive=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def main() -> None:
    html = SRC.read_text(encoding="utf-8")
    names = sorted(set(re.findall(r"\{\{IMG_([\w-]+)\}\}", html)))
    for n in names:
        html = html.replace("{{IMG_" + n + "}}", data_uri(HERE / "screenshots" / f"{n}.png"))
    OUT.write_text(html, encoding="utf-8")
    print(f"{OUT.name}: 이미지 {len(names)}개, {OUT.stat().st_size / 1024:.0f}KB")


if __name__ == "__main__":
    main()
