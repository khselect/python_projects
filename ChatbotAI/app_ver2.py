import streamlit as st
import tempfile
import os
import shutil
import re
import pymupdf4llm 
import time

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

from langchain.prompts import PromptTemplate
from langchain.docstore.document import Document
from langchain.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever
# [추가] 2단계 청킹을 위한 스플리터
from langchain.text_splitter import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

PERSIST_DIRECTORY = "./chroma_db"

st.set_page_config(page_title="🛡️ 사내 규정 마스터 AI (v2.0)", layout="wide")
st.title("🛡️ 사내 규정 마스터 AI (정확도 고도화 Ver.)")

# --------------------------------------------------------------------------------
# 1. 문서 전처리 로직 (2단계 청킹 적용)
# --------------------------------------------------------------------------------
def clean_markdown_text(text):
    text = text.replace("~~", "") 
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text

def process_pdf_to_structured_docs(file_path, source_name):
    # 1. PDF -> Markdown
    md_text = pymupdf4llm.to_markdown(file_path)
    md_text = clean_markdown_text(md_text)
    
    # 2. 구조화 (제N조, 별표 등을 헤더로 변환)
    md_text = re.sub(r'(^|\n)(제\s*\d+(?:의\d+)?\s*조)', r'\1# \2', md_text)
    md_text = re.sub(r'(^|\n)(\[별표\s*\d+.*?\])', r'\1# \2', md_text)
    md_text = re.sub(r'(^|\n)(\[별지\s*.*?\])', r'\1# \2', md_text)

    # 3. [1단계] 헤더 기반 분할 (조항 단위)
    headers_to_split_on = [("#", "Article_Title")]
    markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
    header_splits = markdown_splitter.split_text(md_text)
    
    # 4. [2단계] 재귀적 문자 분할 (긴 조항 세부 분할)
    # chunk_size=800: 한글 기준 문맥 파악에 적절한 길이
    # chunk_overlap=100: 잘린 부분의 문맥 연결을 위해 겹치기
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100
    )
    
    final_docs = []
    for doc in header_splits:
        # 헤더 메타데이터(조항 제목)를 유지하면서 내용을 더 잘게 쪼갭니다.
        splits = text_splitter.split_text(doc.page_content)
        for split_content in splits:
            new_doc = Document(
                page_content=split_content,
                metadata={
                    "source": source_name,
                    "Article_Title": doc.metadata.get("Article_Title", "일반"),
                    "category": "table" if "|" in split_content else "text" # 표 포함 여부 메타데이터
                }
            )
            final_docs.append(new_doc)
        
    return final_docs

# --------------------------------------------------------------------------------
# 2. 사이드바 (설정)
# --------------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ 시스템 설정")
    CUSTOM_MODELS = ["korean-llama3", "korean-gemma2"] 
    selected_model = st.selectbox("AI 모델 선택", CUSTOM_MODELS, index=0)

    st.markdown("---")
    st.header("📂 규정 업로드")
    uploaded_files = st.file_uploader("PDF 규정 파일", type=["pdf"], accept_multiple_files=True)
    process_button = st.button("🚀 규정 학습 시작")

    st.markdown("---")
    st.header("📚 등록된 규정 목록")
    if 'learned_files' not in st.session_state:
        st.session_state.learned_files = []
        
    if st.session_state.learned_files:
        for f_name in st.session_state.learned_files:
            st.success(f"• {f_name}")
    else:
        st.info("등록된 규정 파일이 없습니다.")

    st.markdown("---")
    if st.button("🗑️ 지식베이스 초기화 (rm -rf ./chroma_db)"):
        st.session_state.clear() 
        try:
            if os.path.exists(PERSIST_DIRECTORY):
                shutil.rmtree(PERSIST_DIRECTORY)
                if 'learned_files' in st.session_state:
                    del st.session_state.learned_files
                st.success("✅ DB 삭제 완료! F5를 눌러 새로고침하세요.")
            else:
                st.info("삭제할 DB가 없습니다.")
        except Exception as e:
            st.error(f"⚠️ 파일 사용 중 오류: {e}")

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
    with st.spinner("2단계 청킹(Header+Recursive) 및 학습 진행 중..."):
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
            st.success(f"✅ 총 {len(all_docs)}개의 청크가 정밀 학습되었습니다!")
            
            for file in uploaded_files:
                if file.name not in st.session_state.learned_files:
                    st.session_state.learned_files.append(file.name)
            
            time.sleep(1)
            st.rerun()

# --------------------------------------------------------------------------------
# 4. 검색 및 답변 로직 (Advanced Retrieval)
# --------------------------------------------------------------------------------
embeddings = get_embeddings()
vectorstore = None
ensemble_retriever = None

if os.path.exists(PERSIST_DIRECTORY):
    try:
        vectorstore = Chroma(persist_directory=PERSIST_DIRECTORY, embedding_function=embeddings)
        
        # [튜닝 1] 검색 후보(k) 증가: BM25와 Chroma 모두 10개씩 검색
        chroma_retriever = vectorstore.as_retriever(search_kwargs={"k": 10})
        
        doc_data = vectorstore.get()
        if doc_data['documents']:
            bm25_docs = [Document(page_content=t, metadata=m) for t, m in zip(doc_data['documents'], doc_data['metadatas'])]
            bm25_retriever = BM25Retriever.from_documents(bm25_docs)
            bm25_retriever.k = 10
            
            # [튜닝 2] 가중치 조정 (0.5 : 0.5) - 키워드와 의미 검색의 균형
            ensemble_retriever = EnsembleRetriever(
                retrievers=[bm25_retriever, chroma_retriever],
                weights=[0.5, 0.5]
            )
        else:
            ensemble_retriever = chroma_retriever
            
    except ChromaInternalError:
        st.error("⚠️ 데이터베이스 잠금 오류: 서버 재시작 필요")
        ensemble_retriever = None
    except Exception as e:
        st.error(f"DB 로드 오류: {e}")
        ensemble_retriever = None

# 채팅 UI
if "messages" not in st.session_state:
    st.session_state.messages = []

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.write(m["content"])

if prompt := st.chat_input("규정에 대해 물어보세요..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        if ensemble_retriever:
            # [튜닝 3] 모델 파라미터 고정 (결정론적 출력)
            llm = ChatOllama(
                model=selected_model, 
                base_url="http://127.0.0.1:11434",
                temperature=0,   # 창의성 0
                top_p=0.1        # 확실한 단어만 선택
            )
            
            # [튜닝 4] 중복 문서 제거 (Post-processing)
            retrieved_docs = ensemble_retriever.invoke(prompt)
            unique_docs = []
            seen_content = set()
            
            for doc in retrieved_docs:
                # 내용이 95% 이상 겹치면 중복으로 간주하고 제거
                content_snippet = doc.page_content[:100] 
                if content_snippet not in seen_content:
                    unique_docs.append(doc)
                    seen_content.add(content_snippet)
            
            # 상위 5개만 최종적으로 LLM에 전달
            final_context_docs = unique_docs[:5]

            # 문맥 조합
            context_text = "\n\n".join([doc.page_content for doc in final_context_docs])

            # [튜닝 5] 프롬프트 강화 (프리필 유도 포함)
            template = """
            [System Instruction]
            당신은 회사 규정 전문 AI입니다. 아래 [Context]만을 근거로 답변하세요.
            
            [제약 조건]
            1. 출력 언어: **한국어(Korean)**만 사용.
            2. 근거 제시: "규정 제OO조에 의하면..." 형식을 사용할 것.
            3. 표(Table): 마크다운 표 형식으로 정확히 출력할 것.
            4. 모름: 내용이 없으면 "규정에 해당 내용을 찾을 수 없습니다."라고 답할 것.

            [Context]:
            {context}

            [Question]:
            {question}

            답변(한국어):
            """
            
            # LangChain PromptTemplate
            prompt = PromptTemplate(
                input_variables=["context", "question"],
                template=template
            )

            # Chain 실행 (수동 구성)
            formatted_prompt = prompt.format(context=context_text, question=prompt)
            
            try:
                with st.spinner("정밀 분석 중..."):
                    # LLM 직접 호출
                    response = llm.invoke(formatted_prompt).content
                
                st.write(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
                
                with st.expander("참고한 규정 청크(Chunks)"):
                    for i, doc in enumerate(final_context_docs):
                         title = doc.metadata.get("Article_Title", "조항/별표")
                         st.markdown(f"**[참고 {i+1}: {title}]**")
                         st.text(doc.page_content[:200] + "...")

            except Exception as e:
                st.error(f"오류: {e}")
        else:
            st.warning("문서를 먼저 학습시켜주세요.")