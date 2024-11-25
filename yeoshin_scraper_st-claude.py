import streamlit as st
import time
from anthropic import Anthropic
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import pandas as pd
import logging
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import plotly.express as px
import plotly.graph_objects as go
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Image, Spacer, Paragraph
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase.pdfmetrics import registerFontFamily
import io
import re
import os
from dotenv import load_dotenv
import subprocess

# Streamlit Cloud에서 Chrome 설치
def install_chrome():
    try:
        subprocess.run(['apt-get', 'update'])
        subprocess.run(['apt-get', 'install', '-y', 'chromium-browser'])
    except Exception as e:
        st.error(f"Chrome 설치 중 오류 발생: {str(e)}")

# 앱 시작 시 Chrome 설치
if 'STREAMLIT_CLOUD' in os.environ:
    install_chrome()
    
# 파일 상단에 환경 변수 로드
load_dotenv()

class YeoshinScraper:
    def __init__(self):
        self.results = []
        self.driver = None
        self.setup_logging()
        
    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        
    def setup_driver(self):
        try:
            options = webdriver.ChromeOptions()
            # 성능 최적화 옵션들
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-extensions')  # 확장 프로그램 비활성화
            options.add_argument('--disable-notifications')  # 알림 비활성화
            options.add_argument('--disable-logging')  # 로깅 비활성화
            options.add_argument('--disable-default-apps')  # 기본 앱 비활성화
            options.add_argument('--disable-infobars')  # 정보 표시줄 비활성화
            options.add_argument('--disable-blink-features=AutomationControlled')  # 자동화 감지 방지
            options.add_argument('--start-maximized')  
            options.add_argument('--disable-gpu')
            options.add_argument('--disable-popup-blocking')
            options.add_argument('--blink-settings=imagesEnabled=false')  # 이미지 로딩 비활성화
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--headless')  # Streamlit 환경에서 필요

            # 메모리 관련 설정
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--no-zygote')
            options.add_argument('--disable-accelerated-2d-canvas')
            options.add_argument('--disable-webgl')

            options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            # Streamlit Cloud 환경일 때의 추가 설정
            if 'STREAMLIT_CLOUD' in os.environ:
                options.binary_location = '/usr/bin/chromium-browser'
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-dev-shm-usage')
            
            service = Service()
            if 'STREAMLIT_CLOUD' in os.environ:
                self.driver = webdriver.Chrome(options=options)
            else:
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=options)
                
            self.driver.set_page_load_timeout(30)  # 페이지 로드 타임아웃 설정
            self.wait = WebDriverWait(self.driver, 15)  # 기본 대기 시간 감소

            # 빈 페이지 접속
            self.driver.get("https://www.yeoshin.co.kr")
            time.sleep(2)

            # 로그인 관련 쿠키 설정
            cookies = [
                {"name": "LOGIN_INFO", "value": os.getenv("LOGIN_INFO")},
                {"name": "HSID", "value": os.getenv("HSID")},
                {"name": "SSID", "value": os.getenv("SSID")},
                {"name": "APISID", "value": os.getenv("APISID")},
                {"name": "SAPISID", "value": os.getenv("SAPISID")},
                {"name": "SID", "value": os.getenv("SID")},
                {"name": "_kau", "value": os.getenv("KAU")},
                {"name": "_kahai", "value": os.getenv("KAHAI")},
                {"name": "_karmt", "value": os.getenv("KARMT")},
                {"name": "_kawlt", "value": os.getenv("KAWLT")},
                {"name": "access_token", "value": os.getenv("ACCESS_TOKEN")}
            ]

            for cookie in cookies:
                cookie.update({
                    "domain": ".yeoshin.co.kr",
                    "path": "/"
                })
                self.driver.add_cookie(cookie)

            self.driver.refresh()
            time.sleep(2)

        except Exception as e:
            logging.error(f"Driver 설정 중 오류 발생: {str(e)}")
            raise

    def wait_for_page_load(self, timeout=15):
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            time.sleep(2)
        except TimeoutException:
            logging.warning("페이지 로딩 시간 초과")

    def scroll_to_load_all(self):
        SCROLL_PAUSE_TIME = 1
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        
        for _ in range(3):
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(SCROLL_PAUSE_TIME)
            
            try:
                WebDriverWait(self.driver, 10).until(
                    lambda driver: driver.execute_script("return document.body.scrollHeight") > last_height
                )
            except TimeoutException:
                break
                
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

    def search_keyword(self, keyword, progress_bar):
        try:
            search_url = f"https://www.yeoshin.co.kr/search/category?q={keyword}&tab=events"
            self.driver.get(search_url)
            self.wait_for_page_load()
            progress_bar.progress(0.2)
            
            time.sleep(5)
            self.scroll_to_load_all()
            progress_bar.progress(0.3)
            
        except Exception as e:
            logging.error(f"검색 중 오류 발생: {str(e)}")

    def get_event_details(self, item, progress_value, progress_bar):
        try:
            # 병원 이름과 지역 정보 추출
            spans = item.find_elements(By.CSS_SELECTOR, "span")
            if len(spans) >= 3:
                hospital_name = spans[0].text.strip()
                location = item.find_element(
                    By.XPATH,
                    './/article/section[2]/div/span[2]'
                ).text.strip()
                
                # 이벤트명 추출
                event_name = item.find_element(
                    By.XPATH,
                    './/article/section[2]/section[1]/h2'
                ).text.strip()
                
                # 상세 페이지 링크 요소 찾기 및 클릭
                article = item.find_element(By.TAG_NAME, "article")
                self.driver.execute_script("arguments[0].click();", article)
                time.sleep(3)
                
                # 새 창으로 전환
                main_window = self.driver.current_window_handle
                new_window = [handle for handle in self.driver.window_handles if handle != main_window][0]
                self.driver.switch_to.window(new_window)
                time.sleep(3)

                # 상세 페이지 URL 가져오기
                detail_link = self.driver.current_url
                
                # 평점, 리뷰수, 스크랩수, 문의수 추출
                try:
                    rating = self.driver.find_element(
                        By.XPATH,
                        '//*[@id="ct-view"]/div/div/div/div[2]/div[1]/article/section/div[2]/div/div/span'
                    ).text.strip()
                    # '후기' 텍스트 제거하고 숫자만 추출
                    review_count = re.sub(r'[^0-9]', '', review_count)
                except:
                    rating = "N/A"
                    
                try:
                    review_count = self.driver.find_element(
                        By.XPATH,
                        '//*[@id="ct-view"]/div/div/div/div[2]/div[1]/article/section/div[2]/div/span'
                    ).text.strip()
                except:
                    review_count = "N/A"
                    
                try:
                    scrap_count = self.driver.find_element(
                        By.XPATH,
                        '//*[@id="ct-view"]/div/div/section/div[1]/div/p'
                    ).text.strip()
                except:
                    scrap_count = "N/A"
                    
                try:
                    inquiry_count = self.driver.find_element(
                        By.XPATH,
                        '//*[@id="ct-view"]/div/div/div/div[2]/div[4]/div[1]/div/p[2]'
                    ).text.strip()
                except:
                    inquiry_count = "N/A"

                # 옵션 정보 수집
                options_data = []
                try:
                    # 전체보기 버튼 찾기 및 클릭
                    view_all_button = self.driver.find_element(
                        By.XPATH,
                        '//*[@id="ct-view"]/div/div/div[1]/div[2]/div[2]/div[position()>=2 and position()<=4]/div/div[2]/p'
                    )
                    self.driver.execute_script("arguments[0].click();", view_all_button)
                    time.sleep(2)
                    
                    # 모달에서 옵션 정보 수집
                    options_base_xpath = '//*[@id="ct-view"]/div/div/div[2]/div/div/div/div[2]/div[2]'
                    options = self.driver.find_elements(By.XPATH, f"{options_base_xpath}/div")
                    
                    for i in range(1, len(options) + 1):
                        try:
                            current_option_xpath = f"{options_base_xpath}/div[{i}]"
                            option_name = self.driver.find_element(
                                By.XPATH,
                                f"{current_option_xpath}/div/p"
                            ).text.strip()
                            price = self.driver.find_element(
                                By.XPATH,
                                f"{current_option_xpath}/p"
                            ).text.strip()
                            
                            if option_name and price:
                                options_data.append({
                                    'hospital_name': hospital_name,
                                    'location': location,
                                    'event_name': event_name,
                                    'option_name': option_name,
                                    'price': price,
                                    'rating': rating,
                                    'review_count': review_count,
                                    'scrap_count': scrap_count,
                                    'inquiry_count': inquiry_count,
                                    'detail_link': detail_link
                                })
                        except Exception as e:
                            continue
                            
                except Exception as e:
                    # 기본 옵션 정보 수집
                    options_container = self.driver.find_element(
                        By.XPATH,
                        '//*[@id="ct-view"]/div/div/div[1]/div[2]/div[2]/div[1]/div[2]/div[1]'
                    )
                    option_elements = options_container.find_elements(By.XPATH, './div/div')
                    
                    for option in option_elements:
                        try:
                            divs = option.find_elements(By.CSS_SELECTOR, "div")
                            if len(divs) >= 2:
                                option_name = divs[0].text.strip()
                                option_price = divs[1].text.strip()
                                
                                if option_name and option_price:
                                    options_data.append({
                                        'hospital_name': hospital_name,
                                        'location': location,
                                        'event_name': event_name,
                                        'option_name': option_name,
                                        'price': option_price,
                                        'rating': rating,
                                        'review_count': review_count,
                                        'scrap_count': scrap_count,
                                        'inquiry_count': inquiry_count,
                                        'detail_link': detail_link
                                    })
                        except Exception as e:
                            continue

                # 창 닫고 원래 창으로 복귀
                self.driver.close()
                self.driver.switch_to.window(main_window)
                time.sleep(2)
                
                progress_bar.progress(progress_value)
                return options_data
            
        except Exception as e:
            logging.error(f"이벤트 처리 중 오류: {str(e)}")
            if len(self.driver.window_handles) > 1:
                self.driver.close()
                self.driver.switch_to.window(main_window)
            time.sleep(2)
            return []

    def scrape_data(self, keyword, progress_bar):
        try:
            self.setup_driver()
            self.search_keyword(keyword, progress_bar)
            
            # 검색 결과 로딩 대기
            time.sleep(3)
            
            # 컨테이너 찾기 전에 한 번 더 스크롤
            self.scroll_to_load_all()
            
            events_container = self.wait.until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    "#ct-view > div > main > article > section:nth-child(2) > section"
                ))
            )
            
            event_items = events_container.find_elements(By.XPATH, "./div")
            total_items = len(event_items)
            
            if total_items == 0:
                logging.warning("검색 결과가 없습니다.")
                return pd.DataFrame()
                
            events_data = []
            for idx, item in enumerate(event_items, 1):
                progress_value = 0.3 + (0.7 * (idx / total_items))
                item_data = self.get_event_details(item, progress_value, progress_bar)
                if item_data:
                    events_data.extend(item_data)
            
            return pd.DataFrame(events_data)
            
        except Exception as e:
            logging.error(f"스크래핑 중 오류 발생: {str(e)}")
            return pd.DataFrame()
        finally:
            if self.driver:
                self.driver.quit()

def create_visualizations(df):
    # 가격 데이터 전처리
    def clean_price(price_str):
        try:
            numbers = re.findall(r'\d+', price_str)
            if numbers:
                return int(''.join(numbers))
            return None
        except:
            return None
    
    # 가격 데이터 정제
    df_viz = df.copy()
    df_viz['price_cleaned'] = df_viz['가격'].apply(clean_price)
    
    # Null이 아닌 데이터만 사용
    df_viz = df_viz[df_viz['price_cleaned'].notna()]
    
    # 각 병원별로 첫 번째 옵션만 선택
    df_first_options = df_viz.groupby(['병원명', '위치']).first().reset_index()

    
    # 지역별 평균 가격 계산 (첫 번째 옵션만 사용)
    fig_price = px.bar(
        df_first_options.groupby('위치')['price_cleaned'].mean().reset_index(),
        x='위치',
        y='price_cleaned',
        title='지역별 대표 옵션 가격 평균',
        labels={'price_cleaned': '가격 (원)', '위치': '지역'}
    )
    
    fig_price.update_layout(
        xaxis_tickangle=-45,
        yaxis_title='평균 가격 (원)',
        showlegend=False
    )
    
    return fig_price

def validate_data(df):
    required_columns = ['hospital_name', 'location', 'event_name', 'option_name', 
                       'price', 'rating', 'review_count', 'scrap_count', 'inquiry_count']
    
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        st.warning(f"누락된 컬럼이 있습니다: {', '.join(missing_columns)}")
        return False
    return True

def analyze_with_claude(df):
    anthropic = Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))
    
    # 데이터 전처리
    analysis_data = df.copy()
    analysis_data['exposure_order'] = analysis_data.index + 1
    
    prompt = f"""
    여신티켓의 시술 이벤트 데이터를 분석하여, 새로운 이벤트를 등록하려는 병원에게 도움이 될 만한 인사이트를 제공해주세요.
    
    아래 형식에 맞춰 분석해주세요:
    
    A. 옵션 분석
    1. 옵션명 패턴 분석:
    - 가장 많이 사용되는 옵션명 패턴
    - 효과적인 옵션명 구성 방식
    
    2. 가격대별 옵션 구성 특징:
    - 가격대별 옵션 구성의 특징
    - 가격대별 할인율 패턴
    
    3. 평균 옵션 개수 분석:
    - 이벤트당 평균 옵션 수
    - 최적의 옵션 구성 제안
    
    B. 첫 번째 옵션 분석
    1. 일반적인 첫 번째 옵션 패턴:
    - 주로 사용되는 첫 번째 옵션의 구성과 특징
    - 첫 번째 옵션의 가격대별 분포
    
    2. 가격 비교:
    - 가장 저렴한 첫 번째 옵션: 병원명, 위치, 옵션명, 가격
    - 가장 비싼 첫 번째 옵션: 병원명, 위치, 옵션명, 가격
    
    C. 위치 기반 분석
    1. 지역별 특성:
    - 지역별 평균 가격대
    - 지역별 옵션 구성 특징
    - 지역별 고객 반응(리뷰/평점) 특징
    
    D. 고객 반응 분석
    1. 고객 반응 상세 분석:
    - 문의수가 많은 이벤트들의 특징
    - 평점과 리뷰 수의 상관관계
    - 스크랩 수가 높은 이벤트의 특징
    - 고객 관심을 이끌어내는 핵심 요소들
    
    분석 시 다음 가이드라인을 준수해주세요:
    1. 실제 예시와 수치를 근거로 들어 분석해주세요.
    2. 가격에 대한 분석을 할 때에는 정확한 금액과 실제 예시를 들어서 설명해주세요.
    3. 분석할 때 주의사항:
        - 가격이나 용량의 범위를 표현할 때는 '~' 대신 '부터', '까지' 또는 '-' 를 사용해주세요.
        예시:  - '30만원~100만원' 대신 '30만원부터 100만원까지' 또는 '30만원-100만원' 사용
               - '5cc~10cc' 대신 '5cc부터 10cc까지' 또는 '5cc-10cc' 사용
    
    마지막으로, 위 분석을 바탕으로 새로운 이벤트를 등록하려는 병원에게 3가지 핵심 제언을 해주세요.
    
    분석할 데이터:
    {analysis_data.to_string()}
    """
    
    try:
        response = anthropic.messages.create(
            model="claude-3-sonnet-20240229",
            max_tokens=2000,
            temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )
        
        try:
            content = response.content[0].text if isinstance(response.content, list) else response.content
            
            st.header("🔍 AI 분석 결과")
            
            # A. 옵션 분석
            st.subheader("A. 옵션 분석 📊")
            options_section = content[content.find("A. 옵션 분석"):content.find("B. 첫 번째 옵션")]
            for i in range(1, 4):
                st.markdown(f"**{i}. {options_section.split(f'{i}.')[1].split(f'{i+1}.')[0].strip()}**")
                
            # B. 첫 번째 옵션 분석
            st.subheader("B. 첫 번째 옵션 분석 💰")
            first_option_section = content[content.find("B. 첫 번째 옵션"):content.find("C. 위치 기반")]
            for i in range(1, 3):
                st.markdown(f"**{i}. {first_option_section.split(f'{i}.')[1].split(f'{i+1}.')[0].strip()}**")
            
            # C. 위치 기반 분석
            st.subheader("C. 위치 기반 분석 📍")
            location_section = content[content.find("C. 위치 기반"):content.find("D. 고객 반응")]
            st.markdown(location_section)
            
            # D. 고객 반응 분석
            st.subheader("D. 고객 반응 분석 👥")
            customer_section = content[content.find("D. 고객 반응"):content.find("마지막으로")]
            st.markdown(customer_section)
            
            # 핵심 제언
            if "핵심 제언" in content:
                st.subheader("💡 새로운 이벤트 등록을 위한 핵심 제언")
                recommendations = content[content.find("핵심 제언"):].split("\n")
                for rec in recommendations[1:]:
                    if rec.strip():
                        st.info(rec.strip())
            
            return content
            
        except Exception as e:
            st.error(f"분석 결과 표시 중 오류가 발생했습니다: {str(e)}")
            return "분석 결과를 표시할 수 없습니다."
            
    except Exception as e:
        st.error(f"Claude AI 분석 중 오류가 발생했습니다: {str(e)}")
        return "분석을 수행할 수 없습니다."

def generate_pdf(df, analysis_text, fig_price, fig_dist):
    try:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        
        # 나눔고딕 폰트 경로 지정 및 등록
        FONT_PATH = r"D:\code\yeoshin/NanumGothic.ttf"
        try:
            pdfmetrics.registerFont(TTFont('NanumGothic', FONT_PATH))
            registerFontFamily('NanumGothic', normal='NanumGothic')
            font_name = 'NanumGothic'
        except Exception as e:
            st.warning(f"폰트 로딩 실패: {str(e)}. 기본 폰트를 사용합니다.")
            font_name = 'Helvetica'
        
        # 한글 지원 스타일 생성
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(
            name='KoreanNormal',
            fontName=font_name,
            fontSize=10,
            leading=12
        ))
        styles.add(ParagraphStyle(
            name='KoreanHeading1',
            fontName=font_name,
            fontSize=16,
            leading=20,
            spaceAfter=30
        ))
        
        # PDF에 들어갈 요소들을 담을 리스트
        elements = []
        
        # 제목 추가
        elements.append(Paragraph('스크래핑 데이터', styles['KoreanHeading1']))
        elements.append(Spacer(1, 20))
        
        # 데이터 테이블 생성
        col_names = {
            'hospital_name': '병원명',
            'location': '위치',
            'event_name': '이벤트명',
            'option_name': '옵션명',
            'price': '가격',
            'rating': '평점',
            'review_count': '리뷰수',
            'scrap_count': '스크랩수',
            'inquiry_count': '문의수'
        }
        
        # 테이블 데이터 준비
        table_data = [[col_names[col] for col in col_names.keys()]]
        
        for _, row in df.iterrows():
            table_row = []
            for col in col_names.keys():
                try:
                    value = row[col] if pd.notna(row[col]) else "N/A"
                    table_row.append(str(value)[:20])
                except KeyError:
                    table_row.append('N/A')
            table_data.append(table_row)
        
        # 테이블 스타일 설정
        table_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), font_name),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('FONTNAME', (0, 1), (-1, -1), font_name),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ])
        
# 테이블 생성 및 스타일 적용
        table = Table(table_data, repeatRows=1)
        table.setStyle(table_style)
        elements.append(table)
        
        try:
            # 시각화 섹션 제목
            elements.append(Spacer(1, 30))
            elements.append(Paragraph('데이터 시각화', styles['KoreanHeading1']))
            
            # 그래프 이미지 저장 및 추가
            fig_price.write_image("price_plot.png")
            fig_dist.write_image("dist_plot.png")
            
            elements.append(Image("price_plot.png", width=500, height=300))
            elements.append(Spacer(1, 30))
            elements.append(Image("dist_plot.png", width=500, height=300))
        except Exception as e:
            elements.append(Paragraph(f'그래프 생성 중 오류 발생: {str(e)}', styles['KoreanNormal']))
        
        # 분석 리포트 섹션
        elements.append(Spacer(1, 30))
        elements.append(Paragraph('분석 리포트', styles['KoreanHeading1']))
        elements.append(Paragraph(analysis_text, styles['KoreanNormal']))
        
        # PDF 생성
        doc.build(elements)
        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes
        
    except Exception as e:
        st.error(f"PDF 생성 중 오류가 발생했습니다: {str(e)}")
        return None

def main():
    st.title("여신티켓 데이터 스크래퍼")
    
    keyword = st.text_input("검색할 키워드를 입력하세요:")
    
    if st.button("스크래핑 시작"):
        progress_bar = st.progress(0)
        scraper = YeoshinScraper()
        
        with st.spinner('데이터를 수집중입니다...'):
            df = scraper.scrape_data(keyword, progress_bar)
            
        if not df.empty and validate_data(df):
            st.success("데이터 수집이 완료되었습니다!")
            
            # 칼럼명을 한글로 변경
            column_names = {
                'hospital_name': '병원명',
                'location': '위치',
                'event_name': '이벤트명',
                'option_name': '옵션명',
                'price': '가격',
                'rating': '평점',
                'review_count': '리뷰수',
                'scrap_count': '스크랩수',
                'inquiry_count': '문의수',
                'detail_link': '상세링크'
            }
            df = df.rename(columns=column_names)
            
            # 데이터프레임을 스크롤 가능한 컨테이너에 표시
            st.write("수집된 데이터:")
            st.dataframe(df, height=400)
            
            # 시각화
            fig_price = create_visualizations(df)
            st.plotly_chart(fig_price)
            
            # Claude AI 분석
            with st.spinner('AI 분석을 수행중입니다...'):
                analysis_text = analyze_with_claude(df)
                      
            try:
                pdf_bytes = generate_pdf(df, analysis_text, fig_price, None)
                if pdf_bytes:
                    st.download_button(
                        label="PDF 보고서 다운로드",
                        data=pdf_bytes,
                        file_name=f"yeoshin_{keyword}_report.pdf",
                        mime="application/pdf"
                    )
                else:
                    st.error("PDF 생성에 실패했습니다.")
            except Exception as e:
                st.error(f"PDF 처리 중 오류가 발생했습니다: {str(e)}")
        else:
            st.warning("검색 결과가 없거나 데이터 형식이 올바르지 않습니다. 다른 키워드로 시도해보세요.")

if __name__ == "__main__":
    main()
