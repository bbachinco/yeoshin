# 기본 라이브러리
import streamlit as st
import time
import logging
import os
import io
import re
from dotenv import load_dotenv
import tempfile
import subprocess

# Anthropic 관련
from anthropic import Anthropic

# Playwright 관련
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# 데이터 처리 및 시각화
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# PDF 관련
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Image, Spacer, Paragraph
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase.pdfmetrics import registerFontFamily

# 환경 변수 로드
load_dotenv()

class YeoshinScraper:
    def __init__(self):
        self.results = []
        self.page = None
        self.browser = None
        self.playwright = None
        self.current_keyword = None
        self.setup_logging()
        
    def __del__(self):
        """소멸자에서 드라이버 정리"""
        self.cleanup()
    
    def cleanup(self):
        """브라우저 정리를 위한 메서드"""
        if self.page:
            try:
                self.page.close()
            except Exception as e:
                self.logger.error(f"페이지 종료 중 오류: {str(e)}")
        if self.browser:
            try:
                self.browser.close()
            except Exception as e:
                self.logger.error(f"브라우저 종료 중 오류: {str(e)}")
        if self.playwright:
            try:
                self.playwright.stop()
            except Exception as e:
                self.logger.error(f"Playwright 종료 중 오류: {str(e)}")

    def setup_logging(self):
        """로깅 설정"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler()]
        )
        self.logger = logging.getLogger(__name__)

    def check_login_status(self):
        """로그인 상태 확인"""
        try:
            self.page.goto("https://www.yeoshin.co.kr/myPage")
            
            selectors = [
                "#ct-view > div > div > div.sc-d64fbdbd-0.IeGIQ > a",
                '//*[@id="ct-view"]/div/div/div[1]/a',
                '.user-info',
                '.mypage-user'
            ]
            
            for selector in selectors:
                try:
                    element = self.page.wait_for_selector(selector, timeout=10000)
                    if element and element.is_visible():
                        self.logger.info(f"로그인 확인 성공: {selector}")
                        return True
                except:
                    continue
            
            # 로그인 버튼 확인
            login_button = self.page.query_selector("a[href*='login']")
            if login_button:
                self.logger.error("로그인 상태 확인: 로그인되지 않음")
                return False
            
            self.logger.error("로그인 상태를 확인할 수 없습니다")
            return False
                
        except Exception as e:
            self.logger.error(f"로그인 상태 확인 중 오류 발생: {str(e)}")
            return False

    def setup_driver(self):
        """Playwright 설정"""
        try:
            # Playwright 브라우저만 설치 (의존성 설치 제외)
            subprocess.run(['playwright', 'install', 'chromium'], check=True)
            
            self.playwright = sync_playwright().start()
            
            browser_options = {
                "headless": True,
                "args": [
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-software-rasterizer",
                    "--disable-dev-shm-usage",
                    "--start-maximized",
                    "--window-size=1920,1080"
                ]
            }
            
            # chromium 브라우저 사용
            self.browser = self.playwright.chromium.launch(**browser_options)
            self.page = self.browser.new_page(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
            )
            
            # 쿠키 설정
            self.page.goto("https://www.yeoshin.co.kr")
            
            cookies = [
                {"name": "_kau", "value": os.getenv("_kau"), "domain": ".yeoshin.co.kr", "path": "/"},
                {"name": "_kahai", "value": os.getenv("_kahai"), "domain": ".yeoshin.co.kr", "path": "/"},
                {"name": "_karmt", "value": os.getenv("_karmt"), "domain": ".yeoshin.co.kr", "path": "/"},
                {"name": "_kawlt", "value": os.getenv("_kawlt"), "domain": ".yeoshin.co.kr", "path": "/"},
                {"name": "access_token", "value": os.getenv("ACCESS_TOKEN"), "domain": ".yeoshin.co.kr", "path": "/"}
            ]

            for cookie in cookies:
                if cookie["value"] is None:
                    self.logger.warning(f"Missing cookie value for: {cookie['name']}")
                    continue
                try:
                    self.page.context.add_cookies([cookie])
                    self.logger.info(f"쿠키 설정 성공: {cookie['name']}")
                except Exception as e:
                    self.logger.error(f"쿠키 설정 실패 ({cookie['name']}): {str(e)}")

            self.page.reload()
            
            if not self.check_login_status():
                raise Exception("로그인 상태 확인 실패")

        except Exception as e:
            self.logger.error(f"Playwright setup error: {str(e)}")
            raise e

    def wait_for_page_load(self, timeout=30000):
        """페이지 로딩 대기"""
        try:
            self.page.wait_for_load_state("networkidle", timeout=timeout)
            self.page.wait_for_timeout(5000)
        except PlaywrightTimeoutError:
            self.logger.warning("페이지 로딩 시간 초과")

    def scroll_to_load_all(self):
        """전체 페이지 스크롤"""
        for _ in range(5):
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self.page.wait_for_timeout(3000)
            
            try:
                previous_height = self.page.evaluate("document.body.scrollHeight")
                self.page.wait_for_function(
                    "document.body.scrollHeight > arguments[0]",
                    previous_height,
                    timeout=10000
                )
            except PlaywrightTimeoutError:
                break

    def search_keyword(self, keyword, progress_bar):
        """키워드 검색"""
        try:
            self.current_keyword = keyword
            search_url = f"https://www.yeoshin.co.kr/search/category?q={keyword}&tab=events"
            self.page.goto(search_url)
            self.wait_for_page_load()
            progress_bar.progress(0.2)
            
            time.sleep(5)
            self.scroll_to_load_all()
            progress_bar.progress(0.3)
            
        except Exception as e:
            self.logger.error(f"검색 중 오류 발생: {str(e)}")
            raise e

    def get_event_details(self, item, progress_value, progress_bar):
        event_data = {
            'hospital_name': "정보 없음",
            'location': "위치 정보 없음",
            'event_name': "이벤트 정보 없음",
            'option_name': "옵션 정보 없음",
            'price': "가격 정보 없음",
            'rating': "N/A",
            'review_count': "N/A",
            'scrap_count': "N/A",
            'inquiry_count': "N/A",
            'detail_link': "N/A"
        }
        
        try:
            # 상세 페이지에서 바로 정보 추출 시작
            self.logger.info("상세 페이지에서 정보 추출 시작...")
            
            # 이벤트명 추출
            self.logger.info("이벤트명 추출 시도...")
            event_name_selectors = [
                '//*[@id="ct-view"]/div/div/div[1]/div[2]/article/h1/span',
                '#ct-view > div > div > div.relative.flex-col > div.sc-68757109-1.kfwxBJ > article > h1 > span'
            ]
            
            for selector in event_name_selectors:
                try:
                    element = self.page.wait_for_selector(selector, timeout=5000)
                    event_data['event_name'] = element.text.strip()
                    self.logger.info(f"이벤트명 추출 성공: {event_data['event_name']}")
                    break
                except Exception as e:
                    self.logger.debug(f"이벤트명 선택자 {selector} 실패: {str(e)}")
            
            # 평점 추출
            self.logger.info("평점 추출 시도...")
            rating_selectors = [
                '//*[@id="ct-view"]/div/div/div[1]/div[2]/article/section[1]/div[2]/div/div/span',
                '#ct-view > div > div > div.relative.flex-col > div.sc-68757109-1.kfwxBJ > article > section.flex.flex-col.justify-center.w-full.gap-\\[8px\\] > div.flex.items-end.justify-between.w-full > div > div > span'
            ]
            
            for selector in rating_selectors:
                try:
                    element = self.page.wait_for_selector(selector, timeout=5000)
                    event_data['rating'] = element.text.strip()
                    self.logger.info(f"평점 추출 성공: {event_data['rating']}")
                    break
                except Exception as e:
                    self.logger.debug(f"평점 선택자 {selector} 실패: {str(e)}")
            
            # 리뷰 수 추출
            self.logger.info("리뷰 수 추출 시도...")
            review_count_selectors = [
                '//*[@id="ct-view"]/div/div/div[1]/div[2]/article/section[1]/div[2]/div/span',
                '#ct-view > div > div > div.relative.flex-col > div.sc-68757109-1.kfwxBJ > article > section.flex.flex-col.justify-center.w-full.gap-\\[8px\\] > div.flex.items-end.justify-between.w-full > div > span'
            ]
            
            for selector in review_count_selectors:
                try:
                    element = self.page.wait_for_selector(selector, timeout=5000)
                    event_data['review_count'] = element.text.strip()
                    self.logger.info(f"리뷰 수 추출 성공: {event_data['review_count']}")
                    break
                except Exception as e:
                    self.logger.debug(f"리뷰 선택자 {selector} 실패: {str(e)}")
            
            # 병원명 추출
            self.logger.info("병원명 추출 시도...")
            hospital_name_selectors = [
                '//*[@id="ct-view"]/div/div/div[1]/div[2]/div[1]/article/div/div/p',
                '#ct-view > div > div > div.relative.flex-col > div.sc-68757109-1.kfwxBJ > div.sc-1543ab3d-0.sc-1543ab3d-1.sc-509fd85f-0.hQTMVb.bVOgYk.jlAXoU > article > div > div > p'
            ]
            
            for selector in hospital_name_selectors:
                try:
                    element = self.page.wait_for_selector(selector, timeout=5000)
                    event_data['hospital_name'] = element.text.strip()
                    self.logger.info(f"병원명 추출 성공: {event_data['hospital_name']}")
                    break
                except Exception as e:
                    self.logger.debug(f"병원명 선택자 {selector} 실패: {str(e)}")
            
            # 위치 정보 추출
            self.logger.info("위치 정보 추출 시도...")
            location_selectors = [
                '//*[@id="ct-view"]/div/div/div[1]/div[2]/div[1]/article/section[2]/div/div/span[1]',
                '#ct-view > div > div > div.relative.flex-col > div.sc-68757109-1.kfwxBJ > div.sc-1543ab3d-0.sc-1543ab3d-1.sc-509fd85f-0.hQTMVb.bVOgYk.jlAXoU > article > section:nth-child(3) > div > div > span:nth-child(2)'
            ]
            
            for selector in location_selectors:
                try:
                    element = self.page.wait_for_selector(selector, timeout=5000)
                    event_data['location'] = element.text.strip()
                    self.logger.info(f"위치 정보 추출 성공: {event_data['location']}")
                    break
                except Exception as e:
                    self.logger.debug(f"위치 정보 선택자 {selector} 실패: {str(e)}")
            
            # 문의수와 스크랩수 추출
            try:
                # 문의수 추��
                inquiry_count_selectors = [
                    '//*[@id="ct-view"]/div/div/div[1]/div[2]/div[4]/div[1]/div/p[2]',
                    '#ct-view > div > div > div.relative.flex-col > div.sc-68757109-1.kfwxBJ > div.sc-1543ab3d-0.sc-1543ab3d-1.sc-2ad9e729-2.hQTMVb.jrOHqu.bpXUeM > div.sc-1543ab3d-0.sc-1543ab3d-1.hQTMVb.iHBozd > div > p.sc-78093dd3-0.sc-78093dd3-1.knAupo.ePvHjs'
                ]
                
                for selector in inquiry_count_selectors:
                    try:
                        inquiry_count = self.page.wait_for_selector(selector, timeout=5000).text.strip()
                        event_data['inquiry_count'] = inquiry_count
                        self.logger.info(f"문의수 추출 성공: {inquiry_count}")
                        break
                    except Exception as e:
                        self.logger.debug(f"문의수 선택자 {selector} 실패: {str(e)}")
                        continue

                # 스크랩수 추출
                scrap_count_selectors = [
                    '//*[@id="ct-view"]/div/div/section/div[1]/div/p',
                    '#ct-view > div > div > section > div.sc-1543ab3d-0.sc-1543ab3d-1.hQTMVb.dtvKsa > div > p'
                ]
                
                for selector in scrap_count_selectors:
                    try:
                        scrap_count = self.page.wait_for_selector(selector, timeout=5000).text.strip()
                        event_data['scrap_count'] = scrap_count
                        self.logger.info(f"스크랩수 추출 성공: {scrap_count}")
                        break
                    except Exception as e:
                        self.logger.debug(f"스크랩수 선택자 {selector} 실패: {str(e)}")
                        continue

            except Exception as e:
                self.logger.error(f"문의수/스크랩수 추출 실패: {str(e)}")
            
            # 옵션 정보 추출
            self.logger.info("옵션 정보 추출 시도...")
            options_data = []  # 옵션 정보를 저장할 리스트
            try:
                # 구매하기 버튼이 있는 섹션 찾기
                section_selector = '//*[@id="ct-view"]/div/div/section'
                section = self.page.wait_for_selector(section_selector, timeout=5000)
                self.logger.info("구매하기 버튼 섹션 찾기 성공")

                # 섹션 내의 모든 버튼 찾기
                buttons = section.query_selector_all("button")
                self.logger.info(f"발견된 버튼 수: {len(buttons)}")

                # 버튼 클릭 시도
                purchase_button_clicked = False
                if len(buttons) == 1:  # 버튼이 하나만 있는 경우
                    try:
                        self.page.evaluate("arguments[0].click();", buttons[0])
                        self.logger.info("단일 구매하기 버튼 클릭 성공")
                        purchase_button_clicked = True
                    except Exception as e:
                        self.logger.error(f"단일 구매하기 버튼 클릭 실패: {str(e)}")
                
                elif len(buttons) >= 2:  # 버튼이 두 개 이상인 경우
                    try:
                        self.page.evaluate("arguments[0].click();", buttons[1])  # 두 번째 버튼 클릭
                        self.logger.info("두 번째 구매하기 버튼 클릭 성공")
                        purchase_button_clicked = True
                    except Exception as e:
                        self.logger.error(f"두 번째 구매하기 버튼 클릭 실패: {str(e)}")
                
                if not purchase_button_clicked:
                    self.logger.error("구매하기 버튼 클릭 실패")
                    return [event_data]

                time.sleep(2)  # 모달창이 열리기를 기다림

                # 옵션 리스트 컨테이너 찾기
                options_container_selector = '//*[@id="ct-view"]/div/div/div[2]/div/div/div/div[2]/div[2]'
                options_container = self.page.wait_for_selector(options_container_selector, timeout=10000)
                self.logger.info("옵션 리스트 컨테이너 찾기 성공")

                # 개별 옵션들 찾기
                idx = 1
                while True:
                    try:
                        # 개별 옵션 영역
                        option_selector = f"{options_container_selector}/div[{idx}]"
                        option_element = self.page.wait_for_selector(option_selector, timeout=5000)
                        
                        # 옵션명 추출
                        option_name = option_element.query_selector("div > p").text.strip()
                        
                        # 가격 추출
                        price = option_element.query_selector("p").text.strip()
                        
                        # 데이터 저장
                        option_data = event_data.copy()
                        option_data['option_name'] = option_name
                        option_data['price'] = price
                        options_data.append(option_data)
                        
                        self.logger.info(f"옵션 {idx} 추출 성공 - 이름: {option_name}, 가격: {price}")
                        idx += 1
                        
                    except Exception as e:
                        self.logger.info(f"총 {idx-1}개의 옵션 추출 완료")
                        break
                    except Exception as e:
                        self.logger.error(f"옵션 {idx} 추출 중 오류 발생: {str(e)}")
                        break
                
                return options_data if options_data else [event_data]
                
            except Exception as e:
                self.logger.error(f"옵션 정보 처리 실패: {str(e)}")
                return [event_data]
            
            # 추출된 데이터 확인 로그
            self.logger.info("추출된 데이터:")
            for key, value in event_data.items():
                self.logger.info(f"{key}: {value}")
            
            return event_data
            
        except Exception as e:
            self.logger.error(f"이벤트 상세 정보 추출 중 오류 발생: {str(e)}")
            return None

    def scrape_data(self, keyword, progress_bar):
        try:
            self.cleanup()
            self.setup_driver()
            
            if not self.check_login_status():
                raise Exception("로그인 상태 확인 실패")
            
            self.search_keyword(keyword, progress_bar)
            time.sleep(5)
            self.scroll_to_load_all()

            # 검색 결과 리스트 컨테이너 찾기
            list_container_selectors = [
                '//*[@id="ct-view"]/div/main/article/section[2]/section',
                '#ct-view > div > main > article > section:nth-child(2) > section'
            ]
            
            container = None
            for selector in list_container_selectors:
                try:
                    container = self.page.wait_for_selector(selector, timeout=10000)
                    if container:
                        self.logger.info("검색 결과 리스트 컨테이너 찾기 성공")
                        break
                except:
                    continue
                
            if not container:
                raise Exception("검색 결과 리스트 컨테이너를 찾을 수 없습니다")
            
            # 컨테이너 내의 모든 이벤트 항목 찾기 (div[n]/article 패턴 사용)
            events = []
            idx = 1
            while True:
                try:
                    event_selector = (
                        f"{list_container_selectors[0]}/div[{idx}]/article" if list_container_selectors[0].startswith('/')
                        else f"{list_container_selectors[1]} > div:nth-child({idx}) > article"
                    )
                    event = self.page.wait_for_selector(event_selector, timeout=10000)
                    events.append(event)
                    self.logger.info(f"{idx}번째 이벤트 요소 찾기 성공")
                    idx += 1
                except Exception as e:
                    break
            
            total_items = len(events)
            self.logger.info(f"총 {total_items}개의 이벤트를 찾았습니다")
            
            # 모든 이벤트의 데이터를 저장할 리스트
            all_events_data = []
            
            # 각 이벤트마다 상세 정보 수집
            for idx in range(1, total_items + 1):
                try:
                    self.logger.info(f"\n=== {idx}번째 이벤트 처리 시작 ({idx}/{total_items}) ===")
                    progress_value = 0.3 + (0.7 * (idx / total_items))
                    
                    # 현재 URL 저장
                    current_url = self.page.url
                    self.logger.info(f"현재 URL: {current_url}")
                    
                    # 매번 새로운 이벤트 요소 찾기
                    event_selector = (
                        f"{list_container_selectors[0]}/div[{idx}]/article" if list_container_selectors[0].startswith('/')
                        else f"{list_container_selectors[1]} > div:nth-child({idx}) > article"
                    )
                    
                    # 이벤트 요소 찾기 및 클릭
                    try:
                        event = self.page.wait_for_selector(event_selector, timeout=10000)
                        self.page.evaluate("arguments[0].click();", event)
                        time.sleep(3)
                        self.logger.info(f"{idx}번째 이벤트 클릭 성공")
                        
                        # 이벤트 상세 정보 수집
                        item_data = self.get_event_details(None, progress_value, progress_bar)
                        if item_data:
                            all_events_data.extend(item_data)
                            self.logger.info(f"{idx}번째 이벤트 데이터 수집 성공")
                        
                        # 검색 결과 페이지로 돌아가기
                        self.page.goto(current_url)
                        self.wait_for_page_load()
                        time.sleep(2)  # 페이지 로딩 대기 추가
                        
                    except Exception as e:
                        self.logger.error(f"{idx}번째 이벤트 처리 실패: {str(e)}")
                        continue
                    
                    progress_bar.progress(progress_value)
                    
                except Exception as e:
                    self.logger.error(f"{idx}번째 이벤트 처리 중 오류 발생: {str(e)}")
                    continue

            self.logger.info(f"\n=== 전체 {total_items}개 중 {len(all_events_data)}개 이벤트 데이터 수집 완료 ===")
            
            return pd.DataFrame(all_events_data)
                
        except Exception as e:
            self.logger.error(f"스크래핑 중 오류 발생: {str(e)}")
            return pd.DataFrame()
        finally:
            self.cleanup()

def create_visualizations(df):
    """데이터 시각화 생성"""
    def clean_price(price_str):
        try:
            numbers = re.findall(r'\d+', price_str)
            if numbers:
                return int(''.join(numbers))
            return None
        except:
            return None
    
    df_viz = df.copy()
    df_viz['price_cleaned'] = df_viz['가격'].apply(clean_price)
    df_viz = df_viz[df_viz['price_cleaned'].notna()]
    
    df_first_options = df_viz.groupby(['병원명', '위치']).first().reset_index()
    
    fig_price = px.bar(
        df_first_options.groupby('위치')['price_cleaned'].mean().reset_index(),
        x='위치',
        y='price_cleaned',
        title='지역별 대 옵션 격 평균',
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
    try:
        st.write("Claude API 키 확인:", os.getenv("CLAUDE_API_KEY")[:10] + "...")  # API 키의 처음 10자만 표시
        anthropic = Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))
        st.write("Anthropic 객체 생성 완료")   
             
        # 데이터 전처리
        analysis_data = df.copy()
        analysis_data['exposure_order'] = analysis_data.index + 1
        
        prompt = f"""
        여신티켓의 시술 이벤트 데이터를 분석하여, 새로운 이벤트를 등록하려는 원에 도움이 될 만한 인사이트를 제공해주세요.
        
        아래 형식에 맞춰 분석해주세요:
        
        A. 옵션 분석
        1. 옵션 패턴 분석
        2. 가격대별 옵션 구성 특징
        3. 평균 옵션 개수 분석
        
        B. 첫 번째 옵션 분석
        1. 일반적인 첫 번째 옵션 패턴
        2. 가격 비교
        
        C. 위치 기반 분석
        1. 지역별 특성
        
        D. 고객 반응 분석
        1. 고객 반응 상세 분석
        
        분석 시 다음 가이드라인을 준수해주세요:
        1. 실��� 예시와 수를 근로 들어 분석해주세요.
        2. 가격에 대한 분석을 할 때에는 정확한 금액과 실제 예시를 들어서 설명해주세요.
        3. 분석할 때 주의사항:
            - 가격이나 용량의 범위를 표현할 때는 '~' 대신 '부터', '까지' 또는 '-' 를 사용해주세요.
        
        마지막으로, 3지 핵심 제언 해주세요.
        
        데이터:
        {analysis_data.to_string()}
        """
        
        response = anthropic.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=2500,
            temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )
        
        try:
            content = response.content[0].text if isinstance(response.content, list) else response.content
            
            st.header("🔍 AI 분석 결과")
            
            sections = {
                "A": "옵션 분석 📊",
                "B": "첫 번째 옵션 분석 💰",
                "C": "위치 기반 분석 📍",
                "D": "고객 반응 분석 👥"
            }
            
            for section, title in sections.items():
                st.subheader(f"{title}")
                section_start = content.find(f"{section}.")
                section_end = content.find(f"{chr(ord(section)+1)}.") if section != "D" else content.find("마지막으로")
                
                if section_start != -1:
                    section_content = content[section_start:section_end].strip()
                    st.markdown(section_content)
            
            # 핵심 제언 표시
            if "핵 제언" in content:
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
        return "분석을 행할 수 없습니다."


def generate_pdf(df, analysis_text, fig_price, fig_dist):
    try:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        
        # 나눔고딕 폰트 경로 지정 및 록
        FONT_PATH = r"C:\Users\mctow\OneDrive\문서\바탕 화면\업무\성형어플\가격조사\여신티켓 웹스크래핑/NanumGothic.ttf"
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
            'location': '치',
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
        
# 테이블 생성 및 스타일 적
        table = Table(table_data, repeatRows=1)
        table.setStyle(table_style)
        elements.append(table)
        
        try:
            # 시각화 섹션 제목
            elements.append(Spacer(1, 30))
            elements.append(Paragraph('데이터 시각화', styles['KoreanHeading1']))
            
            # 그프 이미지 저장 및 추가
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
        
        with st.spinner('태팀장 : 데이터를 수집중입니다...오 걸리니까 커피 한 잔 하고 오세요.)'):
            df = scraper.scrape_data(keyword, progress_bar)
            
        # 먼저 영문 컬럼명으로 데이터 검증
        if not df.empty and validate_data(df):
            st.success("데이터 수집이 완료되었습니다!")
            
            # 검증 후 컬명을 한글로 경
            column_names = {
                'hospital_name': '병원명',
                'location': '위치',
                'event_name': '이벤트명',
                'option_name': '옵션명',
                'price': '가격',
                'rating': '평점',
                'review_count': '리뷰수',
                'scrap_count': '스크랩수',
                'inquiry_count': '문의���',
                'detail_link': '상세링크'
            }
            df = df.rename(columns=column_names)
            
            # 데이터프레임을 크롤 가능한 컨테이너에 표시
            st.write("수집된 데이터:")
            st.dataframe(df, height=400)
            
            # 시각화
            fig_price = create_visualizations(df)
            st.plotly_chart(fig_price)
            
            # Claude AI 분석
            with st.spinner('AI 분석을 수행입다...'):
                analysis_text = analyze_with_claude(df)
            
            try:
                pdf_bytes = generate_pdf(df, analysis_text, fig_price, None)
                if pdf_bytes:
                    st.download_button(
                        label="PDF 보기서 다운로드",
                        data=pdf_bytes,
                        file_name=f"yeoshin_{keyword}_report.pdf",
                        mime="application/pdf"
                    )
                else:
                    st.error("PDF 생성에 실패했습니다.")
            except Exception as e:
                st.error(f"PDF 처리 중 오류가 발생했습니다: {str(e)}")
        else:
            st.warning("검색 결과가 없거나 데이터 형식이 올바르지 않습니다. 다른 키워드로 시도���보세요.")

if __name__ == "__main__":
    main()
