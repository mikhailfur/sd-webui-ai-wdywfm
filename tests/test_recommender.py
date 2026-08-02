import unittest
from unittest.mock import patch

import requests

from ai_wdywfm.application.recommend_loras import recommend_loras
from ai_wdywfm.infrastructure.civitai.client import CivitAIClient


class _Response:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        self.headers = {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.HTTPError("error")
            error.response = self
            raise error


SEARCH_RESPONSE = {
    "items": [{
        "id": 77,
        "name": "Rain Style",
        "creator": {"username": "artist"},
        "updatedAt": "2026-01-02T00:00:00Z",
        "stats": {"downloadCount": 1234, "rating": 4.8, "ratingCount": 50},
        "modelVersions": [{
            "id": 88,
            "baseModel": "Illustrious",
            "images": [{"url": "https://image.civitai.com/preview.jpeg"}],
        }],
    }],
    "metadata": {"currentPage": 2, "totalPages": 3},
}


class CivitAIRecommenderTests(unittest.TestCase):
    def test_search_contract_uses_lora_filter_pagination_and_limit(self):
        with patch(
            "ai_wdywfm.infrastructure.civitai.client.requests.get",
            return_value=_Response(200, SEARCH_RESPONSE),
        ) as get:
            result = CivitAIClient(request_id="search").search_loras(
                "rain style", base_model="Illustrious", nsfw="None", page=2, limit=9,
            )
        self.assertEqual(result["items"][0]["id"], 77)
        params = get.call_args.kwargs["params"]
        self.assertEqual(params["types"], "LORA")
        self.assertEqual(params["page"], 2)
        self.assertEqual(params["limit"], 9)
        self.assertEqual(params["baseModels"], "Illustrious")

    def test_normalized_results_are_read_only_links_and_ids(self):
        with patch(
            "ai_wdywfm.infrastructure.civitai.client.requests.get",
            return_value=_Response(200, SEARCH_RESPONSE),
        ):
            result = recommend_loras(
                "rain", base_url="https://civitai.red/api/v1", request_id="rec",
            )
        item = result["items"][0]
        self.assertEqual(item["model_id"], 77)
        self.assertEqual(item["version_id"], 88)
        self.assertEqual(item["base_model"], "Illustrious")
        self.assertEqual(
            item["page_url"],
            "https://civitai.red/models/77?modelVersionId=88",
        )
        self.assertNotIn("download", item)
        self.assertNotIn("install", item)

    def test_empty_search_is_a_valid_empty_result(self):
        with patch(
            "ai_wdywfm.infrastructure.civitai.client.requests.get",
            return_value=_Response(200, {"items": [], "metadata": {}}),
        ):
            result = recommend_loras(
                "impossible", base_url="https://civitai.com/api/v1",
            )
        self.assertEqual(result["items"], [])


if __name__ == "__main__":
    unittest.main()
