from flask import Flask, render_template_string, request, jsonify
import pandas as pd
import os
import shutil
import webbrowser  # 브라우저 실행을 위한 모듈 추가
from threading import Timer

# ======================================================
# 1. 사용자 설정
# ======================================================
KAKAO_JS_KEY = ""
csv_file_path = r"c:"

# ======================================================
# 2. 서버 설정 및 백업
# ======================================================
app = Flask(__name__)
csv_file_path = csv_file_path.replace('"', '').replace("'", "")
backup_file_path = csv_file_path + ".backup"

# 안전장치: 백업 파일 생성
if os.path.exists(csv_file_path):
    if not os.path.exists(backup_file_path):
        shutil.copy(csv_file_path, backup_file_path)

def load_data():
    if not os.path.exists(csv_file_path): return None
    try:
        df = pd.read_csv(csv_file_path, encoding='utf-8-sig')
    except:
        try: df = pd.read_csv(csv_file_path, encoding='cp949')
        except: return None
    df = df.dropna(subset=['latitude', 'longitude'])
    return df

# ======================================================
# 3. 지도 및 Undo 기능 구현
# ======================================================
@app.route('/')
def index():
    df = load_data()
    if df is None: return "❌ CSV 파일을 찾을 수 없습니다."

    positions_js = ""
    for i, row in df.iterrows():
        b_id = row['ID'] if 'ID' in df.columns else i 
        name = str(row['name']).replace("'", "\\'").replace('"', '\\"')
        lat = row['latitude']
        lng = row['longitude']
        if lat == 0 or lng == 0: lat, lng = 36.5, 127.8

        positions_js += f"""
        {{
            id: "{b_id}",
            title: "{name}", 
            latlng: new kakao.maps.LatLng({lat}, {lng})
        }},"""

    center_lat = df[df['latitude'] != 0]['latitude'].mean()
    center_lng = df[df['longitude'] != 0]['longitude'].mean()
    if pd.isna(center_lat): center_lat, center_lng = 36.5, 127.8

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>교량 위치 보정 (실행 취소 기능)</title>
        <style>
            html, body {{ width: 100%; height: 100%; margin: 0; }} 
            #map {{ width: 100%; height: 100%; }}
            .info-box {{ padding:5px; font-size:12px; text-align:center; min-width: 150px; }}
            .btn-undo {{ 
                margin-top: 5px; padding: 4px 8px; background: #ff9800; color: white; 
                border: none; border-radius: 4px; cursor: pointer; font-size: 11px; font-weight: bold;
            }}
            .btn-undo:hover {{ background: #e68900; }}
            .coord-text {{ color: #555; font-size: 11px; margin-bottom: 3px; display:block; }}
        </style>
    </head>
    <body>
        <div id="map"></div>
        <script type="text/javascript" src="//dapi.kakao.com/v2/maps/sdk.js?appkey={KAKAO_JS_KEY}"></script>
        <script>
            var mapContainer = document.getElementById('map'),
                mapOption = {{ center: new kakao.maps.LatLng({center_lat}, {center_lng}), level: 8 }};
            var map = new kakao.maps.Map(mapContainer, mapOption); 
            map.setMapTypeId(kakao.maps.MapTypeId.HYBRID);
            var zoomControl = new kakao.maps.ZoomControl();
            map.addControl(zoomControl, kakao.maps.ControlPosition.RIGHT);

            var positions = [{positions_js}];
            var imageSrc = "https://t1.daumcdn.net/localimg/localimages/07/mapapidoc/markerStar.png"; 

            // 전역 마커 관리 객체
            window.markers = {{}};

            for (var i = 0; i < positions.length; i ++) {{
                createMarker(positions[i]);
            }}

            function createMarker(data) {{
                var imageSize = new kakao.maps.Size(24, 35); 
                var markerImage = new kakao.maps.MarkerImage(imageSrc, imageSize); 
                
                var marker = new kakao.maps.Marker({{
                    map: map, position: data.latlng, title : data.title,
                    image : markerImage, draggable: true
                }});
                
                marker.bridgeId = data.id;

                // [핵심] 이전 좌표 저장용 변수 초기화
                marker.prevLat = data.latlng.getLat();
                marker.prevLng = data.latlng.getLng();

                var iwContent = '<div class="info-box"><strong>' + data.title + '</strong><br>드래그하여 수정</div>';
                var infowindow = new kakao.maps.InfoWindow({{ content: iwContent }});
                
                window.markers[data.id] = {{ marker: marker, info: infowindow }};

                kakao.maps.event.addListener(marker, 'click', function() {{ infowindow.open(map, marker); }});

                // ★ 1. 드래그 시작(dragstart) 시점의 위치를 기억함 (Undo 기준점)
                kakao.maps.event.addListener(marker, 'dragstart', function() {{
                    var curPos = marker.getPosition();
                    marker.prevLat = curPos.getLat();
                    marker.prevLng = curPos.getLng();
                }});

                // ★ 2. 드래그 종료(dragend) 시 업데이트 및 Undo 버튼 표시
                kakao.maps.event.addListener(marker, 'dragend', function() {{
                    var latlng = marker.getPosition();
                    updateLocation(data.id, latlng.getLat(), latlng.getLng(), infowindow);
                }});
            }}

            // ★ 3. 되돌리기(Undo) 함수
            window.undoMarker = function(id) {{
                var item = window.markers[id];
                if(item) {{
                    var lat = item.marker.prevLat; // 기억해둔 직전 좌표
                    var lng = item.marker.prevLng;
                    
                    // 위치 복구
                    var newPos = new kakao.maps.LatLng(lat, lng);
                    item.marker.setPosition(newPos);
                    map.panTo(newPos);

                    // 서버 저장 및 메시지 표시
                    updateLocation(id, lat, lng, item.info, true);
                }}
            }};

            function updateLocation(id, lat, lng, infowindow, isUndo=false) {{
                fetch('/update_location', {{
                    method: 'POST', headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ id: id, latitude: lat, longitude: lng }})
                }}).then(r => r.json()).then(d => {{
                    if (d.status === 'success') {{
                        var msg = isUndo ? "되돌리기 완료! ↩️" : "저장 완료! ✅";
                        var btnHtml = '<button class="btn-undo" onclick="undoMarker(\\'' + id + '\\')">↩ 이전 위치로</button>';
                        
                        // 이미 이전 위치로 돌아갔다면 버튼 숨기기 (선택사항)
                        if(isUndo) btnHtml = ''; 

                        var content = '<div class="info-box"><strong>' + msg + '</strong><br>' +
                                      '<span class="coord-text">' + lat.toFixed(5) + ', ' + lng.toFixed(5) + '</span>' +
                                      btnHtml + '</div>';
                        infowindow.setContent(content);
                        infowindow.open(map, window.markers[id].marker);
                    }} else {{ alert("실패: " + d.message); }}
                }});
            }}
        </script>
    </body>
    </html>
    """
    return render_template_string(html)

@app.route('/update_location', methods=['POST'])
def update_location():
    try:
        data = request.json
        target_id = str(data['id'])
        new_lat = float(data['latitude'])
        new_lng = float(data['longitude'])
        df = load_data()
        df['ID'] = df['ID'].astype(str)
        if target_id in df['ID'].values:
            idx = df[df['ID'] == target_id].index[0]
            df.at[idx, 'latitude'] = new_lat
            df.at[idx, 'longitude'] = new_lng
            df.to_csv(csv_file_path, index=False, encoding='utf-8-sig')
            return jsonify({"status": "success"})
        return jsonify({"status": "error", "message": "ID not found"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

def open_browser():
    # 0.5초 후 지정된 URL로 브라우저를 엽니다.
    webbrowser.open_new("http://127.0.0.1:8000")

if __name__ == '__main__':
    # 서버가 뜨기 전에 브라우저를 먼저 실행시키면 에러가 날 수 있으므로 타이머 사용
    Timer(0.5, open_browser).start()
    
    print("🚀 서버 실행! 잠시 후 브라우저가 자동으로 열립니다.")
    # debug=False로 설정해야 자동 실행 코드가 두 번 중복 실행되지 않습니다.
    app.run(host='0.0.0.0', port=8000, debug=False)