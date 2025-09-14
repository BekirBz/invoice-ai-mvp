import pytesseract
from pdf2image import convert_from_path
from PIL import Image

# 1. Basit image OCR testi
text = pytesseract.image_to_string(Image.open("sample_invoice.png"))
print("OCR from image:\n", text)

# 2. PDF -> Image -> OCR testi
pages = convert_from_path("sample_invoice.pdf", 300)  # 300 DPI
for i, page in enumerate(pages):
    text = pytesseract.image_to_string(page)
    print(f"OCR from PDF page {i+1}:\n", text)