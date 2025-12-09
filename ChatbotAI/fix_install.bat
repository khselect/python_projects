@echo off
echo ========================================================
echo [1/4] 가상환경의 파이썬 위치를 확인합니다...
echo ========================================================
set PYTHON_EXE=..\.venv\Scripts\python.exe

if exist "%PYTHON_EXE%" (
    echo 가상환경 파이썬 확인됨: %PYTHON_EXE%
) else (
    echo [오류] 가상환경을 찾을 수 없습니다! 
    echo .venv 폴더가 상위 폴더(..)에 있는지 확인해주세요.
    echo 현재 위치: %CD%
    pause
    exit /b
)

echo.
echo ========================================================
echo [2/4] 꼬여있는 LangChain 관련 라이브러리를 모두 삭제합니다...
echo ========================================================
"%PYTHON_EXE%" -m pip uninstall -y langchain langchain-community langchain-core langchain-text-splitters langchain-huggingface langchain-chroma langchain-classic chromadb

echo.
echo ========================================================
echo [3/4] 필수 라이브러리를 깨끗하게 다시 설치합니다...
echo ========================================================
"%PYTHON_EXE%" -m pip install langchain langchain-community langchain-core langchain-huggingface langchain-chroma chromadb streamlit pymupdf4llm mammoth markdownify olefile

echo.
echo ========================================================
echo [4/4] 설치된 langchain 버전을 확인합니다.
echo ========================================================
"%PYTHON_EXE%" -m pip show langchain

echo.
echo ========================================================
echo [완료] 모든 작업이 끝났습니다. 창을 닫고 다시 실행해보세요!
echo ========================================================
pause