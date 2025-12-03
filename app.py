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
            # --- แก้ไขใหม่: บังคับเลือกไฟล์แบบ H.264 (AVC) แบบเข้มข้น ---
            if 'tiktok.com' in url:
                # TikTok: ตัด /best ทิ้ง เพื่อไม่ให้หลุดไปเอา HEVC มาเด็ดขาด
                # บังคับหาเฉพาะที่มี codec เป็น avc หรือ h264 เท่านั้น
                ydl_opts.update({
                    'format': 'best[vcodec^=avc]/best[vcodec^=h264]/best[vcodec!^=hevc][vcodec!^=hvc1]',
                })
            else:
                # YouTube/Other: บังคับหา Video ที่เป็น AVC (h264) + Audio AAC
                ydl_opts.update({
                    'format': 'bestvideo[vcodec^=avc]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                    'merge_output_format': 'mp4',
                })
            ext = '.mp4'

        print(f"Processing: {url} as {format_type}...")
        
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