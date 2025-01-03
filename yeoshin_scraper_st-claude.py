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

# OpenAI import 추가
from openai import OpenAI

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
            try:
                # 현재 높이 저장
                previous_height = self.page.evaluate("document.body.scrollHeight")
                
                # 스크롤 수행
                self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                self.page.wait_for_timeout(3000)
                
                # 새로운 컨텐츠가 로드되었는지 확인
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
            
            time.sleep(2)
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
            # 메모리 정리를 위한 가비지 컬렉션 추가
            import gc
            gc.collect()
            
            self.cleanup()
            self.setup_driver()
            
            # 네트워크 상태 확인
            try:
                self.page.goto("https://www.yeoshin.co.kr", timeout=30000)
            except PlaywrightTimeoutError:
                raise Exception("네트워크 연결이 불안정합니다. 다시 시도해주세요.")
            
            # 메모리 사용량 모니터링
            import psutil
            process = psutil.Process()
            if process.memory_info().rss > 1024 * 1024 * 1024:  # 1GB 이상
                self.cleanup()
                raise Exception("메모리 사용량이 너무 높습니다. 다시 시도해주세요.")
            
            if not self.check_login_status():
                raise Exception("로그인 상태 확인 실패")
            
            self.search_keyword(keyword, progress_bar)
            time.sleep(2)
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

            # 모든 이벤트의 데이터를 저장할 리스트
            all_events_data = []
            
            # 데이터 처리 시 청크 단위로 처리
            chunk_size = 10
            for idx in range(1, min(total_items + 1, MAX_ITEMS + 1), chunk_size):
                chunk_end = min(idx + chunk_size, min(total_items + 1, MAX_ITEMS + 1))
                current_chunk = []
                
                for item_idx in range(idx, chunk_end):
                    try:
                        self.logger.info(f"\n=== {item_idx}번째 이벤트 처리 시작 ({item_idx}/{min(total_items, MAX_ITEMS)}) ===")
                        progress_value = 0.3 + (0.7 * (item_idx / min(total_items, MAX_ITEMS)))
                        
                        # 현재 URL 저장
                        current_url = self.page.url
                        self.logger.info(f"현재 URL: {current_url}")
                        
                        # 이벤트 요소 찾기 및 클릭
                        event_selector = (
                            f"{list_container_selectors[0]}/div[{item_idx}]/article" if list_container_selectors[0].startswith('/')
                            else f"{list_container_selectors[1]} > div:nth-child({item_idx}) > article"
                        )
                        
                        try:
                            # click() 메서드 직접 사용
                            event = self.page.locator(event_selector)
                            event.click()
                            time.sleep(1)
                            self.logger.info(f"{item_idx}번째 이벤트 클릭 성공")
                            
                            # 이벤트 상세 정보 수집
                            item_data = self.get_event_details(None, progress_value, progress_bar)
                            if item_data:
                                current_chunk.extend(item_data)
                                self.logger.info(f"{item_idx}번째 이벤트 데이터 수집 성공")
                            
                            # 검색 결과 페이지로 돌아가기
                            self.page.goto(current_url)
                            self.wait_for_page_load()
                            time.sleep(1)
                            
                        except Exception as e:
                            self.logger.error(f"{item_idx}번째 이벤트 처리 실패: {str(e)}")
                            continue
                        
                        progress_bar.progress(progress_value)
                        
                    except Exception as e:
                        self.logger.error(f"{item_idx}번째 이벤트 처리 중 오류 발생: {str(e)}")
                        continue
                
                # 청크 단위로 데이터 추가
                all_events_data.extend(current_chunk)
                gc.collect()  # 청크 처리 후 메모리 정리

            self.logger.info(f"\n=== 전체 {total_items}개 중 {len(all_events_data)}개 이벤트 데이터 수집 완료 ===")
            
            return pd.DataFrame(all_events_data)
                
        except Exception as e:
            self.logger.error(f"스크래핑 중 오류 발생: {str(e)}")
            self.cleanup()
            raise
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

def preprocess_data_for_analysis(df):
    """AI 분석을 위한 데이터 전처리"""
    try:
        # 1. 통계적 요약 생성
        summary_stats = {
            '총 데이터 수': len(df),
            '평균 가격': df['가격'].apply(lambda x: float(re.sub(r'[^\d.]', '', x)) if isinstance(x, str) else x).mean(),
            '평균 리뷰수': df['리뷰수'].apply(lambda x: float(re.sub(r'[^\d.]', '', x)) if isinstance(x, str) else x).mean(),
            '평균 스크랩수': df['스크랩수'].apply(lambda x: float(re.sub(r'[^\d.]', '', x)) if isinstance(x, str) else x).mean(),
            '평균 문의수': df['문의수'].apply(lambda x: float(re.sub(r'[^\d.]', '', x)) if isinstance(x, str) else x).mean(),
        }
        
        # 2. 지역별 분석
        location_stats = df.groupby('위치').agg({
            '병원명': 'count',
            '가격': lambda x: x.apply(lambda y: float(re.sub(r'[^\d.]', '', str(y)))).mean()
        }).reset_index()
        location_stats.columns = ['위치', '병원수', '평균가격']
        
        # 3. 상위 성과 병원 추출 (스크랩수 기준)
        top_hospitals = df.nlargest(5, '스크랩수')[['병원명', '위치', '가격', '스크랩수']]
        
        # 4. 이벤트명 키워드 분석
        keywords = ' '.join(df['이벤트명'].astype(str)).split()
        keyword_freq = pd.Series(keywords).value_counts().head(10)
        
        # 요약 데이터 생성
        analysis_summary = {
            'summary_stats': summary_stats,
            'location_stats': location_stats.to_dict('records'),
            'top_hospitals': top_hospitals.to_dict('records'),
            'top_keywords': keyword_freq.to_dict()
        }
        
        return analysis_summary
        
    except Exception as e:
        st.error(f"데이터 전처리 중 오류 발생: {str(e)}")
        return None

def analyze_with_openai(df):
    try:
        # 1. API 키 확인
        try:
            api_key = st.secrets.env.OPENAI_API_KEY
            client = OpenAI(api_key=api_key)
        except Exception as e:
            st.error(f"API 키를 찾을 수 없습니다: {str(e)}")
            return "API 키 없음"

        # 2. 데이터 전처리
        analysis_summary = preprocess_data_for_analysis(df)
        if not analysis_summary:
            return "데이터 전처리 실패"

        # 3. API 호출
        try:
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[{
                    "role": "system",
                    "content": "당신은 피부과 마케팅 전문가입니다. 요약된 데이터를 기반으로 실질적이고 구체적인 인사이트를 제공해주세요."
                },
                {
                    "role": "user",
                    "content": f"""다음 여신티켓 데이터 요약을 분석하여 인사이트를 제공해주세요:

[데이터 요약]
1. 전체 통계:
{analysis_summary['summary_stats']}

2. 지역별 통계:
{analysis_summary['location_stats']}

3. 상위 성과 병원:
{analysis_summary['top_hospitals']}

4. 주요 키워드:
{analysis_summary['top_keywords']}

다음 형식으로 분석 결과를 제공해주세요:
1. 핵심 인사이트 (상위 3개)
2. 상세 분석 결과
3. 실행 가능한 전략 제안"""
                }],
                temperature=0
            )
        except Exception as e:
            st.error(f"API 호출 실패: {str(e)}")
            return "API 호출 실패"

        return response.choices[0].message.content

    except Exception as e:
        st.error(f"전체 프로세스 실패: {str(e)}")
        return "분석을 수행할 수 없습니다."

def main():
    st.title("여신티켓 데이터 스크래퍼")
    
    # 세션 상태 초기화
    if 'df' not in st.session_state:
        st.session_state.df = None
    if 'analysis_text' not in st.session_state:
        st.session_state.analysis_text = None
    if 'fig_price' not in st.session_state:
        st.session_state.fig_price = None
    if 'scraping_in_progress' not in st.session_state:
        st.session_state.scraping_in_progress = False
    if 'current_progress' not in st.session_state:
        st.session_state.current_progress = 0
    
    keyword = st.text_input("검색할 키워드를 입력하세요:")
    
    if st.button("스크래핑 시작"):
        st.session_state.scraping_in_progress = True
        try:
            progress_bar = st.progress(st.session_state.current_progress)
            scraper = YeoshinScraper()
            
            # 데이터 수집
            with st.spinner('태팀장 : 데이터를 수집중입니다...오래 걸리니까 커피 한 잔 하고 오세요:)'):
                df = scraper.scrape_data(keyword, progress_bar)
                st.session_state.df = df
                st.session_state.current_progress = 1.0
            
            # 먼이터 검증 및 표시
            if not st.session_state.df.empty and validate_data(st.session_state.df):
                st.success("데이터 수집이 완료되었습니다!")
                
                # 컬럼명을 한글로 변경
                column_names = {
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
                st.session_state.df = st.session_state.df.rename(columns=column_names)
                
                # 수집된 데이터 즉시 표시
                st.write("수집된 데이터:")
                st.dataframe(st.session_state.df, height=400)
                
                # 시각화 생성 및 표시
                st.session_state.fig_price = create_visualizations(st.session_state.df)
                st.plotly_chart(st.session_state.fig_price)
                
                # AI 분석 시작
                with st.spinner('AI 분석을 수행중입니다...'):
                    analysis_result = analyze_with_openai(st.session_state.df)
                    st.session_state.analysis_text = analysis_result
                    
                    # AI 분석 결과 표시
                    st.subheader("AI 분석 결과")
                    st.write(analysis_result)
        except Exception as e:
            st.error(f"스크래핑 중 오류 발생: {str(e)}")
        finally:
            st.session_state.scraping_in_progress = False

    # 초기화 버튼
    if st.session_state.df is not None:
        if st.button("새로운 검색 시작"):
            st.session_state.df = None
            st.session_state.analysis_text = None
            st.session_state.fig_price = None
            st.experimental_rerun()

if __name__ == "__main__":
    main()
