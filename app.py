from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import os
import tempfile
import logging
import uuid
from werkzeug.utils import secure_filename

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Allowed file extensions
ALLOWED_EXTENSIONS = {'pdf'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('data_scrap.html')

@app.route('/extract-dc', methods=['POST'])
def extract_delivery_challan():
    return extract_document(request, 'delivery_challan')

@app.route('/extract-invoice', methods=['POST'])
def extract_invoice():
    return extract_document(request, 'invoice')

def extract_document(request, doc_type):
    try:
        logger.info(f"Received {doc_type} extraction request")
        
        if 'file' not in request.files:
            logger.error("No file in request")
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        logger.info(f"File received: {file.filename}")
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'Only PDF files are allowed'}), 400
        
        # Create unique filename to avoid conflicts
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, unique_filename)
        
        file.save(temp_path)
        logger.info(f"File saved to: {temp_path}")
        
        try:
            # Import and use the extraction module
            from document_extractor import DocumentExtractor
            extractor = DocumentExtractor()
            result = extractor.extract_document_info(temp_path)
            
            if result:
                return jsonify(result)
            else:
                # Return empty structure when extraction fails
                return jsonify(get_empty_result_structure(doc_type))
                
        except Exception as e:
            logger.error(f"Extraction failed: {str(e)}")
            return jsonify(get_empty_result_structure(doc_type))
            
        finally:
            # Clean up with error handling
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                    logger.info("Temporary file cleaned up")
            except Exception as e:
                logger.warning(f"Could not remove temp file: {e}")
    
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify(get_empty_result_structure('unknown'))

def get_empty_result_structure(doc_type):
    """Return empty result structure with 'Not Available' for all fields"""
    base_structure = {
        'document_type': doc_type.replace('_', ' ').title() if doc_type != 'unknown' else 'Unknown',
        'supplier_name': 'Not Available',
        'gst_no': 'Not Available',
        'document_number': 'Not Available',
        'document_date': 'Not Available',
        'total_amount': 'Not Available',
        'customer_name': 'Not Available',
        'dispatch_mode': 'Not Available',
        'line_items': [],
        'metadata': {
            'addresses': [],
            'contacts': {
                'phones': [],
                'emails': []
            }
        }
    }
    
    # Add document-specific fields
    if doc_type == 'delivery_challan':
        base_structure.update({
            'purpose': 'Not Available',
            'party_dc_number': 'Not Available',
            'party_dc_date': 'Not Available'
        })
    
    return base_structure

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy', 'message': 'Document Extraction API is running'})

if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)
    
    print("Starting Document Extraction Server...")
    print("Access the application at: http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)