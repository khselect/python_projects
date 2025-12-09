import streamlit as st
import tempfile
import os
import shutil
import re
import pymupdf4llm 
import time
import mammoth  # docx 변환용
import markdownify # html to markdown 용
import olefile # hwp 기초 분석용
import sys

# ChromaDB 관련 임포트
import chromadb
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.chat_models import ChatOllama
from langchain_chroma import Chroma
from langchain_community.retrievers import BM25Retriever
from langchain_core.prompts import PromptTemplate
from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

# [설정] 환경 변수
os.environ["NO_PROXY"] = "localhost,127.0.0.1"
os.environ["OLLAMA_HOST"] = "http://127.0.0.1:11434"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

PERSIST_DIRECTORY = "./chroma_db"

st.set_page_config(page_title="🛡️ 사내 규정 마스터 AI (Win)", layout="wide")
st.title("🛡️ 사내 규정 마스터 AI (Windows Hybrid Ver.)")

# --------------------------------------------------------------------------------
# 0. 핵심 함수 미리 정의 (순서 변경됨: 여기가 중요!)
# --------------------------------------------------------------------------------
@st.cache_resource
def get_embeddings():
    return HuggingFaceEmbeddings(
        model_name="jhgan/ko-sroberta-multitask",
        model_kwargs={'device': 'cpu'},
        encode_kwargs={'normalize_embeddings': True}
    )

# --------------------------------------------------------------------------------
# 1. 문서 전처리 로직
# --------------------------------------------------------------------------------
def clean_markdown_text(text):
    text = text.replace("~~", "") 
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text

def convert_docx_to_markdown(docx_path):
    with open(docx_path, "rb") as docx_file:
        result = mammoth.convert_to_html(docx_file)
        html = result.value
    md_text = markdownify.markdownify(html, heading_style="ATX")
    return md_text

def extract_hwp_text(hwp_path):
    try:
        f = olefile.OleFileIO(hwp_path)
        encoded_text = f.openstream("PrvText").read()
        decoded_text = encoded_text.decode("utf-16le")
        return decoded_text
    except Exception as e:
        return f"[HWP 오류] Word(.docx) 변환 권장. 내용: {e}"

def process_file_to_docs(file, source_name):
    file_ext = os.path.splitext(file.name)[1].lower()
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
        tmp.write(file.getvalue())
        tmp_path = tmp.name

    try:
        if file_ext == ".pdf":
            # pymupdf_layout 경고는 무시해도 됩니다 (단순 안내 메시지)
            md_text = pymupdf4llm.to_markdown(tmp_path)
        elif file_ext == ".docx":
            md_text = convert_docx_to_markdown(tmp_path)
        elif file_ext in [".hwp", ".hwpx"]:
            raw_text = extract_hwp_text(tmp_path)
            md_text = f"# {source_name} 본문\n\n{clean_markdown_text(raw_text)}"
        else:
            return []

        md_text = clean_markdown_text(md_text)
        
        # 헤더 보정
        md_text = re.sub(r'(^|\n)(제\s*\d+(?:의\d+)?\s*조)', r'\1# \2', md_text)
        md_text = re.sub(r'(^|\n)(\[별표\s*\d+.*?\])', r'\1# \2', md_text)
        md_text = re.sub(r'(^|\n)(\[별지\s*.*?\])', r'\1# \2', md_text)

        # 1단계 청킹
        headers_to_split_on = [("#", "Article_Title")]
        markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
        header_splits = markdown_splitter.split_text(md_text)
        
        # 2단계 청킹
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
        
        final_docs = []
        for doc in header_splits:
            splits = text_splitter.split_text(doc.page_content)
            for split_content in splits:
                new_doc = Document(
                    page_content=split_content,
                    metadata={
                        "source": source_name,
                        "Article_Title": doc.metadata.get("Article_Title", "일반"),
                        "file_type": file_ext
                    }
                )
                final_docs.append(new_doc)
        return final_docs
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

# --------------------------------------------------------------------------------
# 2. 저장된 파일 목록 불러오기 & 사이드바
# --------------------------------------------------------------------------------

# [수정됨] 앱 시작 시 저장된 파일명 복구 로직 (get_embeddings가 정의된 후 실행됨)
if "learned_files" not in st.session_state:
    st.session_state.learned_files = []
    
    if os.path.exists(PERSIST_DIRECTORY):
        try:
            # 여기서 get_embeddings()를 호출해도 이제 오류가 나지 않습니다.
            temp_db = Chroma(
                persist_directory=PERSIST_DIRECTORY, 
                embedding_function=get_embeddings()
            )
            
            existing_data = temp_db.get()
            if existing_data and existing_data['metadatas']:
                saved_files = set()
                for meta in existing_data['metadatas']:
                    if meta.get('source'):
                        saved_files.add(meta['source'])
                
                st.session_state.learned_files = list(saved_files)
                
        except Exception as e:
            # pymupdf 경고 등 잡다한 오류는 콘솔에만 찍고 넘어감
            print(f"DB 로드 중 경미한 알림: {e}")

with st.sidebar:
    st.header("⚙️ 시스템 설정")
    CUSTOM_MODELS = ["korean-llama3", "korean-gemma2"] 
    selected_model = st.selectbox("AI 모델 선택", CUSTOM_MODELS, index=0)
    st.markdown("---")
    
    # 학습된 파일 목록 표시
    if st.session_state.learned_files:
        st.write("📚 **학습된 규정 목록:**")
        for f in st.session_state.learned_files:
            st.success(f"📄 {f}")
    else:
        st.info("아직 학습된 규정이 없습니다.")
    
    st.markdown("---")
    
    uploaded_files = st.file_uploader("규정 파일 추가 (PDF, DOCX)", type=["pdf", "docx", "hwp"], accept_multiple_files=True)
    process_button = st.button("🚀 규정 학습 시작")
    
    st.markdown("---")

    if st.button("🗑️ 지식베이스 초기화"):
        st.session_state.clear()
        try:
            if os.path.exists(PERSIST_DIRECTORY):
                shutil.rmtree(PERSIST_DIRECTORY)
                st.session_state.learned_files = []
                st.success("✅ 초기화 완료. F5를 누르세요.")
        except Exception as e:
            st.error(f"오류: {e}")

# --------------------------------------------------------------------------------
# 3. 학습 실행 로직
# --------------------------------------------------------------------------------
if uploaded_files and process_button:
    with st.spinner("학습 중..."):
        all_docs = []
        for file in uploaded_files:
            try:
                docs = process_file_to_docs(file, file.name)
                all_docs.extend(docs)
            except Exception as e:
                st.error(f"{file.name} 오류: {e}")
        
        if all_docs:
            vectorstore = Chroma(
                persist_directory=PERSIST_DIRECTORY,
                embedding_function=get_embeddings()
            )
            vectorstore.add_documents(all_docs)
            st.success(f"✅ 학습 완료 ({len(all_docs)} 청크)")
            
            for file in uploaded_files:
                if file.name not in st.session_state.learned_files:
                    st.session_state.learned_files.append(file.name)
            time.sleep(1)
            st.rerun()

# --------------------------------------------------------------------------------
# 4. 검색 및 답변 로직
# --------------------------------------------------------------------------------
chroma_retriever = None
bm25_retriever = None

if os.path.exists(PERSIST_DIRECTORY):
    try:
        vectorstore = Chroma(
            persist_directory=PERSIST_DIRECTORY,
            embedding_function=get_embeddings()
        )

        chroma_retriever = vectorstore.as_retriever(search_kwargs={"k": 10})

        doc_data = vectorstore.get()
        if doc_data.get("documents"):
            bm25_docs = [
                Document(page_content=t, metadata=m)
                for t, m in zip(doc_data["documents"], doc_data["metadatas"])
            ]
            bm25_retriever = BM25Retriever.from_documents(bm25_docs)
            bm25_retriever.k = 10
            
            # 여기서 성공 메시지는 너무 자주 뜨면 귀찮으므로 주석 처리하거나 print로 변경 가능
            print("✅ 하이브리드 검색 준비 완료")
        else:
            st.info("ℹ️ 문서 수가 적어 벡터 검색만 사용합니다.")

    except Exception as e:
        st.error(f"❌ DB 로드 실패: {e}")

# 채팅 UI
if "messages" not in st.session_state:
    st.session_state.messages = []

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.write(m["content"])

if prompt := st.chat_input("질문하세요..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        if chroma_retriever:
            llm = ChatOllama(
                model=selected_model, 
                base_url="http://127.0.0.1:11434",
                temperature=0,
                top_p=0.1
            )
            
            try:
                # 검색 실행
                vector_docs = chroma_retriever.invoke(prompt) if chroma_retriever else []
                bm25_docs = bm25_retriever.invoke(prompt) if bm25_retriever else []

                combined = vector_docs + bm25_docs
                
                unique_docs = []
                seen = set()
                for doc in combined:
                    key = doc.page_content[:150]
                    if key not in seen:
                        unique_docs.append(doc)
                        seen.add(key)

                final_context_docs = unique_docs[:5]
                context_text = "\n\n".join([doc.page_content for doc in final_context_docs])

                template = """
                [System Instruction]
                당신은 회사 규정 전문 AI입니다. 아래 [Context]만을 근거로 답변하세요.
                사용자가 읽기 편하게 바로 결론부터 답변하세요. 
                "제약 조건을 준수했습니다" 같은 불필요한 말은 절대 하지 마세요.

                [Context]:
                {context}

                [Question]:
                {question}

                답변(한국어):
                """
                
                prompt_obj = PromptTemplate(
                    input_variables=["context", "question"],
                    template=template
                )
                formatted_prompt = prompt_obj.format(context=context_text, question=prompt)
                
                with st.spinner("분석 중..."):
                    response = llm.invoke(formatted_prompt).content
                
                st.write(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
                
                with st.expander("참고한 규정 원문"):
                    for i, doc in enumerate(final_context_docs):
                         title = doc.metadata.get("Article_Title", "조항/별표")
                         source = doc.metadata.get("source", "파일")
                         st.markdown(f"**[참고 {i+1}: {source} - {title}]**")
                         st.text(doc.page_content[:200] + "...")

            except Exception as e:
                st.error(f"오류: {e}")
        else:
            st.warning("규정을 먼저 학습시켜주세요.")