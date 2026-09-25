import sys
from split_by_student import analyze_front_pages

pdf_path = sys.argv[1] if len(sys.argv) > 1 else "final student list/_continuous.pdf"
tessdata_dir = sys.argv[2] if len(sys.argv) > 2 else "tessdata"

analysis = analyze_front_pages(pdf_path, tessdata_dir=tessdata_dir)
for e in analysis:
    if e["is_front"]:
        print(e["page_idx"], round(e["ink_frac"], 4), repr(e["name_text"]))
