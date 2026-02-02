# 🌉 Optimal Path Finding

- 지도 API를 활용하여 전국 각지의 교량 현장을 대상으로 현장점검을 수행함에 있어 효율적 방문을 위한 일정 수립 및 경로 최적화 서비스 구현



## 🚀 주요 기능 (Key Features)

### 1. 📍 자동 좌표 변환 (Geocoding)
- `1.OPF_BridgeData_CSV.py`를 통해 교량의 도로명 주소를 위도/경도 좌표로 일괄 변환합니다.

### 2. 🗺 시각적 위치 보정 인터페이스
- `2.OPF_Visualization.py`를 실행하여 Flask 기반의 웹 환경에서 교량 위치를 확인합니다.
- 마커를 드래그하여 사용자가 원하는 위치로 이동시키면 CSV 데이터에 즉시 반영됩니다.

### 3. 🧬 알고리즘 배틀 기반 경로 최적화
- `3.OPF_Algorithm_Finale.py`는 두 가지 상이한 알고리즘을 대결시켜 최상의 결과를 도출합니다.
  - **Route A (Deep Search)**: 경우의 수(첫번재 점검 교량만) + 최근접 이웃(NN) + 결정론적 3-opt
  - **Route B (Memetic SA)**: 최근접 이웃(NN) + 무작위 3-opt + SA(담금질 기법)
- **실무 제약 조건 반영**: 8시간 근무 시간 제한, 연장 근무 여부 선택, 교량별 점검 유형(일반/보수)에 따른 소요 시간 차등 적용 등을 지원합니다.
- **실시간 교통정보**: 카카오 모빌리티 API를 연동하여 실제 이동 시간을 계산합니다.



## 🛠 기술 스택 (Tech Stack)

- **언어**: Python
- **프레임워크/라이브러리**: Flask, Pandas, Requests, Concurrent.futures
- **외부 API**: Kakao Maps API, Kakao Mobility API, Kakao Local API
- **알고리즘**: Nearest Neighbor, 3-opt, Simulated Annealing (SA)




## 📋 사용법 (How to Use)

1. **API 키 발급 및 기본 설정** 
    - 카카오 디벨로퍼스(https://developers.kakao.com/)에서 `REST API 키` 및 `JavaScript 키`를 발급 받는다.
    - 키 발급 시, 앱 -> 앱설정 -> 앱 -> 제품 링크 관리 -> 웹 도메인에 'http://lolcalhost:8000'을 추가한다.

2. **입력 데이터 제작**
    - 이미 완성된 입력 데이터 제공 -> "Final_Bridge_Data.csv"
    - 점검 교량 추가/변경/삭제 될 경우, 아래의 방식으로 입력 데이터 생성
      
    <1. 위도/경도 추출>
    -  ID, 교량명, 주소, 점검시간을 직접 입력한 csv 파일을 생성한다. (예: Target_bridges.csv)
    - `1.OPF_BridgeData_CSV.py`에 `REST_API_KEY`와 생성한 입력 데이터 파일을 불러온다.
    - 도출될 입력 데이터 파일명을 설정한다. (예: Final_Bridge_Data.csv)
    - `1.OPF_BridgeData_CSV.py` 실행
    - 입력 데이터 완성

    <2. 위도/경도 수정>
    - `2.OPF_Visualization.py`에 `REST_API_KEY`, `JS_KEY`와 입력 데이터 파일을 불러온다.
    - `2.OPF_Visualization.py` 실행
    - 카카오맵(https://map.kakao.com/)을 참고하여 원하는 교량 위치로 직접 수정한다.
    - 브라우저를 닫으면 위도/경도 수정된 입력 데이터 완성


4. **경로 산출**
    - `3.OPF_Algorithm_Finale.py`를 실행
    - 출발지, 도착지, 출발날짜/위치, 점검 시간, 점검 교량을 입력한다.
    - 일정 생성 시, 연장 근무 여부를 확인

5. **리포트 확인**: 자동 생성된 `kakao_map_battle_visual.html` 파일을 통해 시각화된 경로와 상세 타임라인을 확인합니다.



## 📈 기대 효과
- **경제적/시간적 효율성 극대화**: 이동시간 최소화, 유류비 절감, 일일 점검 가능 교량 수 증대.
- **데이터 기반 스마트 스케줄링**: 현실적 이동경로 산출 및 연장근무 및 숙박 판단 도움
- **현장점검 업무의 표준화/체계화**: 표준화된 최적 점검 순서 확보 가능 및 교량 데이터 변경 시에도 체계화된 워크플로우 유지
