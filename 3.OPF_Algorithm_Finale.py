import pandas as pd
import requests
import datetime
import sys
import os
import json
import http.server
import socketserver
import webbrowser
import threading
import concurrent.futures
import math
import random
import itertools
import time

# ==========================================
# 1. 설정 및 초기화
# ==========================================
KAKAO_REST_KEY = ""        # 발급 받은 REST API 키 입력
KAKAO_JS_KEY = ""        # 발급 받은 JavsScript 키 입력

CSV_FILE_NAME = ""        # 최종 입력 데이터 csv 파일 이름 (예: Final_Bridges.csv)
OFFICE_NAME = "사무실"
OFFICE_ADDRESS = "서울 동작구 보라매로5가길 24"
WORK_LIMIT_HOURS = 8 
HTML_FILE = "kakao_map_battle_visual.html"
PORT = 8000


USE_API_CACHE = True      # True : API 절약을 위한 저장, False : 무조건 API 새로 받기
CACHE_FILE_NAME = "route_cache.json"

DAILY_COLORS = [
    '#0000FF', '#FF0000', '#008000', '#800080', '#FFA500', '#000000', "#F005B5"
]

# ==========================================
# 2. 캐시 관리 및 API 함수
# ==========================================
def load_cache():
    if not USE_API_CACHE: return {}
    if os.path.exists(CACHE_FILE_NAME):
        try:
            with open(CACHE_FILE_NAME, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return {}
    return {}

def save_cache(cache_data):
    if not USE_API_CACHE: return
    try:
        with open(CACHE_FILE_NAME, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=4)
    except: pass

route_cache = load_cache()

def get_coordinate(address):
    url = "https://dapi.kakao.com/v2/local/search/address.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_REST_KEY}"}
    try:
        resp = requests.get(url, headers=headers, params={"query": address})
        doc = resp.json()['documents'][0]
        return f"{doc['x']},{doc['y']}"
    except: return None

def get_kakao_route_data(origin, destination, departure_time=None):
    cache_key = f"{origin}|{destination}"
    if origin == destination: return 0, []
    
    if USE_API_CACHE and cache_key in route_cache:
        data = route_cache[cache_key]
        return data.get('time', data.get('duration', 0)), data['path']

    url = "https://apis-navi.kakaomobility.com/v1/directions"
    headers = {"Authorization": f"KakaoAK {KAKAO_REST_KEY}"}
    params = {"origin": origin, "destination": destination, "priority": "RECOMMEND", "car_type": 1}
    if departure_time: params["departure_time"] = departure_time
    
    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200 and departure_time:
            del params["departure_time"]
            response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 200:
            result = response.json()
            routes = result.get('routes')
            if routes:
                summary = routes[0]['summary']
                duration = summary['duration']
                path_data = [] 
                for section in routes[0]['sections']:
                    for road in section['roads']:
                        vertexes = road['vertexes']
                        for i in range(0, len(vertexes), 2):
                            path_data.append({'lng': vertexes[i], 'lat': vertexes[i+1]})
                
                if USE_API_CACHE:
                    route_cache[cache_key] = {'time': duration, 'path': path_data}
                return duration, path_data
    except Exception as e: pass
    return 0, []

def get_route_wrapper(args):
    start_node, end_node, departure_time_str = args
    sec, path = get_kakao_route_data(start_node['coord'], end_node['coord'], departure_time_str)
    cache_key = f"{start_node['coord']}|{end_node['coord']}"
    return (start_node['id'], end_node['id']), {'time': sec, 'path': path}, cache_key

def build_od_matrix(nodes, start_datetime_str):
    n = len(nodes)
    matrix = {} 
    print(f"\n   📡 [데이터 수집] 카카오 API 교통정보 스캔 중...")
    
    tasks = []
    total_pairs = n * (n-1)
    for i in range(n):
        for j in range(n):
            if i == j: 
                matrix[(nodes[i]['id'], nodes[j]['id'])] = {'time': 0, 'path': []}
                continue
            key = f"{nodes[i]['coord']}|{nodes[j]['coord']}"
            if USE_API_CACHE and key in route_cache:
                data = route_cache[key]
                matrix[(nodes[i]['id'], nodes[j]['id'])] = {'time': data.get('time', data.get('duration', 0)), 'path': data['path']}
            else:
                tasks.append((nodes[i], nodes[j], start_datetime_str))

    cached_count = total_pairs - len(tasks)
    print(f"      ✅ 캐시된 데이터: {cached_count}건 / 신규 요청: {len(tasks)}건")

    if tasks:
        completed = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            future_to_route = {executor.submit(get_route_wrapper, t): t for t in tasks}
            for future in concurrent.futures.as_completed(future_to_route):
                mat_key, val, cache_key = future.result()
                matrix[mat_key] = val
                if USE_API_CACHE: route_cache[cache_key] = val
                
                # [진행도 % 표시]
                completed += 1
                percent = (completed / len(tasks)) * 100
                sys.stdout.write(f"\r      ▶ API 다운로드 진행률: {percent:.1f}% ({completed}/{len(tasks)})")
                sys.stdout.flush()
        print() 
        if USE_API_CACHE: save_cache(route_cache)
    
    return matrix

# ==========================================
# 3. 최적화 공통 함수
# ==========================================
def calculate_total_duration(path, matrix):
    total_dist = 0
    for i in range(len(path) - 1):
        total_dist += matrix.get((path[i], path[i+1]), {}).get('time', float('inf'))
    if len(path) > 1:
        return_cost = matrix.get((path[-1], path[0]), {}).get('time', float('inf'))
        total_dist += return_cost
    return total_dist

def run_deterministic_3opt(path, matrix):
    current_path = path[:]
    n = len(current_path)
    improved = True
    while improved:
        improved = False
        current_best_cost = calculate_total_duration(current_path, matrix)
        for i in range(1, n - 4):
            for j in range(i + 2, n - 2):
                for k in range(j + 2, n):
                    A, B, C, D = current_path[:i], current_path[i:j], current_path[j:k], current_path[k:]
                    cases = [
                        A + B[::-1] + C + D, A + B + C[::-1] + D, A + B[::-1] + C[::-1] + D,
                        A + C + B + D, A + C[::-1] + B + D, A + C + B[::-1] + D, A + C[::-1] + B[::-1] + D
                    ]
                    for case_path in cases:
                        cost = calculate_total_duration(case_path, matrix)
                        if cost < current_best_cost:
                            current_path = case_path
                            current_best_cost = cost
                            improved = True
                            break 
                    if improved: break
                if improved: break
            if improved: break
    return current_path

def get_nearest_neighbor_path(nodes, matrix, start_node_id=0):
    unvisited = set([n['id'] for n in nodes if n['id'] != start_node_id])
    path = [start_node_id]
    curr = start_node_id
    while unvisited:
        next_n = min(unvisited, key=lambda x: matrix.get((curr, x), {}).get('time', float('inf')))
        path.append(next_n)
        unvisited.remove(next_n)
        curr = next_n
    return path

# ==========================================
# 4. 알고리즘 배틀 (교체됨: Route A <-> Route B)
# ==========================================

# [Route A] 모든 교량을 시작점으로 시도 + NN + 결정론적 3-opt (이전 Route B 로직)
def solve_route_a(nodes, matrix, start_node_id=0):
    print(f"   📐 [Route A] 1st Bridge Exhaustive + NN + 결정론 3-opt 가동 중...")
    start_time = time.time()
    
    bridge_ids = [n['id'] for n in nodes if n['id'] != start_node_id]
    global_best_path = []
    global_min_dist = float('inf')
    total_scenarios = len(bridge_ids)
    
    for idx, first_id in enumerate(bridge_ids):
        path = [start_node_id, first_id]
        unvisited = set(bridge_ids) - {first_id}
        curr = first_id
        while unvisited:
            next_n = min(unvisited, key=lambda x: matrix.get((curr, x), {}).get('time', float('inf')))
            path.append(next_n)
            unvisited.remove(next_n)
            curr = next_n
            
        optimized_path = run_deterministic_3opt(path, matrix)
        dist = calculate_total_duration(optimized_path, matrix)
        
        if dist < global_min_dist:
            global_min_dist = dist
            global_best_path = optimized_path
            
        percent = ((idx + 1) / total_scenarios) * 100
        sys.stdout.write(f"\r      ▶ 시나리오 분석 중: {percent:.1f}% ({idx+1}/{total_scenarios})")
        sys.stdout.flush()

    sys.stdout.write("\n")
    elapsed_time = time.time() - start_time
    return global_best_path, global_min_dist, elapsed_time

# [Route B] 완전 무작위 절단 SA + 즉시 결정론(Memetic) (이전 Route A 로직)
def apply_pure_random_3opt(path):
    n = len(path)
    if n < 6: return path[:] 
    new_path = path[:]
    i, j, k = sorted(random.sample(range(1, n), 3))
    A, B, C, D = new_path[:i], new_path[i:j], new_path[j:k], new_path[k:]
    mode = random.randint(0, 3)
    if mode == 0:   result = A + C + B + D
    elif mode == 1: result = A + B[::-1] + C + D
    elif mode == 2: result = A + B + C[::-1] + D
    else:           result = A + C[::-1] + B + D
    return result

def solve_route_b(nodes, matrix, start_node_id=0):
    print(f"   🧬 [Route B] NN + Pure Random SA + 즉시 결정론 3-opt 가동 중...")
    start_time = time.time()
    
    current_path = get_nearest_neighbor_path(nodes, matrix, start_node_id)
    current_path = run_deterministic_3opt(current_path, matrix)
    current_cost = calculate_total_duration(current_path, matrix)
    
    best_path = current_path[:]
    best_cost = current_cost
    T = 10000.0
    cooling_rate = 0.9995
    min_temperature = 0.1
    iter_count = 0
    total_expected_iters = 23024 
    
    while T > min_temperature:
        iter_count += 1
        if iter_count % 1000 == 0:
            percent = min(100.0, (iter_count / total_expected_iters) * 100)
            sys.stdout.write(f"\r      ▶ 진행도: {percent:.1f}% (현재온도: {T:.1f}도)")
            sys.stdout.flush()

        neighbor_path = apply_pure_random_3opt(current_path)
        neighbor_cost = calculate_total_duration(neighbor_path, matrix)
        delta = neighbor_cost - current_cost
        
        if delta < 0 or random.random() < math.exp(-delta / T):
            current_path = neighbor_path
            current_cost = neighbor_cost
            if current_cost < best_cost * 1.1:
                refined_path = run_deterministic_3opt(current_path, matrix)
                refined_cost = calculate_total_duration(refined_path, matrix)
                if refined_cost < best_cost:
                    best_cost = refined_cost
                    best_path = refined_path[:]
                    current_path = refined_path[:]
                    current_cost = refined_cost
        T *= cooling_rate

    sys.stdout.write(f"\r      ▶ 진행도: 100.0% (완료)                          \n")
    elapsed_time = time.time() - start_time
    return best_path, best_cost, elapsed_time

# ==========================================
# 5. 시각화 및 유틸 (이하 동일)
# ==========================================
def print_separator(title):
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")

def generate_kakao_map_html(schedule_log, visited_nodes_info, winner_name):
    print("\n   🎨 [지도 생성] HTML 리포트를 작성하고 있습니다...")
    js_paths = []
    for log in schedule_log:
        day_idx = log['day'] - 1
        color = DAILY_COLORS[day_idx % len(DAILY_COLORS)]
        js_paths.append({'day': log['day'], 'color': color, 'path': log['path_data']})

    js_markers = []
    for info in visited_nodes_info:
        coord = info['coord'].split(',')
        m_type = "NORMAL"
        if info['order'] == 0: m_type = "START"
        elif info.get('insp_type') == '도착' or info.get('insp_type') == '복귀': m_type = "END"

        day_idx = info['day'] - 1
        color = DAILY_COLORS[day_idx % len(DAILY_COLORS)]
        if m_type != "NORMAL": color = "#000000"

        js_markers.append({
            'name': info['name'], 'lat': coord[1], 'lng': coord[0],
            'order': info['order'], 'day': info['day'], 'date': info['date'],
            'move_min': info['move_min'], 'insp_min': info['insp_min'],
            'insp_type': info.get('insp_type', '-'), 'arrival': info['arrival_time'], 
            'finish': info.get('finish_time', '-'), 'type': m_type,
            'color': color
        })
    
    day_date_map = {}
    for info in visited_nodes_info:
        if info['day'] not in day_date_map: day_date_map[info['day']] = info['date']
    
    max_day = schedule_log[-1]['day']
    legend_items = []
    for i in range(1, max_day + 1):
        color = DAILY_COLORS[(i-1) % len(DAILY_COLORS)]
        date_str = day_date_map.get(i, "")
        legend_items.append(f'<span style="color:{color}">■</span> Day {i} ({date_str})')
    
    total_nights = max_day - 1
    total_days = max_day
    total_duration_str = f"총 {total_nights}박 {total_days}일"

    summary_html = ""
    current_d = 0
    for info in visited_nodes_info:
        if info['day'] != current_d:
            current_d = info['day']
            date_s = info['date']
            color = DAILY_COLORS[(current_d-1)%len(DAILY_COLORS)]
            summary_html += f"<div style='margin-top:15px; font-weight:bold; color:{color}; border-bottom:1px solid #eee;'>[Day {current_d} - {date_s}]</div>"
            
        if info['order'] == 0: 
            detail = f"(출발 {info['arrival_time']})"
        elif info.get('insp_type') in ['도착', '복귀']: 
            detail = f"(도착 {info['arrival_time']} | 이동 {info['move_min']}분)"
        else: 
            detail = f"(도착 {info['arrival_time']} ~ 완료 {info['finish_time']} | 이동 {info['move_min']}분 | 점검 {info['insp_min']}분)"

        summary_html += f"""
        <div style='font-size:13px; margin-top:8px;'>
            <b>{info['order']}. {info['name']}</b><br>
            <span style='color:gray; font-size:11px; margin-left:10px;'>{detail}</span>
        </div>"""

    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>교량 점검 최적 경로 (Winner: {winner_name})</title>
    <script type="text/javascript" src="//dapi.kakao.com/v2/maps/sdk.js?appkey={KAKAO_JS_KEY}"></script>
    <style>
        html, body {{ width:100%; height:100%; margin:0; padding:0; font-family: 'Malgun Gothic', sans-serif; }}
        #map {{ width: 100%; height: 100%; }}
        .legend {{ 
            position: absolute; bottom: 20px; left: 20px; z-index: 999; 
            background: white; padding: 15px; border-radius: 8px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.3); font-size: 14px; line-height: 1.6;
        }}
        .route-summary {{
            position: absolute; top: 20px; right: 20px; z-index: 999;
            background: white; padding: 15px; border-radius: 8px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.3);
            width: 320px; max-height: 85%; overflow-y: auto;
        }}
        .summary-title {{ font-size: 16px; font-weight: bold; margin-bottom: 5px; border-bottom: 2px solid #ddd; padding-bottom: 5px;}}
        .info-box {{ padding: 10px; min-width: 220px; }}
        .info-title {{ font-weight: bold; font-size: 15px; margin-bottom: 5px; color: #333; }}
        .info-item {{ font-size: 13px; color: #555; margin: 2px 0; }}
        .badge {{ display:inline-block; padding:2px 6px; border-radius:4px; font-size:11px; color:white; font-weight:bold; }}
        .custom-marker {{
            width: 28px; height: 28px; border-radius: 50%; border: 2px solid white; color: white;
            text-align: center; line-height: 28px; font-weight: bold; font-size: 14px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.4); cursor: pointer; transition: transform 0.2s;
        }}
        .custom-marker:hover {{ transform: scale(1.2); z-index: 99; }}
    </style>
</head>
<body>
    <div id="map"></div>
    <div class="legend">
        <div style="font-weight:bold; margin-bottom:5px;">📅 일정 범례</div>
        {'<br>'.join(legend_items)}
        <div style="margin-top:10px; border-top:1px solid #ccc; padding-top:5px; font-weight:bold; color:#333;">{total_duration_str}</div>
    </div>
    <div class="route-summary">
        <div class="summary-title">🏆 경로 요약 (Winner: {winner_name})</div>
        {summary_html}
    </div>
    <script>
        var mapContainer = document.getElementById('map'), mapOption = {{ center: new kakao.maps.LatLng({js_markers[0]['lat']}, {js_markers[0]['lng']}), level: 9 }};
        var map = new kakao.maps.Map(mapContainer, mapOption);
        var paths = {json.dumps(js_paths)};
        var markers = {json.dumps(js_markers)};
        var bounds = new kakao.maps.LatLngBounds();
        
        paths.forEach(function(p) {{
            var linePath = [];
            p.path.forEach(function(pt) {{ linePath.push(new kakao.maps.LatLng(pt.lat, pt.lng)); }});
            var polyline = new kakao.maps.Polyline({{ path: linePath, strokeWeight: 6, strokeColor: p.color, strokeOpacity: 0.8, strokeStyle: 'solid' }});
            polyline.setMap(map);
        }});

        markers.forEach(function(m) {{
            var position = new kakao.maps.LatLng(m.lat, m.lng);
            var content = document.createElement('div');
            content.className = 'custom-marker';
            content.style.backgroundColor = m.color;
            content.innerHTML = m.order;
            
            var badgeColor = (m.insp_type === "보수점검") ? "#FF5555" : (m.insp_type === "일반점검" ? "#5555FF" : "#999");
            var infoHtml = `<div class="info-box"><div class="info-title">[${{m.order}}] ${{m.name}} <span class="badge" style="background-color:${{badgeColor}}">${{m.insp_type}}</span></div><div class="info-item">📅 날짜: Day ${{m.day}} (${{m.date}})</div><div class="info-item">🕒 도착: ${{m.arrival}}</div><div class="info-item">🚗 이동: ${{m.move_min}}분</div>${{m.insp_min > 0 ? `<div class="info-item">🔧 점검: ${{m.insp_min}}분</div>` : ''}}</div>`;
            var infowindow = new kakao.maps.InfoWindow({{ content: infoHtml, removable: true }});
            
            content.onclick = function() {{ infowindow.setPosition(position); infowindow.open(map); }};
            var customOverlay = new kakao.maps.CustomOverlay({{ position: position, content: content, yAnchor: 1 }});
            customOverlay.setMap(map);
            bounds.extend(position);
        }});
        map.setBounds(bounds);
    </script>
</body>
</html>
    """
    
    abs_path = os.path.abspath(HTML_FILE)
    with open(abs_path, "w", encoding="utf-8") as f: f.write(html_content)
    print(f"   ✨ HTML 리포트 생성 완료: {abs_path}")

def serve_and_open():
    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/': self.path = HTML_FILE
            return http.server.SimpleHTTPRequestHandler.do_GET(self)
    
    print_separator("서비스 실행")
    print(f"   🌍 지도 뷰어를 실행합니다...")
    threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
        try: httpd.serve_forever()
        except: pass

def get_next_day_start_time(day_num):
    print(f"\n   💤 [숙박 결정] Day {day_num} 일정을 시작합니다.")
    while True:
        try:
            t_str = input(f"   🕒 Day {day_num} 출발 시간 입력 (HH:MM, 예: 09:00): ").strip()
            h, m = map(int, t_str.split(':'))
            return datetime.time(h, m)
        except: print("   ❌ 올바른 형식(HH:MM)으로 입력해주세요.")

# ==========================================
# 메인
# ==========================================
def main():
    print_separator("교량 점검 최적 경로 스케줄러 (Ultimate Battle Edition)")
    
    if not os.path.exists(CSV_FILE_NAME): 
        print(f"   ❌ 오류: '{CSV_FILE_NAME}' 파일이 없습니다.")
        return
    
    try: df = pd.read_csv(CSV_FILE_NAME, encoding='utf-8')
    except: 
        try: df = pd.read_csv(CSV_FILE_NAME, encoding='cp949')
        except: print("   ❌ CSV 파일을 읽을 수 없습니다."); return

    # 1. 입력 단계
    print("   📍 기본 정보를 입력해주세요.")
    start_input = input(f"      - 출발지 입력 (엔터 시 '{OFFICE_NAME}'): ").strip()
    start_addr = start_input if start_input else OFFICE_ADDRESS
    start_name = "사용자 지정(출발)" if start_input else OFFICE_NAME
    start_coord = get_coordinate(start_addr)
    if not start_coord: return

    dest_input = input(f"      - 도착지 입력 (엔터 시 '{OFFICE_NAME}'로 복귀): ").strip()
    if not dest_input: dest_name = OFFICE_NAME; dest_coord = get_coordinate(OFFICE_ADDRESS)
    else: 
        dest_name = dest_input; dest_coord = get_coordinate(dest_input)
        if not dest_coord: dest_name = OFFICE_NAME; dest_coord = get_coordinate(OFFICE_ADDRESS)
    
    while True:
        try:
            d_s = input("      - 첫 날 날짜 (YYYY-MM-DD): ").strip()
            t_s = input("      - 출발 시간 (HH:MM): ").strip()
            start_dt = datetime.datetime.strptime(f"{d_s} {t_s}", "%Y-%m-%d %H:%M")
            departure_time_str = start_dt.strftime("%Y%m%d%H%M")
            break
        except: print("      ❌ 날짜 형식을 확인해주세요.")

    # 2. 옵션 설정
    time_mode = '1'
    fixed_minutes = 60
    print("\n   ⏱️ 점검 시간 설정")
    print("      1. CSV 데이터 사용 (일반/보수 선택)")
    print("      2. 일괄 시간 적용 (모든 교량 동일)")
    while True:
        tm = input("      >> 선택 (1/2): ").strip()
        if tm == '1': time_mode = '1'; break
        elif tm == '2':
            time_mode = '2'
            try: fixed_minutes = int(input("      >> 일괄 적용할 시간(분): ").strip()); break
            except: print("      ❌ 숫자를 입력해주세요.")

    # 3. 교량 선택
    t_input = input("\n   Bridge 점검할 교량 이름 (쉼표 구분): ").strip()
    if not t_input: return
    target_names = [x.strip() for x in t_input.split(',')]
    
    nodes = [{'id': 0, 'name': start_name, 'coord': start_coord, 'insp_time': 0, 'insp_type': '출발'}]
    idx_cnt = 1
    
    print("\n   🔍 교량 정보 검색 중...")
    for name in target_names:
        rows = df[df['name'] == name]
        if rows.empty: rows = df[df['name'].str.contains(name)]
        if rows.empty: print(f"      ⚠️ '{name}' 검색 실패"); continue
        
        sel_row = None
        if len(rows) > 1:
            print(f"\n      🚨 '{name}' 이름으로 {len(rows)}개의 교량이 검색되었습니다.")
            temp_rows = rows.reset_index(drop=True)
            for idx, row in temp_rows.iterrows():
                print(f"         [{idx + 1}] {row['address']}")
            while True:
                try:
                    sel_idx = int(input(f"      >> 원하는 교량의 번호를 입력하세요 (예: 1): "))
                    if 1 <= sel_idx <= len(temp_rows):
                        sel_row = temp_rows.iloc[sel_idx - 1]; break
                    else: print("      ❌ 목록에 있는 번호를 입력해주세요.")
                except ValueError: print("      ❌ 숫자를 입력해주세요.")
        else:
            sel_row = rows.iloc[0]

        d = sel_row
        if time_mode == '2': it = fixed_minutes; ity = f"일괄({fixed_minutes}분)"
        else:
            print(f"      ⚙️ {d['name']} 점검 유형?")
            t = input("        (1.일반 / 2.보수): ").strip()
            if t=='1': it=int(d['inspection_basic']); ity="일반점검"
            else: it=int(d['inspection_hard']); ity="보수점검"
            
        nodes.append({'id': idx_cnt, 'name': d['name'], 'coord': f"{d['longitude']},{d['latitude']}", 'insp_time': it, 'insp_type': ity})
        idx_cnt += 1

    if len(nodes) < 2: return

    # 4. [BATTLE] 알고리즘 배틀 시작
    print_separator("알고리즘 배틀 시작 (Route A vs Route B)")
    matrix = build_od_matrix(nodes, departure_time_str)
    
    # 4-1. Route A 계산 (전수 조사 방식)
    path_a, cost_a, time_a = solve_route_a(nodes, matrix, start_node_id=0)
    
    # 4-2. Route B 계산 (SA 방식)
    path_b, cost_b, time_b = solve_route_b(nodes, matrix, start_node_id=0)
    
    # 4-3. 배틀 결과 판정
    print_separator("배틀 결과 (Battle Result)")
    print(f"   🔵 [Route A - Deep Search] 예상시간: {int(cost_a/60)}분 (계산소요: {time_a*1000:.1f}ms)")
    print(f"   🔴 [Route B - Memetic SA] 예상시간: {int(cost_b/60)}분 (계산소요: {time_b*1000:.1f}ms)")
    
    winner_path = []
    winner_name = ""
    if cost_a < cost_b:
        print(f"\n   🏆 [승자 확정] Route A 가 {int((cost_b - cost_a)/60)}분 더 빠릅니다!")
        winner_path = path_a
        winner_name = "Route A (Deep Search)"
    elif cost_b < cost_a:
        print(f"\n   🏆 [승자 확정] Route B 가 {int((cost_a - cost_b)/60)}분 더 빠릅니다!")
        winner_path = path_b
        winner_name = "Route B (Memetic SA)"
    else:
        print(f"\n   🤝 [무승부] 두 알고리즘의 최적 경로 시간이 동일합니다.")
        winner_path = path_a
        winner_name = "Route A (Tie-Breaker)"

    node_map = {n['id']: n for n in nodes}
    sorted_nodes = [node_map[nid] for nid in winner_path]
    
    print(f"\n   🔒 [최종 확정된 방문 순서]")
    for i, node in enumerate(sorted_nodes):
        print(f"      {i}. {node['name']}")

    # [Step 4] 시뮬레이션
    print(f"\n   🚀 [시뮬레이션] 실시간 교통정보 반영하여 일정 산출 중...")
    
    current_day = 1
    day_basis = start_dt
    curr_dt = day_basis
    prev_node = sorted_nodes[0]
    
    map_log = []
    visited_info = [] 
    
    visited_info.append({
        'name': start_name, 'coord': start_coord, 'order': 0,
        'day': 1, 'date': day_basis.strftime('%Y-%m-%d'),
        'move_min': 0, 'insp_min': 0, 'insp_type': '출발',
        'arrival_time': curr_dt.strftime('%H:%M'), 'finish_time': curr_dt.strftime('%H:%M')
    })
    
    print(f"\n   🚩 [Day 1] {curr_dt.strftime('%H:%M')} 출발")

    for i in range(1, len(sorted_nodes)):
        target = sorted_nodes[i]
        limit_dt = day_basis + datetime.timedelta(hours=WORK_LIMIT_HOURS)
        
        move_sec, path_data = get_kakao_route_data(prev_node['coord'], target['coord'], curr_dt.strftime("%Y%m%d%H%M"))
        move_min = move_sec // 60
        
        arr_dt = curr_dt + datetime.timedelta(minutes=move_min)
        fin_dt = arr_dt + datetime.timedelta(minutes=target['insp_time'])
        
        is_next_day = False
        if fin_dt > limit_dt:
            print(f"      ⚠️  경고: '{target['name']}' 작업 시 근무 시간 초과 예상 ({fin_dt.strftime('%H:%M')})")
            while True:
                c = input("          >> 연장근무(y) / 숙박 후 다음날(n)? ").lower()
                if c=='y': is_next_day=False; break
                elif c=='n': is_next_day=True; break
        
        if is_next_day:
            current_day += 1
            day_basis = datetime.datetime.combine(day_basis.date() + datetime.timedelta(days=1), get_next_day_start_time(current_day))
            curr_dt = day_basis
            print(f"\n   ☀️ [Day {current_day}] {curr_dt.strftime('%Y-%m-%d %H:%M')} 출발")
            
            move_sec, path_data = get_kakao_route_data(prev_node['coord'], target['coord'], curr_dt.strftime("%Y%m%d%H%M"))
            move_min = move_sec // 60
            arr_dt = curr_dt + datetime.timedelta(minutes=move_min)
            fin_dt = arr_dt + datetime.timedelta(minutes=target['insp_time'])
        
        map_log.append({'day': current_day, 'start_id': prev_node['id'], 'end_id': target['id'], 'path_data': path_data})
        visited_info.append({
            'name': target['name'], 'coord': target['coord'], 'order': i,
            'day': current_day, 'date': day_basis.strftime('%Y-%m-%d'),
            'move_min': move_min, 'insp_min': target['insp_time'], 'insp_type': target['insp_type'],
            'arrival_time': arr_dt.strftime('%H:%M'), 'finish_time': fin_dt.strftime('%H:%M')
        })
        
        print(f"      🚗 {move_min}분 이동 ➔ {target['name']} ({arr_dt.strftime('%H:%M')} 도착)")
        curr_dt = fin_dt
        prev_node = target

    # 복귀
    query_time = curr_dt.strftime("%Y%m%d%H%M")
    ret_sec, ret_path = get_kakao_route_data(prev_node['coord'], dest_coord, query_time)
    ret_min = ret_sec // 60
    final_dt = curr_dt + datetime.timedelta(minutes=ret_min)
    limit_dt = day_basis + datetime.timedelta(hours=WORK_LIMIT_HOURS)
    
    is_return_delay = False
    if final_dt > limit_dt:
        over_minutes = int((final_dt - limit_dt).total_seconds() // 60)
        print(f"      ⚠️  경고: 복귀 시 근무 시간 초과 예상 ({final_dt.strftime('%H:%M')}, +{over_minutes}분)")
        while True:
            c = input("          >> 퇴근 강행(y) / 숙박 후 다음날(n)? ").lower()
            if c=='y': is_return_delay = False; break
            elif c=='n': is_return_delay = True; break

    if is_return_delay:
        current_day += 1
        day_basis = datetime.datetime.combine(day_basis.date() + datetime.timedelta(days=1), get_next_day_start_time(current_day))
        curr_dt = day_basis
        ret_sec, ret_path = get_kakao_route_data(prev_node['coord'], dest_coord, curr_dt.strftime("%Y%m%d%H%M"))
        ret_min = ret_sec // 60
        final_dt = curr_dt + datetime.timedelta(minutes=ret_min)
        print(f"\n   ☀️ [Day {current_day}] 복귀 출발")

    map_log.append({'day': current_day, 'start_id': prev_node['id'], 'end_id': 0, 'path_data': ret_path})
    visited_info.append({
        'name': f"{dest_name} (도착)", 'coord': dest_coord, 'order': len(sorted_nodes),
        'day': current_day, 'date': day_basis.strftime('%Y-%m-%d'),
        'move_min': ret_min, 'insp_min': 0, 'insp_type': '복귀',
        'arrival_time': final_dt.strftime('%H:%M'), 'finish_time': final_dt.strftime('%H:%M')
    })
    
    print(f"      🚗 {ret_min}분 이동 ➔ {dest_name} ({final_dt.strftime('%H:%M')} 도착)")
    
    print_separator("최종 스케줄 요약")
    print(f"{'순서':<5} | {'Day':<5} | {'장소명':<15} | {'도착':<8} | {'이동(분)':<8} | {'작업(분)':<8}")
    print("-" * 70)
    for info in visited_info:
        print(f"{info['order']:<5} | {info['day']:<5} | {info['name']:<15} | {info['arrival_time']:<8} | {info['move_min']:<8} | {info['insp_min']:<8}")
    print("-" * 70)

    generate_kakao_map_html(map_log, visited_info, winner_name)
    serve_and_open()

if __name__ == "__main__": 
    main()
