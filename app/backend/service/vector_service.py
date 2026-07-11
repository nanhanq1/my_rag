# -*- coding: utf-8 -*-
"""
VectorService：负责文档向量化与向量库的增删查。

职责：
  - 加载并拆分文档（txt / md / pdf / csv）
  - 将文档分块写入 Chroma 向量库（携带 doc_id 元数据，便于按文档删除）
  - 按 doc_id 删除文档对应的全部向量
  - 相似度检索（供对话服务作为 RAG 工具使用）
"""
import asyncio
import os.path

from langchain_chroma import Chroma
from langchain_community.document_loaders import TextLoader, PyPDFLoader, CSVLoader
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.backend.config import settings
from app.backend.logger import logger


def load_document(file_path):
    file_type = os.path.splitext(file_path)[-1].lower()
    if file_type in ['.txt', '.md']:
        loader = TextLoader(file_path, encoding='utf-8')
    elif file_type == '.pdf':
        loader = PyPDFLoader(file_path)
    elif file_type == '.csv':
        loader = CSVLoader(file_path)
    else:
        raise ValueError(f"不支持的文件类型：{file_type}")
    return loader.load()

class VectorService:
    def __init__(self):
       # 向量模型
       self.embedding_model = DashScopeEmbeddings(
           model=settings.embedding_model,
           dashscope_api_key=settings.openai_api_key,
       )
       # 向量库
       self.vector_store = Chroma(
           persist_directory=settings.chroma_path,
           embedding_function=self.embedding_model,
           collection_metadata={"hnsw:space": "cosine"},  # 使用cosine计算相似度
       )
       # 文档拆分器
       self.splitter = RecursiveCharacterTextSplitter(
           chunk_size=settings.chunk_size,
           chunk_overlap=settings.chunk_overlap,
           separators=["\n\n", "\n", "。", "，", " ", ""],  # 分块分隔符
       )


    def add_file(self, file_path, doc_id, origin_filename):
        """加载单个文件 -> 拆分 -> 向量化并写入向量库。
        每个分块写入 metadata：doc_id（数据库记录 id）与 source（原始文件名），
        其中 doc_id 用于后续按文档删除。返回写入的分块数量。
        chunks = [
            Document(
                page_content="张三今年18岁",
                metadata={"doc_id": "1","source":"a.pdf"}
            ),
            Document(
                page_content="李四今年20岁",
                metadata={"doc_id": "1","source":"c.pdf"}
            )
        ]
        """
        documents = load_document(file_path)
        chunks = self.splitter.split_documents(documents)

        for chunk in chunks:
            chunk.metadata["doc_id"] = str(doc_id)
            chunk.metadata["source"] = origin_filename
        if chunks:
            self.vector_store.add_documents(chunks)

        return len(chunks)


    async def asearch(self, query):
        """异步检索：在线程池中执行同步 search，避免阻塞事件循环。"""
        return await asyncio.to_thread(self.search, query)

    def search(self, query):
        """相似度检索。

        仅保留相关度分数不低于阈值的结果，过滤掉不相关的命中，
        使上层"知识库中没有找到"的判断更可靠。

        返回二元组 (context, sources)：
            context: 拼接后的上下文文本；无相关结果时为"未检索到相关信息。"
            sources: 命中来源列表（按相关度排序、按文档去重），每项为
                     {"doc_id": ..., "source": 文件名, "score": 分数}
        """

        docs = self.vector_store.similarity_search_with_relevance_scores(query, settings.top_k)

        # 打印每条命中的相关度分数，便于观察分布、校准阈值
        logger.info("检索 query=%r，阈值=%.3f，命中 %d 条：", query, settings.score_threshold, len(docs))
        for i, (doc, score) in enumerate(docs, 1):
            preview = doc.page_content[:30].replace("\n", " ")

        relevant = [(doc, score) for doc, score in docs if score >= settings.score_threshold]
        context = "\n\n".join(doc.page_content for doc, _ in relevant)

        # 提取来源并按文档去重（保留每个文档的最高分）
        sources = []
        seen = set()
        for doc, score in relevant:
            doc_id = doc.metadata.get("doc_id")
            source = doc.metadata.get("source")
            key = (doc_id, source)
            if key in seen:
                continue
            seen.add(key)
            sources.append({"doc_id": doc_id, "source": source, "score": round(float(score), 4)})

        return (context if context else "未检索到相关信息。", sources)

    def delete_by_doc_id(self, doc_id):
        """按 doc_id 删除向量库中的文档。"""
        data = self.vector_store.get(where={"doc_id": str(doc_id)})
        logger.info(doc_id)
        logger.info(f"删除向量库数据：{data}")
        ids = data.get("ids", []) or []
        if ids:
            self.vector_store.delete(ids=ids)
        return len(ids)


