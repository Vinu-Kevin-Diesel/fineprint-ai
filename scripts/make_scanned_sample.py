"""Generate a *scanned-style* test document: text rasterized into an image, with
no selectable text layer. Produces samples/scanned-lease.png and a matching
image-only PDF (samples/scanned-lease.pdf) to exercise the OCR fallback.

Requires Pillow:  pip install pillow
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT_DIR = Path(__file__).resolve().parent.parent / "samples"

TEXT = """RESIDENTIAL LEASE AGREEMENT (SCANNED SAMPLE)

1. TERM. This lease begins August 1, 2026 for a term of twelve (12) months.

2. RENT. Tenant shall pay $1,800 per month, due on the 1st of each month.

3. SECURITY DEPOSIT. Tenant shall pay a deposit of $3,600, which is
   non-refundable under all circumstances.

4. ENTRY. Landlord may enter the premises at any time without prior notice.

5. REPAIRS. Tenant is responsible for all repairs, including structural,
   plumbing, and HVAC systems, at Tenant's sole expense.

6. RENEWAL. This lease renews automatically for another 12 months unless
   Tenant gives notice, at a rent increased by 15%."""


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (r"C:\Windows\Fonts\arial.ttf", "/Library/Fonts/Arial.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    font = _font(24)
    margin, line_h, width = 60, 38, 1000
    lines = TEXT.split("\n")
    height = margin * 2 + line_h * len(lines)

    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        draw.text((margin, margin + i * line_h), line, fill="black", font=font)

    png = OUT_DIR / "scanned-lease.png"
    pdf = OUT_DIR / "scanned-lease.pdf"
    img.save(png)
    img.save(pdf, "PDF", resolution=150.0)  # image-only PDF: no text layer
    print(f"wrote {png}")
    print(f"wrote {pdf}")


if __name__ == "__main__":
    main()
