"""数据库层。

- ``base`` 提供 ``Base`` 与通用 mixin
- ``session`` 提供 engine / SessionLocal / get_db 依赖
- ``init_db`` 负责建表与默认用户引导
- ``models/`` 集中所有 ORM 模型
"""
