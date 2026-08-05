"""KnowledgeRetrieval@1 契约（LT-006.03.01 · D5）—— 知识检索能力 SSOT.

设计依据（实测 SOP `sop_engine_ai_mixin` 现经直 import 消费的 6 类 hub_knowledge 能力）：
- ``search``                  向量/混合检索（= 既有 KnowledgeClient.search 超集起点）
- ``resolve_dataset_id``      kb_space → dataset_id（取代 orchestration.dataset_resolver）
- ``search_industry_keywords`` 虚拟 space industry_keyword（取代 orchestration.industry_keyword_retrieval；
                              数据在 hub_crm → 由 hub_knowledge 经 IndustryKeywordData 契约取，见 §9.1 真双向）
- ``faq_match``               FAQ 短路检索（取代 storage.faq_repository + domain.hybrid_retrieval）
- ``log_retrieval``           检索埋点（取代 orchestration.retrieval_logger）

**SSOT（D5）**：``KnowledgeChunk`` / ``Dataset`` 模型以本文件为准；
``hub/adapter/base/external_protocols/knowledge_client.py`` 的 ``KnowledgeClient``（仅 ``search``）
在 .03.02 降为本契约的 **子集别名 / re-export shim**，不双写。

契约 key（ServiceRegistry / manifest 引用）：``knowledge.retrieval@1``。
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

#: ServiceRegistry / manifest provides_services / requires_services 的稳定 key
KNOWLEDGE_RETRIEVAL = "knowledge.retrieval@1"


class KnowledgeChunk(BaseModel):
    """检索出的一段知识（SSOT·D5）."""

    chunk_id: str
    document_id: str
    dataset_id: str
    content: str
    score: float = Field(ge=0.0, le=1.0)
    metadata: dict = Field(default_factory=dict)


class Dataset(BaseModel):
    """知识库 dataset（SSOT·D5）."""

    id: str
    name: str
    description: str | None = None
    document_count: int = 0


class FaqMatch(BaseModel):
    """FAQ 命中（faq_match 返回；实测 SOP 用 {question, score}）."""

    question: str
    score: float = 0.0


class KnowledgeRetrieval(Protocol):
    """SOP/Agent 共用的知识检索契约（既有 KnowledgeClient 的超集）.

    实现方：``plugins/hub-knowledge``（provide_service(KNOWLEDGE_RETRIEVAL, impl)）。
    消费方：SOP 引擎经 hub DI 注入（路径 B，§7.4）/ 纯 Hermes 插件经 ctx.get_service。
    """

    async def search(
        self,
        *,
        query: str,
        dataset_ids: list[str],
        top_k: int = 5,
        rerank: bool = False,
        meta_filter: dict | None = None,
        retrieval_mode: str = "hybrid",
        intent_keywords: str | None = None,
    ) -> list[dict]:
        """向量/混合检索（既有 HubKnowledgeClient.search 超集；meta_filter 默认
        None，SOP 默认 {"is_current": True}；intent_keywords 为三信号 signal_2）.

        返回引擎 chunk dict 列表（形状对齐 KnowledgeChunk 字段；消费方 _chunk_to_dict
        同时吃 dict/对象，故返 dict 无损、零序列化、零类型churn）。
        """
        ...

    def keywords_for_intent(self, intent_label: str | None) -> str:
        """意图标签 → 检索关键词（取代直 import hybrid_retrieval.intent_label_to_keywords）."""
        ...

    async def resolve_dataset_id(
        self, *, tenant_id: str, kb_space: str,
    ) -> str | None:
        """kb_space → dataset_id（与文档上传同一路由）；无则 None."""
        ...

    async def search_industry_keywords(
        self, *, tenant_id: str, query: str, top_k: int = 20,
    ) -> list[dict]:
        """虚拟 space industry_keyword 检索（chunk dict；关键词数据经 IndustryKeywordData）."""
        ...

    async def faq_match(
        self, *, query: str, top_k: int = 3, threshold: float = 0.0,
    ) -> list[dict]:
        """FAQ 短路检索（预存向量；失败降级关键词相似度）；返 [{question, score}]."""
        ...

    async def log_retrieval(
        self,
        *,
        query: str,
        dataset_ids: list[str],
        chunks: list[dict],
        trigger_source: str = "sop",
    ) -> None:
        """检索埋点（best-effort，失败不阻断主链）."""
        ...
