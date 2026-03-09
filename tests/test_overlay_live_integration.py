import os
import tempfile
import unittest
from unittest.mock import patch

import config
from desktop_bridge.service import BridgeService


class BridgeServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.original_db_path = config.DB_PATH
        config.DB_PATH = os.path.join(self.tempdir.name, "radcopilot-test.db")
        self.services = []

    async def asyncTearDown(self):
        for service in self.services:
            await service.stop()
        config.DB_PATH = self.original_db_path
        self.tempdir.cleanup()

    def _make_service(self, *, demo_mode: bool = False) -> BridgeService:
        service = BridgeService(start_backend_server=False, demo_mode=demo_mode)
        self.services.append(service)
        return service

    async def test_capture_and_analyze_updates_bridge_state(self):
        service = self._make_service()

        async def fake_analyze(image_b64: str, patient_context: str = "") -> dict:
            self.assertEqual(image_b64, "encoded-image")
            self.assertEqual(patient_context, "")
            return {
                "findings": "Possible right upper lobe nodule",
                "confidence": "medium",
                "specialist_flags": ["pulmonary_nodule_v2"],
                "recommended_action": "Compare with prior chest CT",
            }

        service.client.analyze = fake_analyze

        with patch(
            "desktop_bridge.service.capture_screen",
            return_value=("encoded-image", "hash-123"),
        ):
            result = await service.capture_and_analyze()

        state = await service.get_state()

        self.assertEqual(result["image_hash"], "hash-123")
        self.assertEqual(state["analysis"]["finding"], "Possible right upper lobe nodule")
        self.assertEqual(state["analysis"]["recommendation"], "Compare with prior chest CT")
        self.assertEqual(state["status_message"], "Analysis ready")

    async def test_flag_current_read_marks_confirmation(self):
        service = self._make_service()

        async def fake_analyze(image_b64: str, patient_context: str = "") -> dict:
            return {
                "findings": "Pleural effusion present bilaterally",
                "confidence": "medium",
                "specialist_flags": ["pleural_effusion_v1"],
                "recommended_action": "Correlate clinically",
            }

        async def fake_flag(ai_finding: str, radiologist_override: str, image_hash: str) -> dict:
            self.assertEqual(ai_finding, "Pleural effusion present bilaterally")
            self.assertEqual(radiologist_override, "Favor volume overload over acute process")
            self.assertEqual(image_hash, "hash-456")
            return {"status": "received", "flag_id": "flag-1"}

        service.client.analyze = fake_analyze
        service.client.flag = fake_flag

        with patch(
            "desktop_bridge.service.capture_screen",
            return_value=("encoded-image", "hash-456"),
        ):
            await service.capture_and_analyze()

        result = await service.flag_current_read("Favor volume overload over acute process")
        state = await service.get_state()

        self.assertEqual(result["message"], "Flagged for review")
        self.assertEqual(state["confirmation_message"], "Flagged for review")
        self.assertEqual(
            service.db.get_today_disagreements()[0]["override_note"],
            "Favor volume overload over acute process",
        )

    async def test_demo_mode_bootstraps_sample_analysis(self):
        service = self._make_service(demo_mode=True)
        await service.start()

        state = await service.get_state()

        self.assertTrue(state["demo_mode"])
        self.assertEqual(state["analysis"]["image_hash"], "demo-image-hash")
        self.assertEqual(state["status_message"], "Analysis ready")
