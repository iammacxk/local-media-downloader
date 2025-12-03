import os
import time
import shutil
from flask import Flask, request, send_file, jsonify, render_template
import yt_dlp

app = Flask(__name__, template_folder='templates')

DOWNLOAD_FOLDER = 'downloads'
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

# --- ตั้งค่า Path ของ FFmpeg ---
CUSTOM_FFMPEG_PATH = r"C:\ffmpeg\bin"

def get_ffmpeg_opts():
    if os.path.exists(os.path.join(CUSTOM_FFMPEG_PATH, 'ffmpeg.exe')):
        print(f"Found FFmpeg at custom path: {CUSTOM_FFMPEG_PATH}")
        return {'ffmpeg_location': CUSTOM_FFMPEG_PATH}
    
    if shutil.which('ffmpeg'):
        print("Found FFmpeg in system PATH")
        return {} 
        
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
        ydl_opts = {
            'outtmpl': f'{DOWNLOAD_FOLDER}/%(id)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            # --- 🚀 HYPER SPEED SETTINGS (MAX POWER) ---
            'concurrent_fragment_downloads': 32, # เพิ่มท่อส่งข้อมูลเป็น 32 ท่อ (ดึงเต็มสปีด)
            'http_chunk_size': 10485760 * 2,     # รับข้อมูลทีละ 20MB
            'buffersize': 1024 * 1024 * 4,       # Buffer 4MB (ลดการเขียน Disk ถี่เกินไป)
            'retries': 30,                       # พยายามใหม่ 30 ครั้งถ้าหลุด
            'fragment_retries': 30,
            'file_access_retries': 10,
            # ------------------------------
        }
        
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
            # --- 🌍 UNIVERSAL COMPATIBILITY MODE ---
            # รวม Logic เพื่อรองรับทุก Player (YouTube, FB, IG, TikTok, Vimeo, X, etc.)
            # โดยยังคงกฎเหล็กคือ "พยายามหลีกเลี่ยง HEVC" เพื่อให้เปิดบน Windows ได้
            
            universal_format_rule = (
                'bestvideo[vcodec^=avc]+bestaudio[ext=m4a]/'  # 1. YouTube/Adaptive: ภาพ AVC + เสียง M4A (ดีสุด)
                'bestvideo[vcodec^=h264]+bestaudio[ext=m4a]/' # 2. เหมือนข้อ 1 แต่ชื่อ codec ต่างกัน
                'best[vcodec^=avc]/'                          # 3. Single File: เว็บทั่วไป/TikTok ที่เป็น AVC
                'best[vcodec^=h264]/'                         # 4. Single File: เว็บทั่วไป/TikTok ที่เป็น H264
                'best[ext=mp4][vcodec!^=hevc][vcodec!^=hvc1]/' # 5. ไฟล์ MP4 ทั่วไป (ที่ไม่ใช่ HEVC)
                'best[vcodec!^=hevc][vcodec!^=hvc1]/'          # 6. ไฟล์อะไรก็ได้ (ที่ไม่ใช่ HEVC)
                'best'                                         # 7. (Last Resort) ถ้าไม่มีทางเลือกอื่นจริงๆ เอามาเถอะ
            )

            ydl_opts.update({
                'format': universal_format_rule,
                'merge_output_format': 'mp4',
            })
            ext = '.mp4'

        print(f"Processing: {url} as {format_type} (Hyper Speed Mode)...")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_id = info.get('id', 'video')
            video_title = info.get('title', 'video')
            
            filename_on_disk = f"{file_id}{ext}"
            
        safe_title = "".join([c for c in video_title if c not in r'<>:"/\|?*'])
        download_filename = f"{safe_title}{ext}"

        from urllib.parse import quote
        encoded_title = quote(download_filename)

        return jsonify({
            'success': True,
            'filename': filename_on_disk,
            'download_url': f'/get-file/{filename_on_disk}?title={encoded_title}'
        })

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/get-file/<filename>')
def get_file(filename):
    file_path = os.path.join(DOWNLOAD_FOLDER, filename)
    user_filename = request.args.get('title')
    if not user_filename:
        user_filename = filename

    try:
        return send_file(file_path, as_attachment=True, download_name=user_filename)
    except Exception as e:
        return str(e)

if __name__ == '__main__':
    app.run(debug=True, port=5000)