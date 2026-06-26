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


if __name__ == "__main__":
    unittest.main()

