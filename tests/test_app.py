import tempfile
import unittest
from pathlib import Path

import app


class RetrievalTests(unittest.TestCase):
    def test_retrieves_original_excerpt(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            app.init_db(db_path)
            app.add_document(
                "测试制度",
                "test://policy",
                "重要事件需要在15分钟内响应，并在4小时内恢复核心服务。",
                db_path,
            )

            results = app.retrieve("重要事件多久响应", db_path=db_path)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["title"], "测试制度")
            self.assertIn("15分钟", results[0]["excerpt"])

    def test_fallback_answer_is_grounded(self):
        response = app.fallback_answer(
            "问题",
            [
                {
                    "title": "文档",
                    "source": "source://a",
                    "excerpt": "这是数据库原文。",
                }
            ],
        )

        self.assertIn("这是数据库原文", response)
        self.assertIn("总结", response)

    def test_document_count_answer_uses_sql_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            app.init_db(db_path)
            app.add_document("文档一", "test://one", "内容一", db_path)
            app.add_document("文档二", "test://two", "内容二", db_path)

            response = app.document_count_answer(db_path)

            self.assertIn("2 条记录", response["answer"])
            self.assertFalse(response["used_llm"])
            self.assertIn("SELECT COUNT(*) FROM documents", response["citations"][0]["excerpt"])

    def test_detects_document_count_question(self):
        self.assertTrue(app.is_document_count_question("数据库有多少条记录？"))
        self.assertTrue(app.is_document_count_question("文档总数是多少"))
        self.assertFalse(app.is_document_count_question("P0 故障多久响应？"))

    def test_clean_llm_answer_removes_think_block(self):
        response = app.clean_llm_answer("<think>hidden reasoning</think>\n结论：可以回答。")

        self.assertEqual(response, "结论：可以回答。")


if __name__ == "__main__":
    unittest.main()
