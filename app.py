from flask import Flask, request, jsonify, render_template
import ocrmypdf
import PyPDF2
import pdfplumber
import re
import tempfile
import os
from datetime import datetime
from pdf2image import convert_from_path
import pytesseract

app = Flask(__name__)

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ---------- Helper Functions ----------

def is_image_pdf(pdf_path):
    """Check if PDF is image-based."""
    try:
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            text = "".join(page.extract_text() or "" for page in reader.pages)
            return len(text.strip()) / len(reader.pages) < 30
    except Exception as e:
        print(f"Error checking PDF: {e}")
        return True


def perform_ocr(input_path, output_path):
    """Convert image PDF to searchable PDF."""
    try:
        ocrmypdf.ocr(
            input_path, output_path,
            language='eng',
            deskew=True,
            optimize=0,
            force_ocr=True,
            progress_bar=False
        )
        return True
    except Exception as e:
        print(f"OCR failed: {e}")
        return False


def extract_text_from_pdf(pdf_path):
    """Extract text using pdfplumber."""
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                try:
                    text += page.extract_text() or ""
                except Exception as e:
                    print(f"Warning: Failed to extract page {i + 1}: {e}")
    except Exception as e:
        print(f"Error opening PDF: {e}")
    return text


def extract_gst_number(text):
    """Extract GST number (handles all label variations)."""
    text = text.replace("\n", " ").replace("\r", " ").lower()
    gst_labels = [
        r'gstin', r'gst\s*no', r'gst\s*number', r'gst\s*#',
        r'gst\s*num', r'gst\s*registration\s*no'
    ]
    gst_pattern = r'\b\d{2}[a-z0-9]{10}[a-z0-9]{3}\b'
    combined_pattern = r'(' + '|'.join(gst_labels) + r')\s*[:\-]?\s*' + gst_pattern
    match = re.search(combined_pattern, text, re.IGNORECASE)
    if match:
        gst_match = re.search(gst_pattern, match.group(0), re.IGNORECASE)
        if gst_match:
            return gst_match.group(0).upper()
    fallback_match = re.search(gst_pattern, text, re.IGNORECASE)
    if fallback_match:
        return fallback_match.group(0).upper()
    return None


def extract_supplier_info(text):
    """Extract supplier name and GST intelligently, skipping irrelevant headers."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    supplier_name = None
    gst_number = None

    # Find GST number first
    for i, line in enumerate(lines):
        gst_match = re.search(r'GST\s*No[:\-]?\s*([A-Z0-9]{15})', line, re.IGNORECASE)
        if gst_match:
            gst_number = gst_match.group(1).strip()

            # Look up a few lines above GST for supplier name candidates
            for j in range(max(0, i - 4), i):
                candidate = lines[j].strip()
                # Skip common junk headers or invalid lines
                if any(word in candidate.upper() for word in [
                    "FORM", "DELIVERY", "CHALLAN", "RETURNABLE", "PARTY",
                    "DC", "DATE", "TO", "PURPOSE", "NO", "REV"
                ]):
                    continue
                # If line looks like a valid supplier name (contains letters, not mostly digits/symbols)
                if re.search(r'[A-Za-z]{3,}', candidate) and len(candidate) > 5:
                    supplier_name = candidate
                    break
            break

    # Fallback: If still not found, search top 10 lines for company-like lines
    if not supplier_name:
        for line in lines[:10]:
            if (
                re.search(r'(LTD|LIMITED|PVT|PRIVATE|INDUSTRIES|ENTERPRISES|PLANT|CORP|COMPANY)', line, re.IGNORECASE)
                and not any(word in line.upper() for word in ["TO", "DELIVERY", "CHALLAN", "RETURNABLE"])
            ):
                supplier_name = line.strip()
                break

    # Final cleanup — remove unwanted chars and isolated trailing letters
    if supplier_name:
        # Remove junk characters at start
        supplier_name = re.sub(r'^[^A-Za-z]+', '', supplier_name)
        # Remove junk characters at end
        supplier_name = re.sub(r'[^A-Za-z0-9\s\-\)&]+$', '', supplier_name)
        supplier_name = supplier_name.strip()

        # If ends with a single meaningless letter (like 'q', 'x', etc.)
        if re.search(r'\b[a-zA-Z]$', supplier_name):
            supplier_name = supplier_name[:-1].strip()

    return supplier_name, gst_number


def parse_common_data(text):
    """Extract structured info from text."""
    data = {
        'document_number': re.search(r'(?:Invoice|Challan|DC|Bill|Document)[\s]*No[:\s]*([^\n]+)', text, re.IGNORECASE),
        'document_date': re.search(r'(?:Date|Dated|Invoice Date|Bill Date)[:\s]*([^\n]+)', text, re.IGNORECASE),
    }

    return {
        'document_number': data['document_number'].group(1).strip() if data['document_number'] else 'Not Available',
        'document_date': data['document_date'].group(1).strip() if data['document_date'] else 'Not Available',
        'gst_no': extract_gst_number(text) or 'Not Available',
    }


# ---------- Routes ----------

@app.route('/')
def index():
    return render_template('data_scrap.html')


@app.route('/extract', methods=['POST'])
def extract_data():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    input_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(input_path)

    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_output:
        output_path = temp_output.name

    try:
        needs_ocr = is_image_pdf(input_path)
        if needs_ocr:
            perform_ocr(input_path, output_path)
            pdf_to_use = output_path
        else:
            pdf_to_use = input_path

        # Extract text
        text = extract_text_from_pdf(pdf_to_use)

        # Extract data
        supplier_name, gst_number = extract_supplier_info(text)
        parsed_data = parse_common_data(text)

        # Merge intelligently (prefer supplier GST if both found)
        if gst_number and gst_number != "Not Available":
            parsed_data['gst_no'] = gst_number
        parsed_data['supplier_name'] = supplier_name or "Not Available"

        # Render HTML result
        return render_template('data_scrap.html', extracted_data=parsed_data)

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        try:
            if os.path.exists(output_path):
                os.unlink(output_path)
        except:
            pass


if __name__ == '__main__':
    app.run(debug=True, port=5000)