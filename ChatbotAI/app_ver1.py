import streamlit as st
import tempfile
import os
import shutil
import re
import pymupdf4llm 
import time

# [새로 추가된 Import] ChromaDB 오류 처리를 위해 필요합니다.
import chromadb 
from chromadb.errors import InternalError as ChromaInternalError

# [설정] 환경 변수
os.environ["NO_PROXY"] = "localhost,127.0.0.1"
os.environ["OLLAMA_HOST"] = "http://127.0.0.1:11434"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.chat_models import ChatOllama
from langchain_chroma import Chroma
from langchain.chains import RetrievalQA

# 👇 [필수 수정] 임포트 경로 분리 및 PromptTemplate 추가
from langchain.prompts import PromptTemplate
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage

from langchain.docstore.document import Document
from langchain.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever
from langchain.text_splitter import MarkdownHeaderTextSplitter

PERSIST_DIRECTORY = "./chroma_db"

st.set_page_config(page_title="🛡️ 사내 규정 마스터 AI", layout="wide")
st.title("🛡️ 사내 규정 마스터 AI (한국어 강제 & 표 인식 강화)")

# --------------------------------------------------------------------------------
# 1. 문서 전처리 로직 (데이터 클리닝 추가)
# --------------------------------------------------------------------------------
def clean_markdown_text(text):
    """
    LLM이 오해할 수 있는 마크다운 노이즈를 제거합니다. (취소선 제거 포함)
    """
    text = text.replace("~~", "") 
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text

def process_pdf_to_structured_docs(file_path, source_name):
    md_text = pymupdf4llm.to_markdown(file_path)
    md_text = clean_markdown_text(md_text)
    
    # 구조화 (제N조, 별표 등을 헤더로 변환)
    md_text = re.sub(r'(^|\n)(제\s*\d+(?:의\d+)?\s*조)', r'\1# \2', md_text)
    md_text = re.sub(r'(^|\n)(\[별표\s*\d+.*?\])', r'\1# \2', md_text)
    md_text = re.sub(r'(^|\n)(\[별지\s*.*?\])', r'\1# \2', md_text)

    # 분할
    headers_to_split_on = [("#", "Article_Title")]
    markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
    md_header_splits = markdown_splitter.split_text(md_text)
    
    final_docs = []
    for doc in md_header_splits:
        doc.metadata["source"] = source_name
        final_docs.append(doc)
        
    return final_docs

# --------------------------------------------------------------------------------
# 2. 사이드바 (모델 및 DB 초기화 로직)
# --------------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ 시스템 설정")
    # [수정] 커스텀 모델 목록
    CUSTOM_MODELS = ["korean-llama3", "korean-gemma2"] 
    selected_model = st.selectbox("AI 모델 선택", CUSTOM_MODELS, index=0)

    st.markdown("---")
    st.header("📂 규정 업로드")
    uploaded_files = st.file_uploader("PDF 규정 파일", type=["pdf"], accept_multiple_files=True)
    process_button = st.button("🚀 규정 학습 시작")

    st.markdown("---")
    # DB 초기화 버튼
    if st.button("🗑️ 지식베이스 초기화 (오류 시 클릭)"):
        st.session_state.clear() 
        try:
            if os.path.exists(PERSIST_DIRECTORY):
                shutil.rmtree(PERSIST_DIRECTORY)
                st.success("✅ DB 삭제 완료! F5를 눌러 새로고침하세요.")
            else:
                st.info("삭제할 DB가 없습니다.")
        except Exception as e:
            st.error(f"⚠️ 파일이 사용 중입니다. 터미널을 껐다 켜거나, 잠시 후 다시 시도하세요.\n에러: {e}")

# --------------------------------------------------------------------------------
# 3. 임베딩 및 DB 처리
# --------------------------------------------------------------------------------
@st.cache_resource
def get_embeddings():
    return HuggingFaceEmbeddings(
        model_name="jhgan/ko-sroberta-multitask",
        model_kwargs={'device': 'cpu'},
        encode_kwargs={'normalize_embeddings': True}
    )

if uploaded_files and process_button:
    with st.spinner("규정의 표와 조항을 구조화하여 학습 중입니다..."):
        all_docs = []
        for file in uploaded_files:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(file.getvalue())
                tmp_path = tmp.name
            
            try:
                docs = process_pdf_to_structured_docs(tmp_path, file.name)
                all_docs.extend(docs)
            finally:
                os.remove(tmp_path)
        
        if all_docs:
            vectorstore = Chroma(
                persist_directory=PERSIST_DIRECTORY,
                embedding_function=get_embeddings()
            )
            vectorstore.add_documents(all_docs)
            st.success(f"✅ 총 {len(all_docs)}개의 조항/별표가 완벽하게 학습되었습니다!")
            time.sleep(1)
            st.rerun()

# --------------------------------------------------------------------------------
# 4. 검색 및 답변 로직 (Indentation/Logic Fix)
# --------------------------------------------------------------------------------
embeddings = get_embeddings()
vectorstore = None
ensemble_retriever = None

# [핵심 수정 부분] IndentationError 및 로드 로직 수정
if os.path.exists(PERSIST_DIRECTORY):
    try:
        # DB 로드 시도
        vectorstore = Chroma(persist_directory=PERSIST_DIRECTORY, embedding_function=embeddings)
        
        # 1. Vector Search (정상 로드 시에만 Retriever 생성)
        chroma_retriever = vectorstore.as_retriever(search_kwargs={"k": 5})
        
        # 2. BM25 Search (앙상블 Retriever 구성)
        doc_data = vectorstore.get()
        if doc_data['documents']:
            bm25_docs = [Document(page_content=t, metadata=m) for t, m in zip(doc_data['documents'], doc_data['metadatas'])]
            bm25_retriever = BM25Retriever.from_documents(bm25_docs)
            bm25_retriever.k = 5
            
            ensemble_retriever = EnsembleRetriever(
                retrievers=[bm25_retriever, chroma_retriever],
                weights=[0.8, 0.2]
            )
        else:
            ensemble_retriever = chroma_retriever
            
    # DB 잠금 오류 발생 시 처리
    except ChromaInternalError:
        st.error("⚠️ 데이터베이스 잠금 오류: DB 파일이 사용 중입니다. 서버를 완전히 종료(Ctrl+C) 후, './chroma_db' 폴더를 삭제하고 재시작하세요.")
        ensemble_retriever = None
    except Exception as e:
        st.error(f"DB 로드 중 예상치 못한 오류 발생: {e}")
        ensemble_retriever = None
# DB가 없으면 ensemble_retriever는 초기값 None을 유지함

# 채팅 UI
if "messages" not in st.session_state:
    st.session_state.messages = []

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.write(m["content"])

if prompt := st.chat_input("질문하세요 (예: 승진후보자 범위 알려줘)"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        if ensemble_retriever:
            llm = ChatOllama(
                model=selected_model, 
                base_url="http://127.0.0.1:11434",
            )
            
            # [수정] 안정적인 PromptTemplate 사용 (System Prompt 포함)
            template = """
            [System Instruction]
            너는 대한민국 공공기관의 사내 규정을 안내하는 AI 챗봇이다.
            주어진 [문맥(Context)]을 바탕으로 사용자의 질문에 답변하라.

            [절대 준수 원칙]
            1. **무조건 한국어(Korean)로만 답변해라.** 영어를 절대 쓰지 마라.
            2. [문맥]에 표(Table) 내용이 있다면, 마크다운 표 형식으로 그대로 출력해라.
            3. "규정 제OO조에 따르면..." 처럼 근거를 반드시 명시해라.
            4. 문맥에 없는 내용은 "규정에 내용이 없습니다."라고 답해라.

            [문맥(Context)]:
            {context}

            [질문(Question)]:
            {question}

            답변(Answer):
            """

            QA_CHAIN_PROMPT = PromptTemplate(
                input_variables=["context", "question"],
                template=template
            )

            # 체인 실행
            qa_chain = RetrievalQA.from_chain_type(
                llm=llm,
                retriever=ensemble_retriever,
                chain_type="stuff",
                chain_type_kwargs={"prompt": QA_CHAIN_PROMPT}
            )
            
            try:
                with st.spinner("규정 분석 중..."):
                    response = qa_chain.run(prompt)
                
                st.write(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
                
                with st.expander("참고한 규정 원문"):
                    docs = ensemble_retriever.invoke(prompt)
                    for i, doc in enumerate(docs[:3]):
                         title = doc.metadata.get("Article_Title", "조항/별표")
                         st.markdown(f"**[근거 {i+1}: {title}]**")
                         st.text(doc.page_content[:300] + "...")

            except Exception as e:
                st.error(f"오류: {e}")
        else:
            st.warning("먼저 규정 파일을 업로드하고 학습시켜주세요.")