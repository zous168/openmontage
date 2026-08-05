"""SopGeneration@1 契约（LT-006.03.02）—— 从文档生成 / 改进 SOP 提案.

实现方：``plugins/hub-knowledge``（SopGenerationOrchestrator）。
消费方：``plugins/hub-crm`` 的 SOP 路由，经 hub DI ``get_sop_generation()`` 解析，
不再直 import hub_knowledge（消 plugin↔plugin 交叉）。

返回 ``SopProposal``（hub_knowledge 内部类型，含 ``to_api_dict()``）——契约以 ``Any``
表达以保持核心层中立（消费方仅调 ``to_api_dict()``）。
"""

from __future__ import annotations

from typing import Any, Protocol

#: ServiceRegistry / manifest 引用 key
SOP_GENERATION = "sop.generation@1"


class SopGeneration(Protocol):
    async def generate_from_document(self, *, document_text: str) -> Any:
        """文档文本 → 全新 SOP 节点图提案（不落库）."""
        ...

    async def improve_from_document(
        self,
        *,
        existing_nodes: Any,
        sop_name: str,
        sop_type: str,
        document_text: str,
    ) -> Any:
        """现有 SOP + 文档 → 改进后完整节点图提案（不落库）."""
        ...
