import os
import time
from flask import Flask, request, send_file, jsonify, render_template
import yt_dlp

app = Flask(__name__, template_folder='templates')

# โฟลเดอร์สำหรับเก็บไฟล์ชั่วคราว
DOWNLOAD_FOLDER = 'downloads'
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download_media():
    data = request.json
    url = data.get('url')
    format_type = data.get('type') # 'mp3' หรือ 'mp4'

    if not url:
        return jsonify({'error': 'กรุณาใส่ลิงก์'}), 400

    try:
        # การตั้งค่า yt-dlp
        ydl_opts = {
            'outtmpl': f'{DOWNLOAD_FOLDER}/%(title)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
        }

        if format_type == 'mp3':
            ydl_opts.update({
                'format': 'bestaudio/best', # เอาเสียงที่ดีที่สุด
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192', # หรือ 320 ถ้าต้องการสูงสุด
                }],
            })
        elif format_type == 'mp4':
            # โหลดวิดีโอที่ดีที่สุด + เสียงที่ดีที่สุด แล้วรวมกัน (ต้องมี FFmpeg)
            ydl_opts.update({
                'format': 'bestvideo+bestaudio/best',
                'merge_output_format': 'mp4',
            })

        print(f"Processing: {url} as {format_type}...")
        
        # เริ่มดาวน์โหลด
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            # ปรับชื่อไฟล์ให้ตรงกับผลลัพธ์หลังแปลงไฟล์
            if format_type == 'mp3':
                final_filename = os.path.splitext(filename)[0] + '.mp3'
            else:
                final_filename = os.path.splitext(filename)[0] + '.mp4'

        # ส่งไฟล์กลับไปให้ User
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
    # ส่งไฟล์และสั่งลบหลังจากส่งเสร็จ (อาจจะต้องใช้ background task ในงานจริง แต่แบบนี้ง่ายสุดสำหรับ local)
    file_path = os.path.join(DOWNLOAD_FOLDER, filename)
    try:
        return send_file(file_path, as_attachment=True)
    except Exception as e:
        return str(e)

if __name__ == '__main__':
    # รันบน localhost port 5000
    app.run(debug=True, port=5000)