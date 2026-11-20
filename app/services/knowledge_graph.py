"""知识图谱服务：MVP 用内存字典 + 邻接表替代 Neo4j，预留真实图数据库接入分支。

- 节点类型：course（课程）/ knowledge_point（知识点）/ document（资料）；
- 边类型：contains（包含）/ prerequisite（先修）/ references（引用）；
- QA Agent 锁定接口：expand(query) -> {"knowledge_points": [...], "sources": [{title, url, score}]}；
- 基础维护方法：add_entity / add_relation / query_neighbors；
- mock 模式内置少量示例图数据，无需任何外部依赖；backend="neo4j" 时抛 NotImplementedError。
"""

from typing import Any, Dict, List, Optional

from app.config import get_config, is_mock_mode

ENTITY_TYPES = ("course", "knowledge_point", "document")
RELATION_TYPES = ("contains", "prerequisite", "references")

SEED_SCORE = 0.9
HOP_DECAY = 0.2
MAX_DEPTH = 1


class KnowledgeGraphService:
    """内存图谱：实体表 + 关系表 + 出边邻接表。"""

    def __init__(self, config: Optional[Dict[str, Any]] = None, backend: Optional[str] = None,
                 seeded: bool = True) -> None:
        self.config = config if config is not None else get_config()
        self.mock_mode = bool(self.config.get("mock_mode", is_mock_mode()))
        self.backend = backend or self.config.get("graph_backend") or "memory"
        self.entities: Dict[str, Dict[str, Any]] = {}
        self.relations: List[Dict[str, str]] = []
        self.adjacency: Dict[str, List[str]] = {}
        if self.backend == "neo4j":
            self._connect_neo4j()
        if seeded:
            self._seed_mock_data()

    # ------------------------------------------------------------------ 真实接入点

    def _connect_neo4j(self) -> None:
        # 预留：真实模式在此创建 Neo4j Driver（neo4j://user:pass@host:7687）。
        raise NotImplementedError("Neo4j 接入待实现")

    def _expand_neo4j(self, query: str, top_k: int) -> Dict[str, Any]:
        # 预留：真实模式在此执行 Cypher 检索并映射为同一输出结构。
        raise NotImplementedError("Neo4j 图谱检索待实现")

    # ------------------------------------------------------------------ 基础维护

    def add_entity(self, entity_id: str, entity_type: str, name: str,
                   metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if entity_type not in ENTITY_TYPES:
            raise ValueError("未知节点类型: %s（可选 %s）" % (entity_type, ", ".join(ENTITY_TYPES)))
        if not entity_id or not name:
            raise ValueError("entity_id 与 name 不能为空")
        if entity_id in self.entities:
            raise ValueError("实体已存在: %s" % entity_id)
        entity = {"id": entity_id, "type": entity_type, "name": name, "metadata": metadata or {}}
        self.entities[entity_id] = entity
        self.adjacency.setdefault(entity_id, [])
        return dict(entity)

    def add_relation(self, source_id: str, target_id: str, relation_type: str) -> Dict[str, str]:
        if relation_type not in RELATION_TYPES:
            raise ValueError("未知边类型: %s（可选 %s）" % (relation_type, ", ".join(RELATION_TYPES)))
        for entity_id in (source_id, target_id):
            if entity_id not in self.entities:
                raise KeyError("实体不存在: %s" % entity_id)
        for relation in self.relations:
            if relation == {"source": source_id, "target": target_id, "type": relation_type}:
                return dict(relation)
        relation = {"source": source_id, "target": target_id, "type": relation_type}
        self.relations.append(relation)
        self.adjacency.setdefault(source_id, []).append(target_id)
        return dict(relation)

    def query_neighbors(self, entity_id: str, relation_type: Optional[str] = None) -> List[Dict[str, Any]]:
        if entity_id not in self.entities:
            raise KeyError("实体不存在: %s" % entity_id)
        neighbors: List[Dict[str, Any]] = []
        for relation in self.relations:
            if relation["source"] != entity_id:
                continue
            if relation_type is not None and relation["type"] != relation_type:
                continue
            target = self.entities[relation["target"]]
            neighbors.append({
                "id": target["id"],
                "type": target["type"],
                "name": target["name"],
                "relation": relation["type"],
            })
        return neighbors

    # ------------------------------------------------------------------ QA 接口

    def expand(self, query: str, top_k: int = 5) -> Dict[str, Any]:
        """从命中实体出发做 1 跳扩展，返回知识点与资料来源（含 score）。"""
        if self.backend == "neo4j":
            return self._expand_neo4j(query, top_k)
        query = (query or "").strip()
        if not query:
            return {"knowledge_points": [], "sources": []}

        seeds = [entity for entity in self.entities.values() if self._matches(entity, query)]
        scored: Dict[str, float] = {}
        visited = set()
        frontier = [(entity["id"], SEED_SCORE, 0) for entity in seeds]
        while frontier:
            node_id, score, depth = frontier.pop(0)
            if node_id in visited:
                continue
            visited.add(node_id)
            scored[node_id] = max(scored.get(node_id, 0.0), score)
            if depth >= MAX_DEPTH:
                continue
            for neighbor in self.query_neighbors(node_id):
                if neighbor["id"] not in visited:
                    frontier.append((neighbor["id"], round(score - HOP_DECAY, 2), depth + 1))

        # 反向补全：资料 -> 知识点 是 references 方向，需回收引用该知识点的资料作为来源
        for node_id in list(visited):
            if self.entities[node_id]["type"] != "knowledge_point":
                continue
            for relation in self.relations:
                if relation["target"] == node_id and relation["type"] == "references":
                    document_id = relation["source"]
                    fallback = round(scored.get(node_id, 0.0) - HOP_DECAY, 2)
                    scored[document_id] = max(scored.get(document_id, 0.0), max(fallback, 0.0))

        knowledge_points: List[str] = []
        sources: List[Dict[str, Any]] = []
        for node_id, score in sorted(scored.items(), key=lambda item: item[1], reverse=True):
            entity = self.entities[node_id]
            if entity["type"] == "knowledge_point":
                knowledge_points.append(entity["name"])
            elif entity["type"] == "document":
                sources.append({
                    "title": entity["name"],
                    "url": entity.get("metadata", {}).get("url", ""),
                    "score": score,
                })
            if len(knowledge_points) >= top_k and len(sources) >= top_k:
                break
        return {"knowledge_points": knowledge_points[:top_k], "sources": sources[:top_k]}

    def _matches(self, entity: Dict[str, Any], query: str) -> bool:
        if entity["name"] and entity["name"] in query:
            return True
        keywords = entity.get("metadata", {}).get("keywords") or []
        return any(keyword and keyword in query for keyword in keywords)

    # ------------------------------------------------------------------ 示例数据

    def _seed_mock_data(self) -> None:
        self.add_entity("course:gaoshu", "course", "高等数学")
        self.add_entity("kp:daoshu", "knowledge_point", "导数",
                        {"keywords": ["求导", "导数"]})
        self.add_entity("kp:weifen", "knowledge_point", "微分",
                        {"keywords": ["微分"]})
        self.add_entity("kp:taile", "knowledge_point", "泰勒公式",
                        {"keywords": ["泰勒", "展开"]})
        self.add_entity("kp:jixian", "knowledge_point", "极限",
                        {"keywords": ["极限", "趋于"]})
        self.add_entity("doc:ch03", "document", "高等数学 第三章 课件",
                        {"url": "mock://course/gaoshu/ch03", "keywords": ["第三章"]})
        self.add_entity("doc:ch03-ex", "document", "高等数学 第三章 习题",
                        {"url": "mock://course/gaoshu/ch03-ex", "keywords": ["第三章", "习题"]})
        self.add_entity("doc:daoshu-note", "document", "导数公式速查表",
                        {"url": "mock://notes/daoshu", "keywords": ["速查", "公式"]})

        self.add_relation("course:gaoshu", "kp:daoshu", "contains")
        self.add_relation("course:gaoshu", "kp:weifen", "contains")
        self.add_relation("course:gaoshu", "kp:taile", "contains")
        self.add_relation("course:gaoshu", "kp:jixian", "contains")
        self.add_relation("kp:jixian", "kp:daoshu", "prerequisite")
        self.add_relation("kp:daoshu", "kp:weifen", "prerequisite")
        self.add_relation("doc:ch03", "kp:daoshu", "references")
        self.add_relation("doc:ch03", "kp:weifen", "references")
        self.add_relation("doc:ch03-ex", "kp:daoshu", "references")
        self.add_relation("doc:daoshu-note", "kp:daoshu", "references")
