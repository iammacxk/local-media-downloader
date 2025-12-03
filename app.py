import os
import time
import shutil # เพิ่มตัวช่วยเช็คโปรแกรมในเครื่อง
from flask import Flask, request, send_file, jsonify, render_template
import yt_dlp

app = Flask(__name__, template_folder='templates')

DOWNLOAD_FOLDER = 'downloads'
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

# --- ตั้งค่า Path ของ FFmpeg ---
# ระบบจะเช็คให้อัตโนมัติ:
# 1. เช็คว่ามีโฟลเดอร์ C:\ffmpeg\bin หรือไม่ (สำหรับคนลง manual)
# 2. ถ้าไม่มี จะปล่อยให้ yt-dlp หาในเครื่องเอง (สำหรับคนลง winget)
CUSTOM_FFMPEG_PATH = r"C:\ffmpeg\bin"

def get_ffmpeg_opts():
    # เช็คว่ามีไฟล์ ffmpeg.exe ในโฟลเดอร์ที่ระบุไหม
    if os.path.exists(os.path.join(CUSTOM_FFMPEG_PATH, 'ffmpeg.exe')):
        print(f"Found FFmpeg at custom path: {CUSTOM_FFMPEG_PATH}")
        return {'ffmpeg_location': CUSTOM_FFMPEG_PATH}
    
    # เช็คว่าในเครื่องมี ffmpeg หรือไม่ (ผ่าน Environment Variables)
    if shutil.which('ffmpeg'):
        print("Found FFmpeg in system PATH")
        return {} # ไม่ต้องตั้งค่า path เดี๋ยว yt-dlp หาเจอเอง
        
    print("WARNING: FFmpeg not found! Merging video/audio might fail.")
    return {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download_media():
    data = request.json
    url = data.get('url')
    format_type = data.get('type')

    if not url:
        return jsonify({'error': 'กรุณาใส่ลิงก์'}), 400

    try:
        # เริ่มต้นตั้งค่า yt-dlp
        ydl_opts = {
            'outtmpl': f'{DOWNLOAD_FOLDER}/%(title)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
        }
        
        # เพิ่มการตั้งค่า FFmpeg แบบอัตโนมัติ
        ydl_opts.update(get_ffmpeg_opts())

        if format_type == 'mp3':
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
            ext = '.mp3'
        elif format_type == 'mp4':
            ydl_opts.update({
                # เลือกไฟล์ Video ที่เป็น mp4 และ Audio ที่เป็น m4a (AAC) เพื่อลดปัญหา codec
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best',
                'merge_output_format': 'mp4',
            })
            ext = '.mp4'

        print(f"Processing: {url} as {format_type}...")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            base, _ = os.path.splitext(filename)
            final_filename = base + ext

        return jsonify({
            'success': True,
            'filename': os.path.basename(final_filename),
            'download_url': f'/get-file/{os.path.basename(final_filename)}'
        })

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/get-file/<filename>')
def get_file(filename):
    file_path = os.path.join(DOWNLOAD_FOLDER, filename)
    try:
        return send_file(file_path, as_attachment=True)
    except Exception as e:
        return str(e)

if __name__ == '__main__':
    app.run(debug=True, port=5000)