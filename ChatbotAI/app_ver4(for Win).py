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
print(f"현재 실행 중인 파이썬 경로: {sys.executable}")

# [수정] 에러를 일으키던 from chromadb.errors ... 구문을 삭제하고 기본 모듈만 import 합니다.
import chromadb 

# [설정] 환경 변수
os.environ["NO_PROXY"] = "localhost,127.0.0.1"
os.environ["OLLAMA_HOST"] = "http://127.0.0.1:11434"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.chat_models import ChatOllama
from langchain_chroma import Chroma

from langchain_core.prompts import PromptTemplate
from langchain_core.documents import Document

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter


PERSIST_DIRECTORY = "./chroma_db"

st.set_page_config(page_title="🛡️ 사내 규정 마스터 AI (v3.1)", layout="wide")
st.title("🛡️ 사내 규정 마스터 AI (Ver.1.0)")

# --------------------------------------------------------------------------------
# 1. 문서 전처리 로직 (PDF, DOCX, HWP 통합)
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
        return f"[HWP 변환 오류] HWP 파일은 Word(.docx)로 변환하여 업로드하는 것을 권장합니다.\n오류내용: {e}"

def process_file_to_docs(file, source_name):
    file_ext = os.path.splitext(file.name)[1].lower()
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
        tmp.write(file.getvalue())
        tmp_path = tmp.name

    try:
        if file_ext == ".pdf":
            md_text = pymupdf4llm.to_markdown(tmp_path)
        elif file_ext == ".docx":
            md_text = convert_docx_to_markdown(tmp_path)
        elif file_ext in [".hwp", ".hwpx"]:
            raw_text = extract_hwp_text(tmp_path)
            md_text = clean_markdown_text(raw_text)
            md_text = f"# {source_name} 본문\n\n{md_text}"
        else:
            return []

        md_text = clean_markdown_text(md_text)
        
        md_text = re.sub(r'(^|\n)(제\s*\d+(?:의\d+)?\s*조)', r'\1# \2', md_text)
        md_text = re.sub(r'(^|\n)(\[별표\s*\d+.*?\])', r'\1# \2', md_text)
        md_text = re.sub(r'(^|\n)(\[별지\s*.*?\])', r'\1# \2', md_text)

        headers_to_split_on = [("#", "Article_Title")]
        markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
        header_splits = markdown_splitter.split_text(md_text)
        
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
# 2. 사이드바 (설정)
# --------------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ 시스템 설정")
    CUSTOM_MODELS = ["korean-llama3", "korean-gemma2"] 
    selected_model = st.selectbox("AI 모델 선택", CUSTOM_MODELS, index=0)

    st.markdown("---")
    st.header("📂 문서 업로드")
    uploaded_files = st.file_uploader(
        "규정 파일 (PDF, Word 권장)", 
        type=["pdf", "docx", "hwp"], 
        accept_multiple_files=True
    )
    if uploaded_files:
        st.caption("💡 Tip: 표가 포함된 규정은 **Word(.docx)** 파일이 가장 정확합니다.")

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
    if st.button("🗑️ 지식베이스 초기화 (rm -rf)"):
        st.session_state.clear() 
        try:
            if os.path.exists(PERSIST_DIRECTORY):
                shutil.rmtree(PERSIST_DIRECTORY)
                if 'learned_files' in st.session_state:
                    st.session_state.learned_files = []
                st.success("✅ DB 삭제 완료! F5를 눌러 새로고침하세요.")
            else:
                st.info("삭제할 DB가 없습니다.")
        except Exception as e:
            st.error(f"⚠️ 파일 사용 중 오류: {e}\n(OneDrive 사용 시 동기화를 일시 중지하거나 폴더를 일반 경로로 옮겨주세요.)")

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
    with st.spinner("다양한 문서 포맷 변환 및 정밀 학습 중..."):
        all_docs = []
        for file in uploaded_files:
            try:
                docs = process_file_to_docs(file, file.name)
                all_docs.extend(docs)
            except Exception as e:
                st.error(f"'{file.name}' 처리 중 오류: {e}")
        
        if all_docs:
            vectorstore = Chroma(
                persist_directory=PERSIST_DIRECTORY,
                embedding_function=get_embeddings()
            )
            vectorstore.add_documents(all_docs)
            st.success(f"✅ 총 {len(all_docs)}개의 청크가 학습되었습니다!")
            
            for file in uploaded_files:
                if file.name not in st.session_state.learned_files:
                    st.session_state.learned_files.append(file.name)
            
            time.sleep(1)
            st.rerun()

# --------------------------------------------------------------------------------
# 4. 검색 및 답변 로직 (안전한 에러 처리 적용)
# --------------------------------------------------------------------------------
embeddings = get_embeddings()
vectorstore = None
ensemble_retriever = None

if os.path.exists(PERSIST_DIRECTORY):
    try:
        vectorstore = Chroma(
            persist_directory=PERSIST_DIRECTORY,
            embedding_function=embeddings
        )

        ensemble_retriever = vectorstore.as_retriever(search_kwargs={"k": 10})
        st.success("✅ 규정 DB 로드 완료")

    except Exception as e:
        st.error(f"❌ DB 로드 실패: {e}")
else:
    st.warning("⚠️ Chroma DB 디렉토리가 존재하지 않습니다.")

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
            llm = ChatOllama(
                model=selected_model, 
                base_url="http://127.0.0.1:11434",
                temperature=0,
                top_p=0.1
            )
            
            retrieved_docs = ensemble_retriever.invoke(prompt)

            unique_docs = []
            seen_content = set()
            for doc in retrieved_docs:
                content_snippet = doc.page_content[:100] 
                if content_snippet not in seen_content:
                    unique_docs.append(doc)
                    seen_content.add(content_snippet)
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
            
            try:
                with st.spinner("정밀 분석 중..."):
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
            st.warning("문서를 먼저 학습시켜주세요.")