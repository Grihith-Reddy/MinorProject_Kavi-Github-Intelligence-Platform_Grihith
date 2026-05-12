import unittest

from app.services.memory_service import deduplicate_memory_items, extract_turn_memory_items


class MemoryServiceTests(unittest.TestCase):
    def test_extract_turn_memory_items_captures_preference_and_repo_facts(self):
        memory_items = extract_turn_memory_items(
            query="Please use TypeScript examples. We need to build webhook retry orchestration.",
            answer="Implemented memory with repo context and retry flow references.",
            structured={
                "title": "Webhook Retry Plan",
                "summary": "Use retry orchestration in TypeScript and persist execution checkpoints.",
                "sections": [
                    {"heading": "Implementation", "bullets": ["Create retry worker with durable state."]},
                ],
            },
            sources=[
                {
                    "pr_number": 42,
                    "pr_title": "Add retry worker",
                    "files": [
                        {"file_path": "backend/app/workers/retry_worker.py", "start_line": 1, "end_line": 80},
                    ],
                }
            ],
            repo_meta={
                "id": "repo-1",
                "full_name": "acme/platform",
                "default_branch": "main",
            },
        )

        signatures = {(item.get("kind"), item.get("key")) for item in memory_items}
        self.assertIn(("preference", "preferred_language"), signatures)
        self.assertIn(("pull_request", "pr#42"), signatures)
        self.assertIn(("file", "backend/app/workers/retry_worker.py"), signatures)
        self.assertIn(("repository", "acme/platform"), signatures)

    def test_deduplicate_memory_items_prefers_higher_confidence(self):
        deduped = deduplicate_memory_items(
            [
                {
                    "memory_scope": "conversation",
                    "kind": "insight",
                    "key": "Architecture",
                    "value": "First value",
                    "confidence": 0.4,
                },
                {
                    "memory_scope": "conversation",
                    "kind": "insight",
                    "key": "Architecture",
                    "value": "Better value",
                    "confidence": 0.8,
                },
            ]
        )

        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0]["value"], "Better value")
        self.assertGreaterEqual(deduped[0]["confidence"], 0.8)


if __name__ == "__main__":
    unittest.main()
