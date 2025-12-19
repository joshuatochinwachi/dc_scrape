import fitz  # PyMuPDF

# Paths to the PDFs
coinfield_path = r"c:\Users\HP USER\Downloads\Telegram Desktop\Coinfield Estate Presentation.pdf"
eximp_path = r"c:\Users\HP USER\Downloads\Telegram Desktop\Eximp & Cloves Brand Book.pdf"

def extract_pdf_content(pdf_path):
    """Extract text from PDF using PyMuPDF"""
    try:
        doc = fitz.open(pdf_path)
        print(f"\n{'='*60}")
        print(f"Reading: {pdf_path.split(chr(92))[-1]}")
        print(f"Pages: {len(doc)}")
        print(f"{'='*60}\n")
        
        content = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            content.append(f"--- PAGE {page_num + 1} ---\n{text}")
        
        doc.close()
        return '\n\n'.join(content)
    except Exception as e:
        print(f"Error: {e}")
        return f"ERROR: {e}"

# Extract both
print("Extracting Coinfield Estate Presentation...")
coinfield_text = extract_pdf_content(coinfield_path)

print("\nExtracting Eximp & Cloves Brand Book...")
eximp_text = extract_pdf_content(eximp_path)

# Save extractions
output_path = r"c:\Users\HP USER\Documents\Data Analyst\discord\pdf_content.txt"
with open(output_path, 'w', encoding='utf-8') as f:
    f.write("="*80 + "\n")
    f.write("COINFIELD ESTATE PRESENTATION\n")
    f.write("="*80 + "\n\n")
    f.write(coinfield_text)
    f.write("\n\n\n")
    f.write("="*80 + "\n")
    f.write("EXIMP & CLOVES BRAND BOOK\n")
    f.write("="*80 + "\n\n")
    f.write(eximp_text)

print(f"\n✅ Content saved to: {output_path}")
