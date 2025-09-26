#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
투자 포트폴리오 데이터 크롤링 GUI 도구
코스피200 및 나스닥100 편입종목 데이터 수집
PyQt5를 사용한 그래픽 사용자 인터페이스
"""

import sys
import os
import time
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timedelta
import yfinance as yf
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.font_manager as fm
import numpy as np

# 한글 폰트 설정
plt.rcParams['font.family'] = ['AppleGothic', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False  # 마이너스 기호 깨짐 방지
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                            QHBoxLayout, QLabel, QPushButton, QLineEdit,
                            QProgressBar, QTableWidget, QTableWidgetItem,
                            QTextEdit, QTabWidget, QGroupBox, QSpinBox,
                            QMessageBox, QFileDialog, QHeaderView, QSplitter,
                            QFrame, QGridLayout, QComboBox)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer
from PyQt5.QtGui import QFont, QIcon, QPalette, QColor

class Kospi200CrawlerThread(QThread):
    """코스피200 크롤링 작업을 별도 스레드에서 실행"""
    progress_updated = pyqtSignal(int, str)  # 진행률, 상태 메시지
    data_updated = pyqtSignal(list)  # 수집된 데이터
    error_occurred = pyqtSignal(str)  # 오류 메시지
    index_info_updated = pyqtSignal(dict)  # 지수 정보

    def __init__(self, limit=50, period_days=30):
        super().__init__()
        self.limit = limit
        self.period_days = period_days
        self.base_url = "https://finance.naver.com/sise/sise_index.naver?code=KPI200"
        self.entry_url = "https://finance.naver.com/sise/entryJongmok.naver"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

    def run(self):
        try:
            # 지수 정보 수집
            self.progress_updated.emit(5, "코스피200 지수 정보 수집 중...")
            index_info = self.get_kospi200_info()
            self.index_info_updated.emit(index_info)

            # 편입 종목 수집
            self.progress_updated.emit(10, "편입 종목 데이터 수집 시작...")
            all_stocks = self.get_entry_stocks()

            if all_stocks:
                # 상위 종목 선별
                self.progress_updated.emit(90, "데이터 정렬 및 처리 중...")
                top_stocks = self.get_top_stocks(all_stocks, self.limit)
                self.data_updated.emit(top_stocks)
                self.progress_updated.emit(100, f"완료! {len(top_stocks)}개 종목 수집됨")
            else:
                self.error_occurred.emit("종목 데이터를 수집할 수 없습니다.")

        except Exception as e:
            self.error_occurred.emit(f"크롤링 중 오류 발생: {str(e)}")

    def get_kospi200_info(self):
        """코스피200 지수 기본 정보를 가져옵니다."""
        try:
            response = self.session.get(self.base_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            index_info = {}

            # 현재 지수값
            current_value = soup.find('span', class_='num')
            if current_value:
                index_info['현재지수'] = current_value.get_text(strip=True)

            # 전일대비 정보
            change_info = soup.find('span', class_='num_s')
            if change_info:
                change_text = change_info.get_text(strip=True)
                index_info['전일대비'] = change_text

            # 등락률
            rate_info = soup.find('span', class_='num_p')
            if rate_info:
                rate_text = rate_info.get_text(strip=True)
                index_info['등락률'] = rate_text

            return index_info

        except Exception as e:
            return {}

    def get_entry_stocks(self):
        """코스피200 편입 종목 정보를 가져옵니다."""
        kospi_symbols = [
            '005930.KS', '000660.KS', '035420.KS', '005490.KS', '051910.KS',
            '006400.KS', '035720.KS', '000270.KS', '068270.KS', '207940.KS',
            '005380.KS', '015760.KS', '000810.KS', '012330.KS', '066570.KS',
            '003550.KS', '323410.KS', '034730.KS', '018260.KS', '055550.KS',
            '096770.KS', '017670.KS', '000720.KS', '105560.KS', '003670.KS',
            '259960.KS', '024110.KS', '086280.KS', '000150.KS', '161890.KS',
            '032830.KS', '047050.KS', '326030.KS', '033780.KS', '086790.KS',
            '003490.KS', '302440.KS', '011200.KS', '042660.KS', '009150.KS',
            '267250.KS', '028260.KS', '251270.KS', '128940.KS', '000060.KS',
            '066970.KS', '004020.KS', '000100.KS', '003410.KS', '010130.KS'
        ]

        all_stocks = []
        total_stocks = len(kospi_symbols)

        for i, symbol in enumerate(kospi_symbols[:self.limit]):
            try:
                progress = 10 + (i * 80 // total_stocks)
                self.progress_updated.emit(progress, f"{symbol} 데이터 수집 중...")

                ticker = yf.Ticker(symbol)
                info = ticker.info

                end_date = datetime.now()
                start_date = end_date - timedelta(days=self.period_days)
                hist = ticker.history(start=start_date, end=end_date)

                if not hist.empty and len(hist) >= 2:
                    current_price = hist['Close'].iloc[-1]
                    start_price = hist['Close'].iloc[0]

                    price_display = f"{start_price:,.0f}원 / {current_price:,.0f}원"
                    period_return = ((current_price - start_price) / start_price) * 100 if start_price != 0 else 0
                    period_return_str = f"{period_return:+.2f}%"

                    prev_price = hist['Close'].iloc[-2] if len(hist) > 1 else start_price
                    daily_change = current_price - prev_price
                    change_str = f"{daily_change:+,.0f}원"

                    # 발행주식수 대비 거래량 비율 계산
                    total_volume = hist['Volume'].sum()
                    shares_outstanding = info.get('sharesOutstanding', 0)
                    volume_ratio = (total_volume / shares_outstanding) * 100 if shares_outstanding else 0
                    volume_str = f"{volume_ratio:.2f}%"


                    clean_symbol = symbol.replace('.KS', '')

                    stock_info = {
                        '종목코드': clean_symbol,
                        '종목명': info.get('longName', clean_symbol),
                        '현재가': price_display,
                        '전일대비': change_str,
                        '등락률': period_return_str,
                        '거래량': volume_str,
                        '시작가': start_price,
                        '종료가': current_price,
                        '기간수익률': period_return
                    }
                    all_stocks.append(stock_info)

                time.sleep(0.2)

            except Exception as e:
                clean_symbol = symbol.replace('.KS', '')
                stock_info = {
                    '종목코드': clean_symbol, '종목명': clean_symbol,
                    '현재가': 'N/A', '전일대비': 'N/A', '등락률': 'N/A', '거래량': 'N/A'
                }
                all_stocks.append(stock_info)
                continue

        return all_stocks

    def get_top_stocks(self, all_stocks, limit):
        """상위 종목만 가져옵니다."""
        def sort_key(stock):
            try:
                return stock.get('기간수익률', -999)
            except:
                return -999

        sorted_stocks = sorted(all_stocks, key=sort_key, reverse=True)
        return sorted_stocks[:limit]

class Nasdaq100CrawlerThread(QThread):
    """나스닥100 크롤링 작업을 별도 스레드에서 실행"""
    progress_updated = pyqtSignal(int, str)  # 진행률, 상태 메시지
    data_updated = pyqtSignal(list)  # 수집된 데이터
    error_occurred = pyqtSignal(str)  # 오류 메시지
    index_info_updated = pyqtSignal(dict)  # 지수 정보

    def __init__(self, limit=50, period_days=30):
        super().__init__()
        self.limit = limit
        self.period_days = period_days
        self.base_url = "https://finance.naver.com/world/sise.naver?symbol=NAS@IXIC"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

    def run(self):
        try:
            self.progress_updated.emit(5, "나스닥100 지수 정보 수집 중...")
            index_info = self.get_nasdaq_info()
            self.index_info_updated.emit(index_info)

            self.progress_updated.emit(10, "나스닥100 주요 종목 데이터 수집 시작...")
            stocks = self.get_nasdaq_stocks()

            if stocks:
                self.progress_updated.emit(90, "데이터 정렬 및 처리 중...")
                top_stocks = self.get_top_stocks_by_return(stocks, self.limit)
                self.data_updated.emit(top_stocks)
                self.progress_updated.emit(100, f"완료! {len(top_stocks)}개 종목 수집됨")
            else:
                self.error_occurred.emit("나스닥100 종목 데이터를 수집할 수 없습니다.")

        except Exception as e:
            self.error_occurred.emit(f"나스닥100 크롤링 중 오류 발생: {str(e)}")

    def get_nasdaq_info(self):
        """나스닥100 지수 기본 정보를 가져옵니다."""
        try:
            response = self.session.get(self.base_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            index_info = {}
            current_value = soup.find('span', class_='num')
            if current_value:
                index_info['현재지수'] = current_value.get_text(strip=True)
            change_info = soup.find('span', class_='num_s')
            if change_info:
                index_info['전일대비'] = change_info.get_text(strip=True)
            rate_info = soup.find('span', class_='num_p')
            if rate_info:
                index_info['등락률'] = rate_info.get_text(strip=True)
            return index_info
        except Exception as e:
            return {}

    def get_nasdaq_stocks(self):
        """나스닥100 주요 종목 정보를 가져옵니다."""
        nasdaq_symbols = [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'NFLX',
            'ADBE', 'CRM', 'INTC', 'AMD', 'PYPL', 'CSCO', 'ORCL', 'AVGO',
            'QCOM', 'TXN', 'COST', 'PEP', 'CMCSA', 'AMAT', 'SBUX', 'ISRG',
            'GILD', 'BKNG', 'ADP', 'VRTX', 'REGN', 'ATVI', 'MRNA', 'ABNB',
            'SNPS', 'CHTR', 'MDLZ', 'CTAS', 'FISV', 'KLAC', 'ILMN', 'CSX',
            'INTU', 'WBA', 'AMGN', 'EXC', 'LRCX', 'NXPI', 'ADI', 'IDXX',
            'DXCM', 'DOCU', 'ROKU', 'ZM', 'SPLK', 'PTON', 'OKTA', 'CRWD',
            'NET', 'DDOG', 'SNOW', 'PLTR', 'RBLX', 'COIN', 'HOOD', 'SOFI'
        ]

        nasdaq_stocks = []
        total_stocks = len(nasdaq_symbols)

        for i, symbol in enumerate(nasdaq_symbols[:self.limit]):
            try:
                progress = 20 + (i * 70 // total_stocks)
                self.progress_updated.emit(progress, f"{symbol} 데이터 수집 중...")

                ticker = yf.Ticker(symbol)
                info = ticker.info

                end_date = datetime.now()
                start_date = end_date - timedelta(days=self.period_days)
                hist = ticker.history(start=start_date, end=end_date)

                if not hist.empty and len(hist) >= 2:
                    current_price = hist['Close'].iloc[-1]
                    start_price = hist['Close'].iloc[0]

                    price_display = f"${start_price:.2f} / ${current_price:.2f}"
                    period_return = ((current_price - start_price) / start_price) * 100 if start_price != 0 else 0
                    period_return_str = f"{period_return:+.2f}%"

                    prev_price = hist['Close'].iloc[-2] if len(hist) > 1 else start_price
                    daily_change = current_price - prev_price
                    change_str = f"${daily_change:+.2f}"

                    # 발행주식수 대비 거래량 비율 계산
                    total_volume = hist['Volume'].sum()
                    shares_outstanding = info.get('sharesOutstanding', 0)
                    volume_ratio = (total_volume / shares_outstanding) * 100 if shares_outstanding else 0
                    volume_str = f"{volume_ratio:.2f}%"

                    stock_info = {
                        '종목코드': symbol,
                        '종목명': info.get('longName', symbol),
                        '현재가': price_display,
                        '전일대비': change_str,
                        '등락률': period_return_str,
                        '거래량': volume_str,
                        '시작가': start_price,
                        '종료가': current_price,
                        '기간수익률': period_return
                    }
                    nasdaq_stocks.append(stock_info)

                time.sleep(0.2)

            except Exception as e:
                stock_info = {
                    '종목코드': symbol, '종목명': symbol,
                    '현재가': 'N/A', '전일대비': 'N/A', '등락률': 'N/A', '거래량': 'N/A'
                }
                nasdaq_stocks.append(stock_info)
                continue

        return nasdaq_stocks

    def get_top_stocks_by_return(self, all_stocks, limit):
        """등락률 기준으로 상위 종목만 가져옵니다."""
        def sort_key(stock):
            try:
                return stock.get('기간수익률', -999)
            except:
                return -999

        sorted_stocks = sorted(all_stocks, key=sort_key, reverse=True)
        return sorted_stocks[:limit]

class ChartDataThread(QThread):
    """차트 데이터 수집을 위한 스레드"""
    progress_updated = pyqtSignal(int, str)
    chart_data_updated = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, months=60):
        super().__init__()
        self.months = months

    def run(self):
        try:
            self.progress_updated.emit(10, "차트 데이터 수집을 시작합니다...")

            end_date = datetime.now()
            start_date = end_date - timedelta(days=self.months * 30)

            self.progress_updated.emit(20, "코스피200 데이터 수집 중...")
            kospi_ticker = yf.Ticker("^KS11") # KOSPI 200 Index
            kospi_data = kospi_ticker.history(start=start_date, end=end_date, interval="1mo")


            self.progress_updated.emit(60, "나스닥100 데이터 수집 중...")
            nasdaq_ticker = yf.Ticker("^NDX") # NASDAQ 100 Index
            nasdaq_data = nasdaq_ticker.history(start=start_date, end=end_date, interval="1mo")

            self.progress_updated.emit(90, "데이터 처리 중...")

            chart_data = {
                'kospi': kospi_data.reset_index()[['Date', 'Close']] if not kospi_data.empty else None,
                'nasdaq': nasdaq_data.reset_index()[['Date', 'Close']] if not nasdaq_data.empty else None,
                'start_date': start_date,
                'end_date': end_date
            }

            self.chart_data_updated.emit(chart_data)
            self.progress_updated.emit(100, "차트 데이터 수집 완료!")

        except Exception as e:
            self.error_occurred.emit(f"차트 데이터 수집 중 오류 발생: {str(e)}")


class IndividualStockChartThread(QThread):
    """개별종목 차트 데이터 수집을 위한 스레드"""
    progress_updated = pyqtSignal(int, str)
    chart_data_updated = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, kospi_stocks, nasdaq_stocks, period_days=30):
        super().__init__()
        self.kospi_stocks = kospi_stocks
        self.nasdaq_stocks = nasdaq_stocks
        self.period_days = period_days

    def run(self):
        try:
            self.progress_updated.emit(10, "개별종목 차트 데이터 수집을 시작합니다...")

            end_date = datetime.now()
            start_date = end_date - timedelta(days=self.period_days)

            chart_data = {
                'kospi': [],
                'nasdaq': [],
                'start_date': start_date,
                'end_date': end_date
            }

            if self.kospi_stocks:
                self.progress_updated.emit(20, "코스피 종목 데이터 수집 중...")
                for i, stock in enumerate(self.kospi_stocks):
                    try:
                        progress = 20 + (i * 30 // len(self.kospi_stocks))
                        self.progress_updated.emit(progress, f"코스피 {stock['name']} 데이터 수집 중...")

                        ticker = yf.Ticker(stock['symbol'])
                        hist = ticker.history(start=start_date, end=end_date)

                        if not hist.empty:
                            normalized_data = (hist['Close'] / hist['Close'].iloc[0]) * 100
                            chart_data['kospi'].append({
                                'symbol': stock['symbol'],
                                'name': stock['name'],
                                'data': normalized_data,
                                'dates': hist.index
                            })
                        time.sleep(0.1)
                    except Exception as e:
                        continue

            if self.nasdaq_stocks:
                self.progress_updated.emit(60, "나스닥 종목 데이터 수집 중...")
                for i, stock in enumerate(self.nasdaq_stocks):
                    try:
                        progress = 60 + (i * 30 // len(self.nasdaq_stocks))
                        self.progress_updated.emit(progress, f"나스닥 {stock['name']} 데이터 수집 중...")

                        ticker = yf.Ticker(stock['symbol'])
                        hist = ticker.history(start=start_date, end=end_date)

                        if not hist.empty:
                            normalized_data = (hist['Close'] / hist['Close'].iloc[0]) * 100
                            chart_data['nasdaq'].append({
                                'symbol': stock['symbol'],
                                'name': stock['name'],
                                'data': normalized_data,
                                'dates': hist.index
                            })
                        time.sleep(0.1)
                    except Exception as e:
                        continue

            self.progress_updated.emit(90, "데이터 처리 중...")
            self.chart_data_updated.emit(chart_data)
            self.progress_updated.emit(100, "개별종목 차트 데이터 수집 완료!")

        except Exception as e:
            self.error_occurred.emit(f"개별종목 차트 데이터 수집 중 오류 발생: {str(e)}")

class PortfolioDataGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.kospi_crawler_thread = None
        self.nasdaq_crawler_thread = None
        self.chart_data_thread = None
        self.individual_chart_thread = None
        self.kospi_data = []
        self.nasdaq_data = []
        self.chart_data = None
        self.individual_chart_data = None
        self.init_ui()

    def init_ui(self):
        """UI 초기화"""
        self.setWindowTitle("투자 포트폴리오 데이터")
        self.setGeometry(100, 100, 1400, 900)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)

        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        self.create_kospi_tab()
        self.create_nasdaq_tab()
        self.create_chart_tab()
        self.create_individual_chart_tab()
        self.create_log_tab()

        self.statusBar().showMessage("준비됨")

    def create_control_panel(self, parent_layout, market_type="kospi"):
        """상단 제어 패널 생성"""
        control_frame = QFrame()
        control_frame.setFrameStyle(QFrame.StyledPanel)
        control_layout = QHBoxLayout(control_frame)

        control_layout.addWidget(QLabel("수집할 종목 수:"))
        stock_count_spin = QSpinBox()
        stock_count_spin.setRange(1, 200)
        stock_count_spin.setValue(50)
        control_layout.addWidget(stock_count_spin)

        control_layout.addWidget(QLabel("수집 기간 (일):"))
        period_spin = QSpinBox()
        period_spin.setRange(1, 365)
        period_spin.setValue(30)
        control_layout.addWidget(period_spin)

        start_btn = QPushButton(f"{market_type.upper()} 크롤링 시작")
        start_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; border: none; padding: 10px 20px; font-size: 14px; font-weight: bold; border-radius: 5px; } QPushButton:hover { background-color: #45a049; } QPushButton:disabled { background-color: #cccccc; }")
        control_layout.addWidget(start_btn)

        save_excel_btn = QPushButton("Excel 저장")
        save_excel_btn.setEnabled(False)
        save_excel_btn.setStyleSheet("QPushButton { background-color: #2196F3; color: white; border: none; padding: 10px 20px; font-size: 14px; font-weight: bold; border-radius: 5px; } QPushButton:hover { background-color: #1976D2; } QPushButton:disabled { background-color: #cccccc; }")
        control_layout.addWidget(save_excel_btn)

        save_csv_btn = QPushButton("CSV 저장")
        save_csv_btn.setEnabled(False)
        save_csv_btn.setStyleSheet("QPushButton { background-color: #FF9800; color: white; border: none; padding: 10px 20px; font-size: 14px; font-weight: bold; border-radius: 5px; } QPushButton:hover { background-color: #F57C00; } QPushButton:disabled { background-color: #cccccc; }")
        control_layout.addWidget(save_csv_btn)

        progress_bar = QProgressBar()
        progress_bar.setVisible(False)
        control_layout.addWidget(progress_bar)

        control_layout.addStretch()
        parent_layout.addWidget(control_frame)

        return {
            'stock_count_spin': stock_count_spin, 'period_spin': period_spin,
            'start_btn': start_btn, 'save_excel_btn': save_excel_btn,
            'save_csv_btn': save_csv_btn, 'progress_bar': progress_bar
        }

    def create_kospi_tab(self):
        """코스피200 탭 생성"""
        kospi_widget = QWidget()
        layout = QVBoxLayout(kospi_widget)

        self.kospi_controls = self.create_control_panel(layout, "kospi")
        self.kospi_controls['start_btn'].clicked.connect(self.start_kospi_crawling)
        self.kospi_controls['save_excel_btn'].clicked.connect(lambda: self.save_to_excel("kospi"))
        self.kospi_controls['save_csv_btn'].clicked.connect(lambda: self.save_to_csv("kospi"))

        # 스플리터로 테이블과 통계 영역 분리
        splitter = QSplitter(Qt.Vertical)

        self.kospi_table = self.create_stocks_table()
        splitter.addWidget(self.kospi_table)

        self.kospi_stats_group, self.kospi_stats_canvas1, self.kospi_stats_canvas2 = self.create_statistics_group()
        splitter.addWidget(self.kospi_stats_group)

        splitter.setSizes([400, 200]) # 초기 크기 설정
        layout.addWidget(splitter)

        self.tab_widget.addTab(kospi_widget, "코스피200")


    def create_nasdaq_tab(self):
        """나스닥100 탭 생성"""
        nasdaq_widget = QWidget()
        layout = QVBoxLayout(nasdaq_widget)

        self.nasdaq_controls = self.create_control_panel(layout, "nasdaq")
        self.nasdaq_controls['start_btn'].clicked.connect(self.start_nasdaq_crawling)
        self.nasdaq_controls['save_excel_btn'].clicked.connect(lambda: self.save_to_excel("nasdaq"))
        self.nasdaq_controls['save_csv_btn'].clicked.connect(lambda: self.save_to_csv("nasdaq"))

        splitter = QSplitter(Qt.Vertical)

        self.nasdaq_table = self.create_stocks_table()
        splitter.addWidget(self.nasdaq_table)

        self.nasdaq_stats_group, self.nasdaq_stats_canvas1, self.nasdaq_stats_canvas2 = self.create_statistics_group()
        splitter.addWidget(self.nasdaq_stats_group)

        splitter.setSizes([400, 200])
        layout.addWidget(splitter)

        self.tab_widget.addTab(nasdaq_widget, "나스닥100")


    def create_chart_tab(self):
        """시계열 차트 탭 생성"""
        chart_widget = QWidget()
        layout = QVBoxLayout(chart_widget)

        chart_control_frame = QFrame()
        chart_control_frame.setFrameStyle(QFrame.StyledPanel)
        chart_control_layout = QHBoxLayout(chart_control_frame)

        self.create_chart_btn = QPushButton("차트 생성")
        self.create_chart_btn.clicked.connect(self.start_chart_data_collection)
        self.create_chart_btn.setStyleSheet("QPushButton { background-color: #9C27B0; color: white; border: none; padding: 10px 20px; font-size: 14px; font-weight: bold; border-radius: 5px; } QPushButton:hover { background-color: #7B1FA2; } QPushButton:disabled { background-color: #cccccc; }")
        chart_control_layout.addWidget(self.create_chart_btn)

        chart_control_layout.addWidget(QLabel("기간 (개월):"))
        self.chart_months_spin = QSpinBox()
        self.chart_months_spin.setRange(12, 120)
        self.chart_months_spin.setValue(60)
        chart_control_layout.addWidget(self.chart_months_spin)

        self.chart_progress_bar = QProgressBar()
        self.chart_progress_bar.setVisible(False)
        chart_control_layout.addWidget(self.chart_progress_bar)

        chart_control_layout.addStretch()
        layout.addWidget(chart_control_frame)

        self.chart_canvas = FigureCanvas(Figure(figsize=(12, 8)))
        layout.addWidget(self.chart_canvas)

        self.tab_widget.addTab(chart_widget, "지수 비교차트")

    def create_individual_chart_tab(self):
        """개별종목 차트 탭 생성"""
        individual_chart_widget = QWidget()
        layout = QVBoxLayout(individual_chart_widget)

        individual_control_frame = QFrame()
        individual_control_frame.setFrameStyle(QFrame.StyledPanel)
        individual_control_layout = QHBoxLayout(individual_control_frame)

        individual_control_layout.addWidget(QLabel("기간 (일):"))
        self.individual_period_spin = QSpinBox()
        self.individual_period_spin.setRange(1, 365)
        self.individual_period_spin.setValue(30)
        individual_control_layout.addWidget(self.individual_period_spin)

        self.kospi_top5_btn = QPushButton("코스피 상위 5개 종목 차트")
        self.kospi_top5_btn.clicked.connect(lambda: self.start_individual_chart_data_collection("kospi"))
        self.kospi_top5_btn.setStyleSheet("QPushButton { background-color: #2196F3; color: white; border: none; padding: 10px 20px; font-size: 14px; font-weight: bold; border-radius: 5px; } QPushButton:hover { background-color: #1976D2; } QPushButton:disabled { background-color: #cccccc; }")
        individual_control_layout.addWidget(self.kospi_top5_btn)

        self.nasdaq_top5_btn = QPushButton("나스닥 상위 5개 종목 차트")
        self.nasdaq_top5_btn.clicked.connect(lambda: self.start_individual_chart_data_collection("nasdaq"))
        self.nasdaq_top5_btn.setStyleSheet("QPushButton { background-color: #FF9800; color: white; border: none; padding: 10px 20px; font-size: 14px; font-weight: bold; border-radius: 5px; } QPushButton:hover { background-color: #F57C00; } QPushButton:disabled { background-color: #cccccc; }")
        individual_control_layout.addWidget(self.nasdaq_top5_btn)

        self.individual_chart_progress_bar = QProgressBar()
        self.individual_chart_progress_bar.setVisible(False)
        individual_control_layout.addWidget(self.individual_chart_progress_bar)

        individual_control_layout.addStretch()
        layout.addWidget(individual_control_frame)

        self.individual_chart_canvas = FigureCanvas(Figure(figsize=(12, 8)))
        layout.addWidget(self.individual_chart_canvas)

        self.tab_widget.addTab(individual_chart_widget, "개별종목 비교")

    def create_stocks_table(self):
        """종목 테이블 생성"""
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(['순위', '종목코드', '종목명', '현재가', '기간수익률', '거래량 (발행주식수 대비)'])

        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)

        table.setAlternatingRowColors(True)
        table.setStyleSheet("QTableWidget { gridline-color: #d0d0d0; background-color: white; alternate-background-color: #f8f8f8; color: black; } QHeaderView::section { background-color: #e0e0e0; padding: 8px; border: 1px solid #d0d0d0; font-weight: bold; color: black; } QTableWidget::item { color: black; padding: 5px; }")

        return table

    def create_statistics_group(self):
        """통계 정보 그룹 생성 (차트 포함)"""
        stats_group = QGroupBox("수집 통계")
        stats_group.setStyleSheet("QGroupBox { font-weight: bold; border: 2px solid #cccccc; border-radius: 5px; margin-top: 10px; padding-top: 10px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }")

        # 메인 레이아웃: 그리드
        main_layout = QGridLayout(stats_group)

        # 1. 텍스트 통계 영역
        text_stats_frame = QFrame()
        stats_layout = QGridLayout(text_stats_frame)
        stats_labels = {}
        stats_items = ['총 종목 수', '상승 종목', '하락 종목', '보합 종목', '최고 수익률 종목', '최저 수익률 종목']

        for i, item in enumerate(stats_items):
            label_text = QLabel(f"{item}:")
            label_text.setStyleSheet("font-weight: bold;")
            stats_layout.addWidget(label_text, i, 0)
            label = QLabel("-")
            label.setStyleSheet("font-weight: bold; color: #333;")
            stats_labels[item] = label
            stats_layout.addWidget(label, i, 1)

        main_layout.addWidget(text_stats_frame, 0, 0)

        # 2. 차트 영역
        charts_frame = QFrame()
        charts_layout = QHBoxLayout(charts_frame)

        # 상승/하락 비율 파이 차트
        figure1 = Figure(figsize=(4, 4))
        canvas1 = FigureCanvas(figure1)
        charts_layout.addWidget(canvas1)

        # 상위 5개 종목 파이 차트
        figure2 = Figure(figsize=(4, 4))
        canvas2 = FigureCanvas(figure2)
        charts_layout.addWidget(canvas2)

        main_layout.addWidget(charts_frame, 0, 1)
        main_layout.setColumnStretch(0, 1)
        main_layout.setColumnStretch(1, 2)

        stats_group.stats_labels = stats_labels
        return stats_group, canvas1, canvas2


    def create_log_tab(self):
        """로그 탭 생성"""
        log_widget = QWidget()
        layout = QVBoxLayout(log_widget)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("QTextEdit { background-color: #f5f5f5; border: 1px solid #d0d0d0; font-family: 'Courier New', monospace; font-size: 12px; color: black; }")
        layout.addWidget(self.log_text)

        log_btn_layout = QHBoxLayout()
        clear_log_btn = QPushButton("로그 지우기")
        clear_log_btn.setStyleSheet("QPushButton { background-color: #6c757d; color: white; border: none; padding: 8px 16px; font-size: 12px; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #5a6268; }")
        clear_log_btn.clicked.connect(self.clear_log)
        log_btn_layout.addWidget(clear_log_btn)
        log_btn_layout.addStretch()
        layout.addLayout(log_btn_layout)

        self.tab_widget.addTab(log_widget, "실행로그")

    def start_kospi_crawling(self):
        """코스피200 크롤링 시작"""
        if self.kospi_crawler_thread and self.kospi_crawler_thread.isRunning(): return
        self.kospi_controls['start_btn'].setEnabled(False)
        self.kospi_controls['start_btn'].setText("수집 중...")
        self.kospi_controls['progress_bar'].setVisible(True)
        self.kospi_controls['progress_bar'].setValue(0)
        self.log_message("코스피200 크롤링을 시작합니다...")
        limit = self.kospi_controls['stock_count_spin'].value()
        period_days = self.kospi_controls['period_spin'].value()
        self.kospi_crawler_thread = Kospi200CrawlerThread(limit, period_days)
        self.kospi_crawler_thread.progress_updated.connect(lambda v, m: self.update_progress(v, m, "kospi"))
        self.kospi_crawler_thread.data_updated.connect(lambda d: self.update_stock_data(d, "kospi"))
        self.kospi_crawler_thread.error_occurred.connect(lambda e: self.handle_error(e, "kospi"))
        self.kospi_crawler_thread.finished.connect(lambda: self.crawling_finished("kospi"))
        self.kospi_crawler_thread.start()

    def start_nasdaq_crawling(self):
        """나스닥100 크롤링 시작"""
        if self.nasdaq_crawler_thread and self.nasdaq_crawler_thread.isRunning(): return
        self.nasdaq_controls['start_btn'].setEnabled(False)
        self.nasdaq_controls['start_btn'].setText("수집 중...")
        self.nasdaq_controls['progress_bar'].setVisible(True)
        self.nasdaq_controls['progress_bar'].setValue(0)
        self.log_message("나스닥100 크롤링을 시작합니다...")
        limit = self.nasdaq_controls['stock_count_spin'].value()
        period_days = self.nasdaq_controls['period_spin'].value()
        self.nasdaq_crawler_thread = Nasdaq100CrawlerThread(limit, period_days)
        self.nasdaq_crawler_thread.progress_updated.connect(lambda v, m: self.update_progress(v, m, "nasdaq"))
        self.nasdaq_crawler_thread.data_updated.connect(lambda d: self.update_stock_data(d, "nasdaq"))
        self.nasdaq_crawler_thread.error_occurred.connect(lambda e: self.handle_error(e, "nasdaq"))
        self.nasdaq_crawler_thread.finished.connect(lambda: self.crawling_finished("nasdaq"))
        self.nasdaq_crawler_thread.start()

    def start_chart_data_collection(self):
        """차트 데이터 수집 시작"""
        if self.chart_data_thread and self.chart_data_thread.isRunning(): return
        self.create_chart_btn.setEnabled(False)
        self.create_chart_btn.setText("데이터 수집 중...")
        self.chart_progress_bar.setVisible(True)
        self.chart_progress_bar.setValue(0)
        self.log_message("차트 데이터 수집을 시작합니다...")
        months = self.chart_months_spin.value()
        self.chart_data_thread = ChartDataThread(months)
        self.chart_data_thread.progress_updated.connect(self.update_chart_progress)
        self.chart_data_thread.chart_data_updated.connect(self.update_chart)
        self.chart_data_thread.error_occurred.connect(self.handle_chart_error)
        self.chart_data_thread.finished.connect(self.chart_data_finished)
        self.chart_data_thread.start()

    def update_chart_progress(self, value, message):
        """차트 진행률 업데이트"""
        self.chart_progress_bar.setValue(value)
        self.log_message(f"[차트] {message}")
        self.statusBar().showMessage(message)

    def update_chart(self, chart_data):
        """차트 업데이트"""
        self.chart_data = chart_data
        self.draw_chart(chart_data)
        self.log_message("[차트] 차트 생성 완료")

    def draw_chart(self, chart_data):
        """차트 그리기 (수익률 비교를 위해 정규화)"""
        fig = self.chart_canvas.figure
        fig.clear()
        ax = fig.add_subplot(111)

        kospi_data = chart_data['kospi']
        nasdaq_data = chart_data['nasdaq']

        # 코스피200 데이터 정규화 및 플로팅
        if kospi_data is not None and not kospi_data.empty:
            # 시작일의 종가를 기준으로 모든 데이터를 100으로 정규화
            base_kospi = kospi_data['Close'].iloc[0]
            normalized_kospi = (kospi_data['Close'] / base_kospi) * 100
            ax.plot(kospi_data['Date'], normalized_kospi, label='코스피200', linewidth=2, color='blue')

        # 나스닥100 데이터 정규화 및 플로팅
        if nasdaq_data is not None and not nasdaq_data.empty:
            # 시작일의 종가를 기준으로 모든 데이터를 100으로 정규화
            base_nasdaq = nasdaq_data['Close'].iloc[0]
            normalized_nasdaq = (nasdaq_data['Close'] / base_nasdaq) * 100
            ax.plot(nasdaq_data['Date'], normalized_nasdaq, label='나스닥100', linewidth=2, color='red')

        # 차트 타이틀 및 레이블 변경
        if (kospi_data is not None and not kospi_data.empty) or \
           (nasdaq_data is not None and not nasdaq_data.empty):
            ax.set_title('코스피200 vs 나스닥100 성과 비교', fontsize=16, fontweight='bold')
            ax.set_xlabel('날짜', fontsize=12)
            ax.set_ylabel('정규화된 지수 (시작일 = 100)', fontsize=12) # Y축 레이블 변경
            ax.legend(fontsize=12)
            ax.grid(True, linestyle='--', alpha=0.5)
            # Y축에 100 기준선 추가
            ax.axhline(y=100, color='gray', linestyle=':', linewidth=1)
            ax.tick_params(axis='x', rotation=30)
            fig.tight_layout()
        else:
            ax.text(0.5, 0.5, '데이터를 불러올 수 없습니다.', ha='center', va='center', transform=ax.transAxes, fontsize=14)

        self.chart_canvas.draw()

    def handle_chart_error(self, error_message):
        """차트 오류 처리"""
        self.log_message(f"[차트] 오류: {error_message}")
        QMessageBox.warning(self, "차트 오류", error_message)
        self.chart_data_finished()

    def chart_data_finished(self):
        """차트 데이터 수집 완료"""
        self.create_chart_btn.setEnabled(True)
        self.create_chart_btn.setText("차트 생성")
        self.chart_progress_bar.setVisible(False)
        self.statusBar().showMessage("차트 데이터 수집 완료")
        self.log_message("[차트] 차트 데이터 수집이 완료되었습니다.")

    def start_individual_chart_data_collection(self, market_type):
        """개별종목 차트 데이터 수집 시작"""
        if self.individual_chart_thread and self.individual_chart_thread.isRunning(): return

        if market_type == "kospi":
            self.kospi_top5_btn.setEnabled(False)
            self.kospi_top5_btn.setText("수집 중...")
            if not self.kospi_data:
                QMessageBox.warning(self, "경고", "먼저 코스피200 데이터를 수집해주세요.")
                self.kospi_top5_btn.setEnabled(True)
                self.kospi_top5_btn.setText("코스피 상위 5개 종목 차트")
                return
            top_stocks = sorted(self.kospi_data, key=lambda x: x.get('기간수익률', 0), reverse=True)[:5]
            kospi_stocks = [{'symbol': f"{s['종목코드']}.KS", 'name': s['종목명']} for s in top_stocks]
            nasdaq_stocks = []
        else:
            self.nasdaq_top5_btn.setEnabled(False)
            self.nasdaq_top5_btn.setText("수집 중...")
            if not self.nasdaq_data:
                QMessageBox.warning(self, "경고", "먼저 나스닥100 데이터를 수집해주세요.")
                self.nasdaq_top5_btn.setEnabled(True)
                self.nasdaq_top5_btn.setText("나스닥 상위 5개 종목 차트")
                return
            top_stocks = sorted(self.nasdaq_data, key=lambda x: x.get('기간수익률', 0), reverse=True)[:5]
            kospi_stocks = []
            nasdaq_stocks = [{'symbol': s['종목코드'], 'name': s['종목명']} for s in top_stocks]

        self.individual_chart_progress_bar.setVisible(True)
        self.individual_chart_progress_bar.setValue(0)
        self.log_message(f"{market_type.upper()} 상위 5개 종목 차트 데이터 수집을 시작합니다...")
        period_days = self.individual_period_spin.value()

        self.individual_chart_thread = IndividualStockChartThread(kospi_stocks, nasdaq_stocks, period_days)
        self.individual_chart_thread.progress_updated.connect(self.update_individual_chart_progress)
        self.individual_chart_thread.chart_data_updated.connect(self.update_individual_chart)
        self.individual_chart_thread.error_occurred.connect(self.handle_individual_chart_error)
        self.individual_chart_thread.finished.connect(lambda: self.individual_chart_data_finished(market_type))
        self.individual_chart_thread.start()

    def update_individual_chart_progress(self, value, message):
        """개별종목 차트 진행률 업데이트"""
        self.individual_chart_progress_bar.setValue(value)
        self.log_message(f"[개별종목] {message}")
        self.statusBar().showMessage(message)

    def update_individual_chart(self, chart_data):
        """개별종목 차트 업데이트"""
        self.individual_chart_data = chart_data
        self.draw_individual_chart(chart_data)
        self.log_message("[개별종목] 차트 생성 완료")

    def draw_individual_chart(self, chart_data):
        """개별종목 차트 그리기"""
        fig = self.individual_chart_canvas.figure
        fig.clear()
        ax = fig.add_subplot(111)

        colors = plt.get_cmap('tab10').colors
        color_idx = 0

        all_stocks_data = chart_data['kospi'] + chart_data['nasdaq']

        for stock_data in all_stocks_data:
            currency = "(원화)" if '.KS' in stock_data['symbol'] else "(달러)"
            ax.plot(stock_data['dates'], stock_data['data'],
                   label=f"{stock_data['name']} {currency}",
                   linewidth=2, color=colors[color_idx % len(colors)])
            color_idx += 1

        ax.set_title('개별종목 성과 비교 (정규화)', fontsize=16, fontweight='bold')
        ax.set_xlabel('날짜', fontsize=12)
        ax.set_ylabel('정규화된 가격 (기준: 100)', fontsize=12)
        ax.legend(fontsize=10)
        ax.grid(True, alpha=0.3)
        ax.tick_params(axis='x', rotation=45)
        fig.tight_layout()
        self.individual_chart_canvas.draw()


    def handle_individual_chart_error(self, error_message):
        """개별종목 차트 오류 처리"""
        self.log_message(f"[개별종목] 오류: {error_message}")
        QMessageBox.warning(self, "개별종목 차트 오류", error_message)
        self.kospi_top5_btn.setEnabled(True)
        self.kospi_top5_btn.setText("코스피 상위 5개 종목 차트")
        self.nasdaq_top5_btn.setEnabled(True)
        self.nasdaq_top5_btn.setText("나스닥 상위 5개 종목 차트")
        self.individual_chart_progress_bar.setVisible(False)

    def individual_chart_data_finished(self, market_type):
        """개별종목 차트 데이터 수집 완료"""
        if market_type == "kospi":
            self.kospi_top5_btn.setEnabled(True)
            self.kospi_top5_btn.setText("코스피 상위 5개 종목 차트")
        else:
            self.nasdaq_top5_btn.setEnabled(True)
            self.nasdaq_top5_btn.setText("나스닥 상위 5개 종목 차트")
        self.individual_chart_progress_bar.setVisible(False)
        self.statusBar().showMessage("개별종목 차트 데이터 수집 완료")
        self.log_message(f"[{market_type.upper()}] 차트 데이터 수집이 완료되었습니다.")

    def update_progress(self, value, message, market_type):
        """진행률 업데이트"""
        controls = self.kospi_controls if market_type == "kospi" else self.nasdaq_controls
        controls['progress_bar'].setValue(value)
        self.log_message(f"[{market_type.upper()}] {message}")
        self.statusBar().showMessage(message)

    def update_stock_data(self, stock_data, market_type):
        """종목 데이터 업데이트"""
        if market_type == "kospi":
            self.kospi_data = stock_data
            table, stats_group, canvas1, canvas2, controls = \
                self.kospi_table, self.kospi_stats_group, self.kospi_stats_canvas1, self.kospi_stats_canvas2, self.kospi_controls
        else:
            self.nasdaq_data = stock_data
            table, stats_group, canvas1, canvas2, controls = \
                self.nasdaq_table, self.nasdaq_stats_group, self.nasdaq_stats_canvas1, self.nasdaq_stats_canvas2, self.nasdaq_controls

        table.setRowCount(len(stock_data))
        for i, stock in enumerate(stock_data):
            table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            table.setItem(i, 1, QTableWidgetItem(stock['종목코드']))
            table.setItem(i, 2, QTableWidgetItem(stock['종목명']))
            table.setItem(i, 3, QTableWidgetItem(stock.get('현재가', 'N/A')))
            table.setItem(i, 4, QTableWidgetItem(stock.get('등락률', 'N/A')))
            table.setItem(i, 5, QTableWidgetItem(stock.get('거래량', 'N/A')))

        self.update_statistics(stock_data, stats_group, canvas1, canvas2)
        controls['save_excel_btn'].setEnabled(True)
        controls['save_csv_btn'].setEnabled(True)
        self.log_message(f"[{market_type.upper()}] {len(stock_data)}개 종목 데이터 수집 완료")

    def update_statistics(self, stock_data, stats_group, canvas1, canvas2):
        """통계 정보 및 차트 업데이트"""
        if not stock_data: return

        # 1. 텍스트 통계 업데이트
        total = len(stock_data)
        up_count = sum(1 for s in stock_data if s.get('기간수익률', 0) > 0)
        down_count = sum(1 for s in stock_data if s.get('기간수익률', 0) < 0)
        unchanged_count = total - up_count - down_count

        stats_labels = stats_group.stats_labels
        stats_labels['총 종목 수'].setText(str(total))
        stats_labels['상승 종목'].setText(f"{up_count}개")
        stats_labels['하락 종목'].setText(f"{down_count}개")
        stats_labels['보합 종목'].setText(f"{unchanged_count}개")

        valid_returns = sorted([s for s in stock_data if isinstance(s.get('기간수익률'), (int, float))],
                               key=lambda x: x['기간수익률'])
        if valid_returns:
            highest = valid_returns[-1]
            lowest = valid_returns[0]
            stats_labels['최고 수익률 종목'].setText(f"{highest['종목명']} ({highest['등락률']})")
            stats_labels['최저 수익률 종목'].setText(f"{lowest['종목명']} ({lowest['등락률']})")

        # 2. 상승/하락 비율 파이 차트
        fig1 = canvas1.figure
        fig1.clear()
        ax1 = fig1.add_subplot(111)
        if total > 0:
            sizes = [up_count, down_count, unchanged_count]
            labels = [f'상승 ({up_count})', f'하락 ({down_count})', f'보합 ({unchanged_count})']
            colors = ['#ff9999', '#66b3ff', '#99ff99']
            ax1.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90, textprops={'fontsize': 9})
            ax1.set_title('상승/하락 종목 비율', fontsize=12)
        canvas1.draw()

        # 3. 상위 5개 종목 수익률 파이 차트
        fig2 = canvas2.figure
        fig2.clear()
        ax2 = fig2.add_subplot(111)
        top5 = valid_returns[-5:]
        if top5:
            # 양수 수익률만 필터링
            positive_top5 = [s for s in top5 if s['기간수익률'] > 0]
            if positive_top5:
                returns = [s['기간수익률'] for s in positive_top5]
                names = [s['종목명'] for s in positive_top5]
                ax2.pie(returns, labels=names, autopct='%1.1f%%', startangle=90, textprops={'fontsize': 8})
                ax2.set_title('최고 수익률 5종목 비중', fontsize=12)
            else:
                 ax2.text(0.5, 0.5, '상위 5종목의\n양수 수익률 없음', ha='center', va='center', fontsize=10)
        canvas2.draw()


    def handle_error(self, error_message, market_type):
        """오류 처리"""
        self.log_message(f"[{market_type.upper()}] 오류: {error_message}")
        QMessageBox.warning(self, "오류", error_message)
        self.crawling_finished(market_type)

    def crawling_finished(self, market_type):
        """크롤링 완료"""
        controls = self.kospi_controls if market_type == "kospi" else self.nasdaq_controls
        controls['start_btn'].setEnabled(True)
        controls['start_btn'].setText(f"{market_type.upper()} 크롤링 시작")
        controls['progress_bar'].setVisible(False)
        self.statusBar().showMessage("완료")
        self.log_message(f"[{market_type.upper()}] 크롤링이 완료되었습니다.")

    def save_to_file(self, market_type, file_format):
        """파일 저장 로직 통합"""
        stock_data = self.kospi_data if market_type == "kospi" else self.nasdaq_data
        market_name = f"{market_type}200" if market_type == "kospi" else f"{market_type}100"

        if not stock_data:
            QMessageBox.warning(self, "경고", f"저장할 {market_name.upper()} 데이터가 없습니다.")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_ext = 'xlsx' if file_format == 'excel' else 'csv'
        filter_str = "Excel Files (*.xlsx)" if file_format == 'excel' else "CSV Files (*.csv)"
        default_filename = f"{market_name}_stocks_{timestamp}.{file_ext}"

        filename, _ = QFileDialog.getSaveFileName(self, f"{market_name.upper()} {file_ext.upper()} 파일 저장", default_filename, filter_str)

        if filename:
            try:
                df = pd.DataFrame(stock_data)
                if file_format == 'excel':
                    df.to_excel(filename, index=False, engine='openpyxl')
                else:
                    df.to_csv(filename, index=False, encoding='utf-8-sig')
                self.log_message(f"[{market_name.upper()}] {file_ext.upper()} 파일 저장 완료: {filename}")
                QMessageBox.information(self, "성공", f"{market_name.upper()} {file_ext.upper()} 파일이 저장되었습니다:\n{filename}")
            except Exception as e:
                self.log_message(f"[{market_name.upper()}] {file_ext.upper()} 저장 오류: {str(e)}")
                QMessageBox.critical(self, "오류", f"{file_ext.upper()} 파일 저장 중 오류가 발생했습니다:\n{str(e)}")

    def save_to_excel(self, market_type):
        self.save_to_file(market_type, 'excel')

    def save_to_csv(self, market_type):
        self.save_to_file(market_type, 'csv')

    def log_message(self, message):
        """로그 메시지 추가"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def clear_log(self):
        """로그 지우기"""
        self.log_text.clear()

    def closeEvent(self, event):
        """창 닫기 이벤트"""
        threads = [
            ("코스피200", self.kospi_crawler_thread),
            ("나스닥100", self.nasdaq_crawler_thread),
            ("차트 데이터", self.chart_data_thread),
            ("개별종목 차트", self.individual_chart_thread)
        ]
        running_threads = [name for name, thread in threads if thread and thread.isRunning()]

        if running_threads:
            reply = QMessageBox.question(self, "종료 확인",
                f"다음 작업이 진행 중입니다: {', '.join(running_threads)}\n정말 종료하시겠습니까?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                for _, thread in threads:
                    if thread and thread.isRunning():
                        thread.terminate()
                        thread.wait()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

def main():
    """메인 함수"""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = PortfolioDataGUI()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()