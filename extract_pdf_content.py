import os
from PyPDF2 import PdfReader

# Paths to the PDFs
coinfield_path = r"c:\Users\HP USER\Downloads\Telegram Desktop\Coinfield Estate Presentation.pdf"
eximp_path = r"c:\Users\HP USER\Downloads\Telegram Desktop\Eximp & Cloves Brand Book.pdf"

def extract_text_from_pdf(pdf_path):
    """Extract text from all pages of a PDF"""
    try:
        print(f"\n{'='*60}")
        print(f"Reading: {os.path.basename(pdf_path)}")
        print(f"{'='*60}\n")
        
        reader = PdfReader(pdf_path)
        num_pages = len(reader.pages)
        print(f"Total pages: {num_pages}\n")
        
        all_text = []
        for i, page in enumerate(reader.pages, 1):
            text = page.extract_text()
            all_text.append(f"--- PAGE {i} ---\n{text}\n")
            
        return {
            'filename': os.path.basename(pdf_path),
            'num_pages': num_pages,
            'text': '\n'.join(all_text)
        }
    except Exception as e:
        print(f"Error reading {pdf_path}: {e}")
        return None

def main():
    # Extract content from both PDFs
    coinfield_content = extract_text_from_pdf(coinfield_path)
    eximp_content = extract_text_from_pdf(eximp_path)
    
    # Save extracted text for review
    output_file = r"c:\Users\HP USER\Documents\Data Analyst\discord\pdf_extracted_content.txt"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        if coinfield_content:
            f.write(f"\n{'='*80}\n")
            f.write(f"COINFIELD ESTATE PRESENTATION ({coinfield_content['num_pages']} pages)\n")
            f.write(f"{'='*80}\n\n")
            f.write(coinfield_content['text'])
            f.write("\n\n\n")
        
        if eximp_content:
            f.write(f"\n{'='*80}\n")
            f.write(f"EXIMP & CLOVES BRAND BOOK ({eximp_content['num_pages']} pages)\n")
            f.write(f"{'='*80}\n\n")
            f.write(eximp_content['text'])
    
    print(f"\n✅ Content extracted and saved to: {output_file}")

if __name__ == "__main__":
    main()
