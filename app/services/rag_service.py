class RAGService:
    def __init__(self, vector_db, llm, embedding_model):
        self.vector_db = vector_db
        self.llm = llm
        self.embedding = embedding_model

    async def answer(self, query, course=None, top_k=5):
        vec = self.embedding.encode(query)
        results = self.vector_db.search(
            vec, top_k=top_k,
            filter={"course": course} if course else None)
        context = "\n\n".join(
            "[来源:%s] %s" % (r.metadata["title"], r.text) for r in results)
        prompt = ("基于以下校园资料回答问题,资料中没有相关信息时请明确说明,并标注信息来源。\n 资料内容:\n" + context + "\n问题:" + query)
        return {"answer": await self.llm.generate(prompt),
        "sources": [{"title": r.metadata["title"],
        "url": r.metadata["url"],
        "score": r.score} for r in results]}
