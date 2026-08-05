"""core.contracts —— 插件间共享能力的契约（Protocol）.

中立第三方：消费方 A 与提供方 B **都只 import 这里的契约**，互不 import
（设计 docs/Hermes插件服务共享机制设计.md §8）。契约 key 带 ``@version``。
"""
