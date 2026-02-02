import pandas as pd
import requests
import time

# ======================================================
# 1. 사용자 설정 (API 키 입력)
# ======================================================
REST_API_KEY = ""        # 발급 받은 REST API 키 입력

# ======================================================
# 2. 파일 불러오기
# ======================================================
input_file = ""        # 생성한 입력 데이터 csv 파일 이름 (예: Target_bridges.csv)
output_file = ""        # 최종 입력 데이터 csv 파일 이름 (예: Final_Bridge_Data.csv)

try:
    # [수정] encoding='cp949' 추가 (한글 깨짐 해결)
    # 엑셀에서 만든 CSV는 대부분 cp949로 읽어야 합니다.
    df = pd.read_csv(input_file, usecols=['ID', 'name', 'address'], encoding='cp949')
    print(f"📂 '{input_file}' 로드 완료! (총 {len(df)}개 교량)")
except UnicodeDecodeError:
    # 혹시 cp949로도 안 되면 utf-8-sig로 재시도
    try:
        df = pd.read_csv(input_file, usecols=['ID', 'name', 'address'], encoding='utf-8-sig')
        print(f"📂 '{input_file}' 로드 완료! (utf-8-sig)")
    except Exception as e:
        print(f"❌ 인코딩 오류 2차 실패: {e}")
        exit()
except Exception as e:
    print(f"❌ 파일 읽기 실패: {e}")
    exit()

# ======================================================
# 3. 카카오 API 좌표 변환 함수
# ======================================================
def get_lat_lon(address, api_key):
    url = "https://dapi.kakao.com/v2/local/search/address.json"
    headers = {"Authorization": f"KakaoAK {api_key}"}
    
    try:
        response = requests.get(url, headers=headers, params={"query": address})
        data = response.json()
        
        if data.get('documents'):
            y = data['documents'][0]['y']
            x = data['documents'][0]['x']
            return float(y), float(x)
        else:
            # 주소 검색 실패 시 키워드 검색 시도
            url_keyword = "https://dapi.kakao.com/v2/local/search/keyword.json"
            response = requests.get(url_keyword, headers=headers, params={"query": address})
            data = response.json()
            if data.get('documents'):
                y = data['documents'][0]['y']
                x = data['documents'][0]['x']
                return float(y), float(x)
            return None, None
            
    except Exception as e:
        print(f"API 에러: {e}")
        return None, None

# ======================================================
# 4. 좌표 데이터 추가 작업 실행
# ======================================================
print("\n🚀 좌표 변환을 시작합니다...")

lats = []
lngs = []

# 데이터프레임 순회
for index, row in df.iterrows():
    bridge_name = row['name']
    
    # address 값이 비어있을(NaN) 경우 대비
    if pd.isna(row['address']):
        address = ""
    else:
        address = str(row['address']).strip()
    
    print(f"[{index+1}/{len(df)}] {bridge_name} 위치 찾는 중...", end=" ")
    
    if address:
        lat, lng = get_lat_lon(address, REST_API_KEY)
    else:
        lat, lng = None, None
    
    if lat and lng:
        print("✅ 성공")
        lats.append(lat)
        lngs.append(lng)
    else:
        print("❌ 실패 (주소 확인 필요)")
        lats.append(0.0)
        lngs.append(0.0)
    
    time.sleep(0.1)

# ======================================================
# 5. 데이터프레임 정리 및 저장
# ======================================================
df['latitude'] = lats
df['longitude'] = lngs
df['inspection_time'] = "" 

# 저장할 때는 전세계 공통인 utf-8-sig로 저장
df.to_csv(output_file, index=False, encoding="utf-8-sig")

print("\n" + "="*50)
print(f"🎉 작업 완료! '{output_file}' 파일이 생성되었습니다.")
print("="*50)
print(df.head())
