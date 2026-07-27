import unittest
from unittest.mock import patch

from ai_wdywfm.infrastructure.forge_neo.inventory import (
    _activation_words,
    _preferred_weight,
    _read_user_metadata_file,
    unload_sd_checkpoint,
)


class InventoryMetadataTests(unittest.TestCase):
    def test_activation_words_are_bounded_and_deduplicated(self):
        words = _activation_words("hero_tag, hero tag, style trigger\nsecond trigger")
        self.assertEqual(words, ["hero_tag", "style trigger", "second trigger"])

    def test_preferred_weight_accepts_bounded_numeric_metadata(self):
        self.assertEqual(_preferred_weight("0.85"), 0.85)
        self.assertIsNone(_preferred_weight(0))
        self.assertIsNone(_preferred_weight("strong"))

    def test_sidecar_metadata_is_cached_and_invalidated_by_file_change(self):
        _read_user_metadata_file.cache_clear()
        target = "C:/models/style.json"
        with patch(
            "ai_wdywfm.infrastructure.forge_neo.inventory.Path.read_text",
            return_value='{"activation text":"first"}',
        ) as read_text:
            self.assertEqual(
                _read_user_metadata_file(target, 1, 27)["activation text"], "first"
            )
            before = _read_user_metadata_file.cache_info()
            self.assertEqual(
                _read_user_metadata_file(target, 1, 27)["activation text"], "first"
            )
            after = _read_user_metadata_file.cache_info()
            self.assertEqual(after.hits, before.hits + 1)
            self.assertEqual(read_text.call_count, 1)

        with patch(
            "ai_wdywfm.infrastructure.forge_neo.inventory.Path.read_text",
            return_value='{"activation text":"second value"}',
        ):
            self.assertEqual(
                _read_user_metadata_file(target, 2, 34)["activation text"], "second value"
            )


    def test_unload_sd_checkpoint_is_safe_outside_forge_runtime(self):
        self.assertFalse(unload_sd_checkpoint())

    def test_unload_sd_checkpoint_skips_when_nothing_loaded(self):
        fake_sd_models = unittest.mock.MagicMock()

        class FakeInitialModel:
            pass

        fake_sd_models.FakeInitialModel = FakeInitialModel
        fake_sd_models.model_data.sd_model = FakeInitialModel()
        with patch.dict("sys.modules", {"modules": unittest.mock.MagicMock(sd_models=fake_sd_models)}):
            self.assertFalse(unload_sd_checkpoint())
            fake_sd_models.unload_model_weights.assert_not_called()

    def test_unload_sd_checkpoint_unloads_when_model_present(self):
        fake_sd_models = unittest.mock.MagicMock()

        class FakeInitialModel:
            pass

        fake_sd_models.FakeInitialModel = FakeInitialModel
        fake_sd_models.model_data.sd_model = object()
        with patch.dict("sys.modules", {"modules": unittest.mock.MagicMock(sd_models=fake_sd_models)}):
            self.assertTrue(unload_sd_checkpoint())
            fake_sd_models.unload_model_weights.assert_called_once()


if __name__ == "__main__":
    unittest.main()
