from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from demo import Hand
from PIL import Image
import os
import shutil
import string
import random
import textwrap
import math
import time
from svg2png import svg2png, fulltrim
from resourcepath import resourcepath

app = Flask(__name__)
CORS(app)

class HandwritingGenerator:
    def __init__(self):
        self.hand = None
        self.valid_chars = ["'", '6', 'G', 'b', ')', 'I', '0', 'O', 'c', '9', 'L', '8', 't', 'q', 's', '\x00', 'U', 'S', 'W', 'a', 'k', '2', 'B', 'M', '7', 'T', 'g', 'f', 'F', 'P', 'l', 'E', 'v', 'y', 'j', 'Y', 'J', '-', 'R', '!', '#', '.', 'o', 'r', '?', 'C', "'", '5', 'm', 'h', '4', 'A', 'u', 'p', 'w', 'n', '(', 'V', 'd', '1', ',', 'H', 'i', 'x', ';', ':', 'z', 'K', '3', 'N', ' ', 'D', 'e', '\n']
    
    def validate_text(self, text):
        """Validasi karakter dalam text"""
        for letter in list(text):
            if letter not in self.valid_chars:
                return False, letter
        return True, None
    
    def split_string(self, text, length):
        """Split text menjadi beberapa baris"""
        return textwrap.wrap(text, length)
    
    def safe_rmtree(self, directory, retries=3, delay=0.3):
        """Hapus directory dengan retry jika ada PermissionError"""
        for i in range(retries):
            try:
                shutil.rmtree(directory)
                return True
            except PermissionError as e:
                if i < retries - 1:
                    print(f"PermissionError saat menghapus {directory}, mencoba lagi... ({i+1}/{retries})")
                    time.sleep(delay)
                else:
                    print(f"Warning: Tidak dapat menghapus {directory} setelah {retries} percobaan: {e}")
                    return False
            except Exception as e:
                print(f"Error saat menghapus {directory}: {e}")
                return False
        return False
    
    def add_justified_spacing(self, text, target_length):
        """Tambahkan spasi ekstra untuk justified alignment"""
        words = text.split()
        if len(words) <= 1:
            return text
        
        # Hitung jumlah spasi yang dibutuhkan
        current_length = len(text)
        spaces_needed = target_length - current_length
        gaps = len(words) - 1
        
        if gaps <= 0 or spaces_needed <= 0:
            return text
        
        # Distribusikan spasi ekstra
        base_spaces = spaces_needed // gaps
        extra_spaces = spaces_needed % gaps
        
        result = []
        for i, word in enumerate(words):
            result.append(word)
            if i < len(words) - 1:
                # Tambahkan 1 spasi normal + spasi tambahan
                spaces = 1 + base_spaces + (1 if i < extra_spaces else 0)
                result.append(' ' * spaces)
        
        return ''.join(result)
    
    def generate(self, text, legibility=50, stroke_width=5, style=0, 
                 stroke_color='#0047AB', orientation='Left', 
                 max_line_width=42.5, line_spacing=80):
        """Generate handwriting dari text"""
        
        # Validasi text
        if not text or len("".join(text.split())) == 0:
            return {'error': 'No text provided'}, 400
        
        text = text.replace('Q', 'q').replace('X', 'x')
        is_valid, invalid_char = self.validate_text(text)
        if not is_valid:
            return {'error': f'Invalid character found: {invalid_char}'}, 400
        
        # Initialize hand jika belum
        if not self.hand:
            self.hand = Hand()
        
        # Hitung parameter
        bias = math.sqrt(legibility / 100)
        width = stroke_width / 4 + 0.6
        
        # Split text menjadi lines
        lines = text.splitlines()
        
        # Buat temp directory dengan path yang benar
        temp_dir = resourcepath('handsynth-temp')
        
        # Hapus directory lama jika ada (dengan safe method)
        if os.path.isdir(temp_dir):
            self.safe_rmtree(temp_dir)
            time.sleep(0.1)
        
        # Buat directory baru
        os.makedirs(temp_dir, exist_ok=True)
        
        # Process lines
        synthesized_lines = []
        original_lengths = []  # Simpan panjang asli untuk justified
        
        for line in lines:
            if len(line) > round(max_line_width):
                sublines = self.split_string(line, round(max_line_width))
                synthesized_lines.extend(sublines)
                original_lengths.extend([round(max_line_width)] * len(sublines))
            else:
                synthesized_lines.append(line if line else ' ')
                original_lengths.append(len(line))
        
        # Untuk justified: modifikasi text dengan spasi ekstra
        lines_to_generate = synthesized_lines.copy()
        if orientation == 'Justify':
            max_len = round(max_line_width)
            for i, line in enumerate(synthesized_lines):
                # Jangan justify baris terakhir atau baris pendek
                is_last = (i == len(synthesized_lines) - 1)
                is_short = len(line.strip()) < max_len * 0.7
                
                if not is_last and not is_short and len(line.strip()) > 0:
                    lines_to_generate[i] = self.add_justified_spacing(line, max_len)
        
        # Generate SVG untuk setiap line
        for i, line in enumerate(lines_to_generate):
            svg_path = os.path.join(temp_dir, f'{i}.svg')
            self.hand.write(
                filename=svg_path,
                lines=[line],
                biases=[bias],
                styles=[style],
                stroke_colors=[stroke_color],
                stroke_widths=[width],
            )
        
        # Convert SVG ke PNG
        for i in range(len(lines_to_generate)):
            svg_path = os.path.join(temp_dir, f'{i}.svg')
            png_path = os.path.join(temp_dir, f'{i}.png')
            
            if lines_to_generate[i].strip() == '':
                blank_img = Image.new('RGBA', (2000, 120))
                blank_img.save(png_path)
                blank_img.close()
            else:
                svg2png(svg_path, png_path)
        
        # Combine lines
        line_spacing_val = round(line_spacing)
        canvas = Image.new('RGBA', (2400, 400 + round(line_spacing_val * len(lines_to_generate))))
        
        # List untuk menyimpan image objects yang perlu ditutup
        opened_images = []
        
        for i in range(len(lines_to_generate)):
            png_path = os.path.join(temp_dir, f'{i}.png')
            line_image = Image.open(png_path)
            opened_images.append(line_image)
            
            _, _, _, mask = line_image.split()
            
            if orientation == 'Left':
                canvas.paste(line_image, (400, line_spacing_val * (i + 1)), mask)
            elif orientation == 'Right':
                canvas.paste(line_image, (2000 - line_image.width, line_spacing_val * (i + 1)), mask)
            elif orientation == 'Middle':
                canvas.paste(line_image, (int(1000 - (line_image.width / 2)), line_spacing_val * (i + 1)), mask)
            elif orientation == 'Justify':
                # Semua baris justified dimulai dari posisi yang sama (kiri)
                canvas.paste(line_image, (400, line_spacing_val * (i + 1)), mask)
        
        # Tutup semua opened images sebelum cleanup
        for img in opened_images:
            img.close()
        
        canvas = fulltrim(canvas)
        finalcanvas = Image.new('RGBA', (canvas.width + 120, canvas.height + 120))
        finalcanvas.paste(canvas, (60, 60))
        
        whitecanvas = Image.new('RGB', (canvas.width + 120, canvas.height + 120), color='white')
        _, _, _, mask = finalcanvas.split()
        whitecanvas.paste(finalcanvas, (0, 0), mask=mask)
        
        # Save output
        if not os.path.isdir('outputs'):
            os.makedirs('outputs', exist_ok=True)
        
        fileid = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6))
        alpha_path = os.path.join('outputs', f'{fileid}-alpha.png')
        white_path = os.path.join('outputs', f'{fileid}-white.png')
        
        finalcanvas.save(alpha_path)
        whitecanvas.save(white_path)
        
        # Tutup canvas sebelum cleanup
        canvas.close()
        finalcanvas.close()
        whitecanvas.close()
        
        # Cleanup dengan delay dan retry
        time.sleep(0.2)
        self.safe_rmtree(temp_dir)
        
        return {
            'success': True,
            'file_id': fileid,
            'alpha_path': alpha_path,
            'white_path': white_path
        }, 200

# Instance generator
generator = HandwritingGenerator()

@app.route('/api/generate', methods=['POST'])
def generate_handwriting():
    """
    API endpoint untuk generate handwriting
    
    Body JSON:
    {
        "text": "Hello World",
        "legibility": 50,  // 0-100
        "stroke_width": 5,  // 0-10
        "style": 0,  // 0-11
        "stroke_color": "#0047AB",
        "orientation": "Left",  // Left/Middle/Right/Justified
        "max_line_width": 42.5,  // 10-75
        "line_spacing": 80  // 20-140
    }
    """
    data = request.json
    
    result, status = generator.generate(
        text=data.get('text', ''),
        legibility=data.get('legibility', 50),
        stroke_width=data.get('stroke_width', 5),
        style=data.get('style', 0),
        stroke_color=data.get('stroke_color', '#0047AB'),
        orientation=data.get('orientation', 'Left'),
        max_line_width=data.get('max_line_width', 42.5),
        line_spacing=data.get('line_spacing', 80)
    )
    
    return jsonify(result), status

@app.route('/api/download/<file_id>/<bg_type>', methods=['GET'])
def download_file(file_id, bg_type):
    """
    Download generated image
    bg_type: 'alpha' atau 'white'
    """
    filename = os.path.join('outputs', f'{file_id}-{bg_type}.png')
    if os.path.exists(filename):
        return send_file(filename, mimetype='image/png')
    return jsonify({'error': 'File not found'}), 404

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'OK', 'message': 'Handwriting API is running'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)