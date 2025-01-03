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
from concurrent.futures import ThreadPoolExecutor
import asyncio

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
        try:
            if self.page:
                self.page.close()
                self.logger.info("페이지가 성공적으로 종료되었습니다.")
        except Exception as e:
            self.logger.error(f"페이지 종료 중 오류: {str(e)}")
        
        try:
            if self.browser:
                self.browser.close()
                self.logger.info("브라우저가 성공적으로 종료되었습니다.")
        except Exception as e:
            self.logger.error(f"브라우저 종료 중 오류: {str(e)}")
        
        try:
            if self.playwright:
                self.playwright.stop()
                self.logger.info("Playwright가 성공적으로 종료되었습니다.")
        except Exception as e:
            self.logger.error(f"Playwright 종료 중 오류: {str(e)}")
        
        # 모든 참조 초기화
        self.page = None
        self.browser = None
        self.playwright = None

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
            # 사용 가능한 secrets 키 확인
            self.logger.info("Available secrets keys:")
            for key in st.secrets:
                self.logger.info(f"- {key}")
                if key == 'env':
                    self.logger.info("env 내부 키:")
                    for env_key in st.secrets.env:
                        self.logger.info(f"  - {env_key}")
            
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
            
            # secrets에서 쿠키 값 가져오기 시도
            try:
                required_cookies = {
                    '_kau': st.secrets.env._kau,  # 원래 키 이름 사용
                    '_kahai': st.secrets.env._kahai,
                    '_karmt': st.secrets.env._karmt,
                    '_kawlt': st.secrets.env._kawlt,
                    'access_token': st.secrets.env.ACCESS_TOKEN
                }
            except Exception as e:
                self.logger.error(f"Secrets 접근 오류: {str(e)}")
                raise Exception("필수 쿠키 값을 secrets에서 찾을 수 없습니다.")
            
            # 필수 쿠키 중 하나라도 없으면 에러 발생
            missing_cookies = [name for name, value in required_cookies.items() if not value]
            if missing_cookies:
                raise Exception(f"필수 쿠키가 없습니다: {', '.join(missing_cookies)}")
            
            self.page.goto("https://www.yeoshin.co.kr")
            
            # 유효한 쿠키만 설정
            for name, value in required_cookies.items():
                cookie = {
                    "name": name,
                    "value": value,
                    "domain": ".yeoshin.co.kr",
                    "path": "/"
                }
                try:
                    self.page.context.add_cookies([cookie])
                    self.logger.info(f"쿠키 설정 성공: {name}")
                except Exception as e:
                    self.logger.error(f"쿠키 설정 실패 ({name}): {str(e)}")
                    raise Exception(f"쿠키 설정 실패: {name}")

            self.page.reload()
            
            # 로그인 상태 확인
            if not self.check_login_status():
                raise Exception("로그인 상태 확인 실패")
            
        except Exception as e:
            self.logger.error(f"Playwright setup error: {str(e)}")
            raise e

    def wait_for_page_load(self, timeout=15000):
        """페이지 로딩 대기"""
        try:
            self.page.wait_for_load_state("networkidle", timeout=timeout)
            self.page.wait_for_timeout(2000)
        except PlaywrightTimeoutError:
            self.logger.warning("페이지 로딩 시간 초과")

    def scroll_to_load_all(self):
        """전체 페이지 스크롤"""
        for _ in range(3):
            try:
                previous_height = self.page.evaluate("document.body.scrollHeight")
                self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                self.page.wait_for_timeout(1500)
                
                current_height = self.page.evaluate("document.body.scrollHeight")
                if current_height == previous_height:
                    break
                
            except PlaywrightTimeoutError:
                self.logger.warning("스크롤 타임아웃")
                break
            except Exception as e:
                self.logger.error(f"스크롤 중 오류 발생: {str(e)}")
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
        """이벤트 상세 정보 추출"""
        event_data = []
        try:
            self.logger.info("상세 페이지에서 정보 추출 시작...")
            
            # 이벤트명 추출
            self.logger.info("이벤트명 추출 시도...")
            
            # NEW 태그가 있는 경우의 이벤트명 셀렉터
            new_event_selector = '//*[@id="ct-view"]/div/div/div[1]/div[2]/article/h1/span[2]'
            
            # 일반적인 경우의 이벤트명 셀렉터
            regular_event_selectors = [
                '//*[@id="ct-view"]/div/div/div[1]/div[2]/article/h1/span',
                '#ct-view > div > div > div.relative.flex-col > div.sc-68757109-1.kfwxBJ > article > h1 > span'
            ]
            
            event_name = None
            
            # 먼저 NEW 태그가 있는지 확인
            try:
                new_tag = self.page.locator('//*[@id="ct-view"]/div/div/div[1]/div[2]/article/h1/span[1]').first
                if new_tag and 'NEW' in new_tag.text_content().strip().upper():
                    # NEW 태그가 있는 경우, span[2]에서 이벤트명 추출
                    element = self.page.locator(new_event_selector).first
                    if element:
                        event_name = element.text_content().strip()
                        self.logger.info(f"NEW 태그가 있는 이벤트명 추출 성공 - 값: {event_name}")
            except Exception as e:
                self.logger.debug(f"NEW 태그 확인 중 예외 발생: {str(e)}")
            
            # NEW 태그에서 추출 실패하거나 NEW 태그가 없는 경우, 기존 방식으로 시도
            if not event_name:
                for selector in regular_event_selectors:
                    try:
                        element = self.page.locator(selector).first
                        if element:
                            event_name = element.text_content().strip()
                            self.logger.info(f"일반 이벤트명 추출 성공 - 값: {event_name}")
                            break
                    except Exception as e:
                        continue

            # 평점과 리뷰수 추출
            try:
                # 평점과 리뷰수가 있는 컨테이너 먼저 찾기
                rating_container_xpath = '//*[@id="ct-view"]/div/div/div[1]/div[2]/article/section[1]/div[2]/div'
                container = self.page.wait_for_selector(rating_container_xpath, timeout=5000)
                
                if container:
                    # 컨테이너 내에서 평점과 리뷰수 추출
                    rating = self.page.wait_for_selector(f"{rating_container_xpath}/div/span", timeout=2000)
                    review_count = self.page.wait_for_selector(f"{rating_container_xpath}/span", timeout=2000)
                    
                    if rating and review_count:
                        rating = rating.text_content().strip()
                        review_count = review_count.text_content().strip()
                        self.logger.info(f"평점: {rating}, 리뷰수: {review_count}")
                    
            except Exception as e:
                self.logger.error(f"평점/리뷰수 추출 실패: {str(e)}")
                rating = "N/A"
                review_count = "N/A"

            # 병원명 추출
            self.logger.info("병원명 추출 시도...")
            hospital_name_selectors = [
                '//*[@id="ct-view"]/div/div/div[1]/div[2]/div[1]/article/div/div/p',
                '#ct-view > div > div > div.relative.flex-col > div.sc-68757109-1.kfwxBJ > div.sc-1543ab3d-0.sc-1543ab3d-1.sc-509fd85f-0.hQTMVb.bVOgYk.jlAXoU > article > div > div > p'
            ]
            
            hospital_name = None
            for selector in hospital_name_selectors:
                try:
                    element = self.page.locator(selector).first
                    if element:
                        hospital_name = element.text_content().strip()
                        self.logger.info(f"병원명 추출 성공 - 값: {hospital_name}")
                        break
                except Exception as e:
                    continue

            # 위치 정보 추출
            self.logger.info("위치 정보 추출 시도...")
            location_selectors = [
                '//*[@id="ct-view"]/div/div/div[1]/div[2]/div[1]/article/section[2]/div/div/span[1]',
                '#ct-view > div > div > div.relative.flex-col > div.sc-68757109-1.kfwxBJ > div.sc-1543ab3d-0.sc-1543ab3d-1.sc-509fd85f-0.hQTMVb.bVOgYk.jlAXoU > article > section:nth-child(3) > div > div > span:nth-child(2)'
            ]
            
            location = None
            for selector in location_selectors:
                try:
                    element = self.page.locator(selector).first
                    if element:
                        location = element.text_content().strip()
                        self.logger.info(f"위치 정보 추출 성공 - 값: {location}")
                        break
                except Exception as e:
                    continue

            # 문의수 추출
            self.logger.info("문의수 추출 시도...")
            inquiry_count_selectors = [
                '//*[@id="ct-view"]/div/div/div[1]/div[2]/div[4]/div[1]/div/p[2]',
                '#ct-view > div > div > div.relative.flex-col > div.sc-68757109-1.kfwxBJ > div.sc-1543ab3d-0.sc-1543ab3d-1.sc-2ad9e729-2.hQTMVb.jrOHqu.bpXUeM > div.sc-1543ab3d-0.sc-1543ab3d-1.hQTMVb.iHBozd > div > p.sc-78093dd3-0.sc-78093dd3-1.knAupo.ePvHjs'
            ]
            
            inquiry_count = None
            for selector in inquiry_count_selectors:
                try:
                    element = self.page.locator(selector).first
                    if element:
                        inquiry_count = element.text_content().strip()
                        self.logger.info(f"문의수 추출 성공 - 값: {inquiry_count}")
                        break
                except Exception as e:
                    continue

            # 스크랩수 추출
            self.logger.info("스크랩수 추출 시도...")
            scrap_count_selectors = [
                '//*[@id="ct-view"]/div/div/section/div[1]/div/p',
                '#ct-view > div > div > section > div.sc-1543ab3d-0.sc-1543ab3d-1.hQTMVb.dtvKsa > div > p'
            ]
            
            scrap_count = None
            for selector in scrap_count_selectors:
                try:
                    element = self.page.locator(selector).first
                    if element:
                        scrap_count = element.text_content().strip()
                        self.logger.info(f"스크랩수 추출 성공 - 값: {scrap_count}")
                        break
                except Exception as e:
                    continue

            # 기본 데이터 구조 생성
            event_data = {
                'hospital_name': hospital_name or "정보 없음",
                'location': location or "위치 정보 없음",
                'event_name': event_name or "이벤트 정보 없음",
                'rating': rating or "N/A",
                'review_count': review_count or "N/A",
                'inquiry_count': inquiry_count or "N/A",
                'scrap_count': scrap_count or "N/A",
                'option_name': "옵션 정보 없음",
                'price': "가격 정보 없음"
            }

            # 옵션 정보 추출 로직은 그대로 유지...
            
            # 옵션 정보 추출
            self.logger.info("옵션 정보 추출 시도...")
            options_data = []  # 옵션 정보를 저장할 리스트

            try:
                # 구매하기 버튼이 있는 섹션 찾기
                section_selector = '//*[@id="ct-view"]/div/div/section'
                section = self.page.locator(section_selector)
                self.logger.info("구매하기 버튼 섹션 찾기 성공")

                # 섹션 내의 모든 버튼 찾기
                buttons = section.locator("button")
                button_count = buttons.count()
                self.logger.info(f"발견된 버튼 수: {button_count}")

                # 버튼 클릭 시도
                purchase_button_clicked = False
                
                if button_count == 1:
                    try:
                        buttons.first.click()
                        self.logger.info("단일 구매하기 버튼 클릭 성공")
                        purchase_button_clicked = True
                    except Exception as e:
                        self.logger.error(f"단일 구매하기 버튼 클릭 실패: {str(e)}")
                
                elif button_count >= 2:
                    try:
                        buttons.nth(1).click()  # 두 번째 버튼 클릭
                        self.logger.info("두 번째 구매하기 버튼 클릭 성공")
                        purchase_button_clicked = True
                    except Exception as e:
                        self.logger.error(f"두 번째 구매하기 버튼 클릭 실패: {str(e)}")

                if not purchase_button_clicked:
                    self.logger.error("구매하기 버튼 클릭 실패")
                    return [event_data]

                if purchase_button_clicked:
                    # 잠시 대기 후 모달창 확인
                    self.page.wait_for_timeout(5000)  # 5초 대기
                    
                    # 옵션 컨테이너 선택자
                    option_container_selectors = [
                        '//*[@id="ct-view"]/div/div/div[2]/div/div/div/div[2]/div[2]',
                        '#ct-view > div > div > div.fixed.top-0.h-[100%].w-[100vw].z-[999].bg-black.bg-opacity-40.max-w-[var(--mobile-max-width)] > div > div > div > div.h-[100%].max-h-[100%].overflow-auto.scroll-auto.mx-[21px].rounded-bl-[12px].rounded-br-[12px].border.border-solid.border-[#616161].border-t-0 > div.flex.flex-col.w-[(100%)].overflow-y-scroll.bg-[#ffffff]'
                    ]
                    
                    # 옵션 컨테이너 찾기
                    container = None
                    for selector in option_container_selectors:
                        try:
                            container = self.page.wait_for_selector(selector, timeout=10000)
                            if container:
                                self.logger.info(f"옵션 컨테이너 찾기 성공: {selector}")
                                break
                        except Exception as e:
                            self.logger.debug(f"옵션 컨테이너 선택자 {selector} 시도 실패: {str(e)}")
                            continue
                    
                    if not container:
                        self.logger.error("옵션 컨테이너를 찾을 수 없습니다")
                        return [event_data]
                    
                    # 개별 옵션 요소들 찾기
                    options_data = []
                    idx = 1
                    while True:
                        try:
                            # 각 옵션 요소의 XPath 생성
                            option_xpath = f'//*[@id="ct-view"]/div/div/div[2]/div/div/div/div[2]/div[2]/div[{idx}]'
                            option = self.page.wait_for_selector(option_xpath, timeout=5000)
                            
                            if not option:
                                break
                                
                            # 옵션명과 가격 추출 (정확한 XPath 사용)
                            try:
                                option_name_xpath = f'//*[@id="ct-view"]/div/div/div[2]/div/div/div/div[2]/div[2]/div[{idx}]/div/p'
                                price_xpath = f'//*[@id="ct-view"]/div/div/div[2]/div/div/div/div[2]/div[2]/div[{idx}]/p'
                                
                                option_name_element = self.page.wait_for_selector(option_name_xpath, timeout=5000)
                                price_element = self.page.wait_for_selector(price_xpath, timeout=5000)
                                
                                if option_name_element and price_element:
                                    option_name = option_name_element.text_content().strip()
                                    price = price_element.text_content().strip()
                                    
                                    option_data = event_data.copy()
                                    option_data['option_name'] = option_name
                                    option_data['price'] = price
                                    options_data.append(option_data)
                                    self.logger.info(f"옵션 {idx} 추출 성공 - 이름: {option_name}, 가격: {price}")
                            
                            except Exception as e:
                                self.logger.error(f"옵션 {idx} 상세 정보 추출 실패: {str(e)}")
                                continue
                            
                            idx += 1
                            
                        except PlaywrightTimeoutError:
                            self.logger.info(f"더 이상의 옵션이 없습니다. 총 {idx-1}개의 옵션을 찾았습니다.")
                            break
                        except Exception as e:
                            self.logger.error(f"옵션 {idx} 추출 중 오류 발생: {str(e)}")
                            break
                    
                    if not options_data:
                        self.logger.warning("추출된 옵션 정보가 없습니다")
                        return [event_data]
                    
                    return options_data

            except Exception as e:
                self.logger.error(f"옵션 정보 처리 실패: {str(e)}")
                return [event_data]

        except Exception as e:
            self.logger.error(f"이벤트 상세 정보 추출 중 오류: {str(e)}")
            return []

    def scrape_data(self, keyword, progress_bar):
        try:
            self.cleanup()
            self.setup_driver()
            
            if not self.check_login_status():
                raise Exception("로그인 상태 확인 실패")
            
            self.search_keyword(keyword, progress_bar)
            
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
            
            # 먼저 전체 검색 결과 수 파악
            idx = 1
            total_items = 0
            while True:
                try:
                    event_selector = (
                        f"{list_container_selectors[0]}/div[{idx}]/article" if list_container_selectors[0].startswith('/')
                        else f"{list_container_selectors[1]} > div:nth-child({idx}) > article"
                    )
                    event = self.page.wait_for_selector(event_selector, timeout=5000)
                    if event:
                        total_items += 1
                        idx += 1
                except Exception as e:
                    break
            
            self.logger.info(f"총 {total_items}개의 이벤트를 찾았습니다")
            
            # 실제 스크래핑할 이벤트 수 결정
            MAX_ITEMS = 50
            if total_items > MAX_ITEMS:
                st.warning(f"검색 결과가 총 {total_items}개입니다. 안정적인 데이터 수집을 위해 상위 {MAX_ITEMS}개의 이벤트만 수집합니다.")
            else:
                st.info(f"총 {total_items}개의 이벤트가 검색되었습니다.")

            # 병렬 처리를 위한 함수
            def process_single_event(idx):
                try:
                    self.logger.info(f"\n=== {idx}번째 이벤트 처리 시작 ({idx}/{min(total_items, MAX_ITEMS)}) ===")
                    progress_value = 0.3 + (0.7 * (idx / min(total_items, MAX_ITEMS)))
                    
                    current_url = self.page.url
                    
                    event_selector = (
                        f"{list_container_selectors[0]}/div[{idx}]/article" if list_container_selectors[0].startswith('/')
                        else f"{list_container_selectors[1]} > div:nth-child({idx}) > article"
                    )
                    
                    event = self.page.locator(event_selector)
                    event.click()
                    time.sleep(2)  # 기존 3초에서 2초로 감소
                    
                    item_data = self.get_event_details(None, progress_value, progress_bar)
                    
                    self.page.goto(current_url)
                    self.wait_for_page_load()
                    time.sleep(1)  # 기존 2초에서 1초로 감소
                    
                    return item_data
                    
                except Exception as e:
                    self.logger.error(f"{idx}번째 이벤트 처리 실패: {str(e)}")
                    return None

            # ThreadPoolExecutor를 사용한 병렬 처리
            all_events_data = []
            with ThreadPoolExecutor(max_workers=3) as executor:  # 동시에 3개의 이벤트 처리
                futures = [executor.submit(process_single_event, idx) 
                          for idx in range(1, min(total_items + 1, MAX_ITEMS + 1))]
                
                for future in futures:
                    result = future.result()
                    if result:
                        if isinstance(result, list):
                            all_events_data.extend(result)
                        else:
                            all_events_data.append(result)

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
        # 1. API 키 확인 - 직접 ANTHROPIC_API_KEY로 설정
        try:
            api_key = st.secrets.env.CLAUDE_API_KEY
            os.environ["ANTHROPIC_API_KEY"] = api_key  # Anthropic이 사용하는 환경 변수명으로 설정
            st.write("1. API 키 상태:", "있음" if api_key else "없음")
        except Exception as e:
            st.error(f"API 키를 찾을 수 없습니다: {str(e)}")
            return "API 키 없음"
        
        # 2. Anthropic 객체 생성 - 인자 없이 생성
        try:
            client = Anthropic()  # API 키는 환경 변수에서 자동으로 가져감
            st.write("2. Anthropic 객체 생성 성공")
        except Exception as e:
            st.error(f"2. Anthropic 객체 생성 실패: {str(e)}")
            st.error(f"에러 타입: {type(e)}")
            st.error(f"에러 내용: {str(e)}")
            return "Anthropic 객체 생성 실패"

        # 3. 데이터 전처리
        try:
            analysis_data = df.copy()
            analysis_data['exposure_order'] = analysis_data.index + 1
            st.write("3. 데이터 전처리 성공")
        except Exception as e:
            st.error(f"3. 데이터 전처리 실패: {str(e)}")
            return "데이터 전처리 실패"

        # 4. API 호출
        try:
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2500,
                temperature=0,
                messages=[{
                    "role": "user",
                    "content": f"""여신티켓의 시술 이벤트 데이터를 분석하여, 새로운 이벤트를 등록하려는 원에 도움이 될 만한 인사이트를 제공해주세요.
                    
                    데이터:
                    {analysis_data.to_string()}
                    """
                }]
            )
            st.write("4. API 호출 성공")
        except Exception as e:
            st.error(f"4. API 호출 실패: {str(e)}")
            return "API 호출 실패"

        # 5. 응답 처리
        try:
            content = response.content
            if not content:
                st.error("5. 응답이 비어있습니다")
                return "응답이 비어있습니다"
            st.write("5. 응답 처리 성공")
        except Exception as e:
            st.error(f"5. 응답 처리 실패: {str(e)}")
            return "응답 처리 실패"

        return content

    except Exception as e:
        st.error(f"전체 프로세스 실패: {str(e)}")
        return "분석을 수행할 수 없습니다."


def generate_pdf(df, analysis_text, fig_price, fig_dist):
    try:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        
        # 나눔고딕 폰트 경로 수정 (깃허브 루트 디렉토리)
        FONT_PATH = "NanumGothic.ttf"
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

# 데이터 수집 및 처리 로직을 async로 변경
async def process_data(keyword):
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            context = await browser.new_context()
            page = await context.new_page()
            
            # 데이터 수집 로직
            df = await collect_data(page, keyword)
            
            await page.close()
            await context.close()
            await browser.close()
            
            return df
            
    except Exception as e:
        logging.error(f"데이터 수집 중 오류 발생: {str(e)}")
        return None

def main():
    st.title("여신티켓 이벤트 수집기")
    
    keyword = st.text_input("검색어를 입력하세요:")
    
    if st.button("검색 시작") and keyword:
        with st.spinner('데이터를 수집하는 중입니다...'):
            # 비동기 함수 실행을 위한 이벤트 루프 생성
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            st.session_state.df = loop.run_until_complete(process_data(keyword))
            loop.close()
            
        # 먼저 영문 컬럼명으로 데이터 검증
        if not st.session_state.df.empty and validate_data(st.session_state.df):
            st.success("데이터 수집이 완료되었습니다!")
            
            # 검증 후 컬럼명을 한글로 변경
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
            st.session_state.df = st.session_state.df.rename(columns=column_names)
            
            # 시각화
            st.session_state.fig_price = create_visualizations(st.session_state.df)
            
            # Claude AI 분석
            with st.spinner('AI 분석을 수행중입니다...'):
                st.session_state.analysis_text = analyze_with_claude(st.session_state.df)
    
    # 저장된 데이터가 있으면 표시
    if st.session_state.df is not None:
        st.write("수집된 데이터:")
        st.dataframe(st.session_state.df, height=400)
        
        if st.session_state.fig_price is not None:
            st.plotly_chart(st.session_state.fig_price)
        
        if st.session_state.analysis_text is not None:
            try:
                pdf_bytes = generate_pdf(
                    st.session_state.df, 
                    st.session_state.analysis_text, 
                    st.session_state.fig_price, 
                    None
                )
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

    # 초기화 버튼 추가
    if st.session_state.df is not None:
        if st.button("새로운 검색 시작"):
            st.session_state.df = None
            st.session_state.analysis_text = None
            st.session_state.fig_price = None
            st.experimental_rerun()

if __name__ == "__main__":
    main()
