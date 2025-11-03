import re
import os
import logging
import pdfplumber

# Configure logging
logger = logging.getLogger(__name__)

class DocumentExtractor:
    def __init__(self):
        self.supplier_keywords = ['LIMITED', 'LTD', 'PVT', 'PRIVATE', 'CORP', 'CORPORATION', 
                                 'COMPANY', 'CO.', 'ELECTRONICS', 'SOLUTIONS', 'ENTERPRISES',
                                 'INDUSTRIES', 'GROUP', 'WORLDWIDE', 'GLOBAL', 'INTERNATIONAL']
        
    def extract_document_info(self, pdf_path):
        """Extract document information from PDF - returns None if extraction fails"""
        try:
            logger.info(f"Starting extraction for: {pdf_path}")
            
            # Check if file exists
            if not os.path.exists(pdf_path):
                logger.error(f"PDF file not found: {pdf_path}")
                return None
            
            # Extract text from PDF using pdfplumber (no OCR needed)
            try:
                text = self.extract_text_from_pdf(pdf_path)
                
                if not text.strip():
                    logger.error("No text extracted from PDF")
                    return None
                    
            except Exception as e:
                logger.error(f"PDF text extraction failed: {str(e)}")
                return None
            
            # Analyze document structure
            lines = self.clean_text_lines(text.split('\n'))
            
            # Determine document type
            doc_type = self.detect_document_type(text, lines)
            
            # Extract all possible information
            extracted_data = {
                'document_type': doc_type,
                'supplier_name': self.extract_supplier_name(text, lines, doc_type),
                'gst_no': self.extract_gst_number(text),
                'document_number': self.extract_document_number(text, doc_type),
                'document_date': self.extract_document_date(text, doc_type),
                'total_amount': self.extract_total_amount(text),
                'customer_name': self.extract_customer_name(text, lines),
                'dispatch_mode': self.extract_dispatch_mode(text),
                'line_items': self.extract_line_items(text),
                'metadata': self.extract_metadata(text, lines)
            }
            
            # Add document-specific fields
            if doc_type == "Delivery Challan":
                extracted_data.update({
                    'purpose': self.extract_purpose(text),
                    'party_dc_number': self.extract_party_dc_number(text),
                    'party_dc_date': self.extract_party_dc_date(text)
                })
            
            # Clean and validate extracted data
            cleaned_data = self.clean_extracted_data(extracted_data)
            
            logger.info("Extraction completed successfully")
            return cleaned_data
            
        except Exception as e:
            logger.error(f"Extraction error: {str(e)}")
            return None

    def extract_text_from_pdf(self, pdf_path):
        """Extract text from PDF using pdfplumber (no OCR required)"""
        text = ""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            return text
        except Exception as e:
            logger.error(f"pdfplumber extraction failed: {str(e)}")
            return ""
    
    def clean_extracted_data(self, data):
        """Replace None values with 'Not Available' and clean the data"""
        cleaned = {}
        for key, value in data.items():
            if value is None:
                cleaned[key] = 'Not Available'
            elif isinstance(value, dict):
                cleaned[key] = self.clean_extracted_data(value)
            elif isinstance(value, list):
                cleaned[key] = value if value else []
            elif isinstance(value, str) and not value.strip():
                cleaned[key] = 'Not Available'
            else:
                cleaned[key] = value
        return cleaned
    
    def clean_text_lines(self, lines):
        """Clean and filter text lines"""
        cleaned = []
        for line in lines:
            line = line.strip()
            if line and len(line) > 2:
                cleaned.append(line)
        return cleaned
    
    def detect_document_type(self, text, lines):
        """Detect document type"""
        text_upper = text.upper()
        
        if any(word in text_upper for word in ['DELIVERY CHALLAN', 'DC NO', 'CHALLAN NO']):
            return "Delivery Challan"
        elif any(word in text_upper for word in ['TAX INVOICE', 'GST INVOICE']):
            return "Tax Invoice"
        elif any(word in text_upper for word in ['INVOICE', 'INV NO', 'BILL NO']):
            return "Invoice"
        
        return "Unknown Document"
    
    def extract_supplier_name(self, text, lines, doc_type):
        """Extract supplier name"""
        # Look for company names in the first few lines
        for i, line in enumerate(lines[:10]):
            line_upper = line.upper()
            # Check if line contains business keywords
            if (any(keyword in line_upper for keyword in self.supplier_keywords) and 
                len(line) > 5 and 
                not any(exclude in line_upper for exclude in ['GST', 'INVOICE', 'CHALLAN', 'DATE', 'TO:'])):
                return line.strip()
        
        # Alternative: Look for lines before GST information
        for i, line in enumerate(lines):
            if 'GST' in line.upper():
                if i > 0 and len(lines[i-1]) > 5:
                    return lines[i-1].strip()
        
        return None
    
    def extract_gst_number(self, text):
        """Extract GST number"""
        patterns = [
            r'GST[:\-\s]*NO[:\-\s]*([0-9A-Z]{15})',
            r'GSTIN[:\-\s]*([0-9A-Z]{15})',
            r'GST[:\-\s]*([0-9A-Z]{15})',
            r'([0-9A-Z]{2}[0-9A-Z]{13})'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                gst_no = match.strip()
                if len(gst_no) == 15 and gst_no.isalnum():
                    return gst_no
        return None
    
    def extract_document_number(self, text, doc_type):
        """Extract document number"""
        if doc_type == "Delivery Challan":
            patterns = [
                r'DC\s*NO[:\-\s]*([A-Z0-9\/\-\._]+)',
                r'DELIVERY\s*CHALLAN\s*NO[:\-\s]*([A-Z0-9\/\-\._]+)',
                r'CHALLAN\s*NO[:\-\s]*([A-Z0-9\/\-\._]+)'
            ]
        else:
            patterns = [
                r'INVOICE\s*NO[:\-\s]*([A-Z0-9\/\-\._]+)',
                r'INV\s*NO[:\-\s]*([A-Z0-9\/\-\._]+)',
                r'BILL\s*NO[:\-\s]*([A-Z0-9\/\-\._]+)'
            ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                doc_no = match.group(1).strip()
                if 3 <= len(doc_no) <= 50:
                    return doc_no
        return None
    
    def extract_document_date(self, text, doc_type):
        """Extract document date"""
        patterns = [
            r'DC\s*DATE[:\-\s]*([\d]{1,2}[\/\-\.][\d]{1,2}[\/\-\.][\d]{2,4})',
            r'INVOICE\s*DATE[:\-\s]*([\d]{1,2}[\/\-\.][\d]{1,2}[\/\-\.][\d]{2,4})',
            r'DATE[:\-\s]*([\d]{1,2}[\/\-\.][\d]{1,2}[\/\-\.][\d]{2,4})'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                date_str = match.strip()
                if self._validate_date(date_str):
                    return date_str
        return None
    
    def _validate_date(self, date_str):
        """Validate date format"""
        try:
            return bool(re.match(r'^\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}$', date_str))
        except:
            return False
    
    def extract_total_amount(self, text):
        """Extract total amount"""
        patterns = [
            r'TOTAL[:\-\s]*[\$?€]?\s*([\d,]+\.?\d{0,2})',
            r'GRAND\s*TOTAL[:\-\s]*[\$?€]?\s*([\d,]+\.?\d{0,2})',
            r'TOTAL\s*VALUE[:\-\s]*[\$?€]?\s*([\d,]+\.?\d{0,2})'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                amount = match.strip().replace(',', '')
                if self._validate_amount(amount):
                    return amount
        return None
    
    def _validate_amount(self, amount):
        """Validate amount"""
        try:
            float_amount = float(amount)
            return 0 < float_amount < 1000000000
        except:
            return False
    
    def extract_customer_name(self, text, lines):
        """Extract customer name"""
        patterns = [
            r'TO[:\-\s]*\n?\s*([^\n]+)',
            r'BILL\s*TO[:\-\s]*\n?\s*([^\n]+)',
            r'CUSTOMER[:\-\s]*\n?\s*([^\n]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                customer = match.group(1).strip()
                # Clean up customer name
                customer = re.sub(r'^\s*(M/s|M/s\.|M/s\s|TO\s*:)\s*', '', customer, flags=re.IGNORECASE)
                if customer and len(customer) > 3:
                    return customer
        return None
    
    def extract_dispatch_mode(self, text):
        """Extract dispatch mode"""
        patterns = [
            r'THROUGH[:\-\s]*([^\n]+)',
            r'DISPATCH\s*MODE[:\-\s]*([^\n]+)',
            r'BY\s*([^\n,]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                mode = match.group(1).strip()
                if mode and len(mode) > 2:
                    return mode
        return None
    
    def extract_line_items(self, text):
        """Extract line items"""
        items = []
        lines = text.split('\n')
        
        # Look for product/quantity patterns
        for line in lines:
            if (re.search(r'\d+[,.]?\d*\s*(NOS|PCS|UNITS|QTY)', line.upper()) and
                len(line) > 10 and 
                not any(word in line.upper() for word in ['TOTAL', 'SUBTOTAL', 'GRAND']) and
                re.search(r'[A-Za-z]', line)):
                items.append(line.strip())
        
        return items if items else []
    
    def extract_metadata(self, text, lines):
        """Extract metadata"""
        metadata = {
            'addresses': self._extract_addresses(lines),
            'contacts': self._extract_contacts(text)
        }
        return metadata
    
    def _extract_addresses(self, lines):
        """Extract addresses"""
        addresses = []
        address_keywords = ['ROAD', 'STREET', 'AVENUE', 'LANE', 'POST', 'PIN', 'CITY', 'STATE']
        
        for line in lines:
            if any(keyword in line.upper() for keyword in address_keywords):
                addresses.append(line.strip())
        
        return addresses if addresses else []
    
    def _extract_contacts(self, text):
        """Extract contacts"""
        contacts = {'phones': [], 'emails': []}
        
        # Extract phone numbers
        phone_pattern = r'[\+\(]?[1-9][0-9 .\-\(\)]{8,}[0-9]'
        phones = re.findall(phone_pattern, text)
        if phones:
            contacts['phones'] = phones[:3]  # Limit to first 3 numbers
        
        # Extract email addresses
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, text)
        if emails:
            contacts['emails'] = emails[:3]  # Limit to first 3 emails
        
        return contacts
    
    # Delivery Challan specific methods
    def extract_purpose(self, text):
        patterns = [
            r'PURPOSE[:\-\s]*([^\n]+)'
        ]
        return self._extract_with_patterns(patterns, text)
    
    def extract_party_dc_number(self, text):
        patterns = [
            r'PARTY\s*DC[:\-\s]*([A-Z0-9\/\-\._]+)',
            r'PARTY\s*DC\s*NO[:\-\s]*([A-Z0-9\/\-\._]+)'
        ]
        return self._extract_with_patterns(patterns, text)
    
    def extract_party_dc_date(self, text):
        patterns = [
            r'PARTY\s*DC\s*DATE[:\-\s]*([\d]{1,2}[\/\-\.][\d]{1,2}[\/\-\.][\d]{2,4})'
        ]
        return self._extract_with_patterns(patterns, text)
    
    def _extract_with_patterns(self, patterns, text):
        """Helper method to extract with multiple patterns"""
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None