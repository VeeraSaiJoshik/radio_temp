"""
Unit tests for the dummy orchestrator.

No image input required — all tests operate on the stage fixture data
and the FastAPI endpoint directly. Firebase is mocked throughout.
"""

import time
import threading
import pytest
from unittest.mock import patch, MagicMock, call
from fastapi.testclient import TestClient

import orchestrator.main as orch_module
from orchestrator.main import (
    TB_STAGES,
    PNEUMONIA_STAGES,
    STAGE_DELAYS,
    _run_pipeline,
    app,
)
from models import DiagnosisState, ModelNode

client = TestClient(app)

# ── Helpers ────────────────────────────────────────────────────────────────────

TEST_ID = "unit-test-image-001"

# Minimal valid OrchestratorInput payload (no real image needed)
VALID_PAYLOAD = {
    "db_information": {
        "id": TEST_ID,
        "image_id": "550e8400-e29b-41d4-a716-446655440000",
        "user_id": "",
        "image_location": "Chest",
        "image_type": "X-Ray",
        "image_date": "2025-01-01T00:00:00",
        "metadata": {
            "first_name": "Test",
            "last_name": "Patient",
            "full_name": "Test Patient",
        },
    },
    "image": "",
}


@pytest.fixture(autouse=True)
def reset_counter():
    """Reset the module-level call counter before every test."""
    with orch_module._counter_lock:
        orch_module._call_counter = 0
    yield
    with orch_module._counter_lock:
        orch_module._call_counter = 0


# ── Stage count ────────────────────────────────────────────────────────────────

class TestStageCounts:
    def test_tb_has_five_stages(self):
        assert len(TB_STAGES) == 5

    def test_pneumonia_has_five_stages(self):
        assert len(PNEUMONIA_STAGES) == 5

    def test_delays_match_stage_count(self):
        assert len(STAGE_DELAYS) == len(TB_STAGES)
        assert len(STAGE_DELAYS) == len(PNEUMONIA_STAGES)

    def test_first_stage_has_zero_delay(self):
        assert STAGE_DELAYS[0] == 0


# ── DiagnosisState identity ────────────────────────────────────────────────────

class TestDiagnosisStateIdentity:
    """id and image_id must always equal the input image_id."""

    @pytest.mark.parametrize("stage_fn", TB_STAGES)
    def test_tb_stage_id_matches(self, stage_fn):
        state = stage_fn(TEST_ID)
        assert state.id == TEST_ID
        assert state.image_id == TEST_ID

    @pytest.mark.parametrize("stage_fn", PNEUMONIA_STAGES)
    def test_pneumonia_stage_id_matches(self, stage_fn):
        state = stage_fn(TEST_ID)
        assert state.id == TEST_ID
        assert state.image_id == TEST_ID


# ── Percent completion progression ────────────────────────────────────────────

class TestPercentCompletion:
    def test_tb_completion_is_monotonically_increasing(self):
        values = [TB_STAGES[i](TEST_ID).percent_completion for i in range(5)]
        assert values == sorted(values), f"Not monotonically increasing: {values}"

    def test_pneumonia_completion_is_monotonically_increasing(self):
        values = [PNEUMONIA_STAGES[i](TEST_ID).percent_completion for i in range(5)]
        assert values == sorted(values), f"Not monotonically increasing: {values}"

    def test_tb_first_stage_is_zero(self):
        assert TB_STAGES[0](TEST_ID).percent_completion == 0.0

    def test_pneumonia_first_stage_is_zero(self):
        assert PNEUMONIA_STAGES[0](TEST_ID).percent_completion == 0.0

    def test_tb_final_stage_is_complete(self):
        assert TB_STAGES[-1](TEST_ID).percent_completion == 1.0

    def test_pneumonia_final_stage_is_complete(self):
        assert PNEUMONIA_STAGES[-1](TEST_ID).percent_completion == 1.0

    def test_all_intermediate_stages_are_partial(self):
        for stages in (TB_STAGES, PNEUMONIA_STAGES):
            for stage_fn in stages[1:-1]:
                pct = stage_fn(TEST_ID).percent_completion
                assert 0.0 < pct < 1.0, f"Intermediate stage has bad completion: {pct}"


# ── Root node status progression ──────────────────────────────────────────────

class TestRootNodeStatus:
    def test_tb_first_stage_root_is_in_progress(self):
        assert TB_STAGES[0](TEST_ID).progress_tree.status == "in-progress"

    def test_pneumonia_first_stage_root_is_in_progress(self):
        assert PNEUMONIA_STAGES[0](TEST_ID).progress_tree.status == "in-progress"

    def test_tb_final_root_is_positive(self):
        assert TB_STAGES[-1](TEST_ID).progress_tree.status == "positive"

    def test_pneumonia_final_root_is_negative(self):
        assert PNEUMONIA_STAGES[-1](TEST_ID).progress_tree.status == "negative"

    def test_all_status_values_are_valid(self):
        valid = {"pending", "positive", "negative", "in-progress"}

        def check_node(node: ModelNode):
            assert node.status in valid, f"Invalid status: {node.status}"
            for child in node.children:
                check_node(child)

        for stages in (TB_STAGES, PNEUMONIA_STAGES):
            for stage_fn in stages:
                check_node(stage_fn(TEST_ID).progress_tree)


# ── Tree growth (children appear progressively) ───────────────────────────────

class TestTreeGrowth:
    def test_tb_stage_0_has_no_children(self):
        tree = TB_STAGES[0](TEST_ID).progress_tree
        assert tree.children == []

    def test_pneumonia_stage_0_has_no_children(self):
        tree = PNEUMONIA_STAGES[0](TEST_ID).progress_tree
        assert tree.children == []

    def test_tb_stage_1_root_has_one_child(self):
        tree = TB_STAGES[1](TEST_ID).progress_tree
        assert len(tree.children) == 1

    def test_tb_stage_2_triage_has_one_child(self):
        triage = TB_STAGES[2](TEST_ID).progress_tree.children[0]
        assert len(triage.children) == 1

    def test_tb_stage_3_triage_has_two_children(self):
        triage = TB_STAGES[3](TEST_ID).progress_tree.children[0]
        assert len(triage.children) == 2

    def test_tb_final_triage_has_two_children(self):
        triage = TB_STAGES[-1](TEST_ID).progress_tree.children[0]
        assert len(triage.children) == 2

    def test_pneumonia_final_triage_has_two_children(self):
        triage = PNEUMONIA_STAGES[-1](TEST_ID).progress_tree.children[0]
        assert len(triage.children) == 2


# ── Model names are non-empty ──────────────────────────────────────────────────

class TestModelMetadata:
    def _all_nodes(self, node: ModelNode):
        yield node
        for child in node.children:
            yield from self._all_nodes(child)

    def test_all_tb_model_names_non_empty(self):
        for stage_fn in TB_STAGES:
            for node in self._all_nodes(stage_fn(TEST_ID).progress_tree):
                assert node.model.name.strip(), "Empty model name found"

    def test_all_pneumonia_model_names_non_empty(self):
        for stage_fn in PNEUMONIA_STAGES:
            for node in self._all_nodes(stage_fn(TEST_ID).progress_tree):
                assert node.model.name.strip(), "Empty model name found"

    def test_all_tb_model_providers_non_empty(self):
        for stage_fn in TB_STAGES:
            for node in self._all_nodes(stage_fn(TEST_ID).progress_tree):
                assert node.model.provider.strip(), "Empty model provider found"

    def test_root_node_name_is_orchestrator(self):
        for stage_fn in TB_STAGES + PNEUMONIA_STAGES:
            root = stage_fn(TEST_ID).progress_tree
            assert "orchestrator" in root.model.name.lower()


# ── Annotations ───────────────────────────────────────────────────────────────

class TestAnnotations:
    def test_tb_early_stages_have_no_annotations(self):
        for stage_fn in TB_STAGES[:-1]:
            assert TB_STAGES[0](TEST_ID).annotations == []

    def test_tb_final_stage_has_two_annotations(self):
        annotations = TB_STAGES[-1](TEST_ID).annotations
        assert len(annotations) == 2

    def test_tb_annotations_have_required_fields(self):
        for ann in TB_STAGES[-1](TEST_ID).annotations:
            assert ann.name.strip()
            assert ann.description.strip()
            assert ann.number >= 1
            assert ann.confidence in ("high", "medium", "low")
            assert len(ann.annotations) >= 1

    def test_tb_annotation_numbers_are_unique(self):
        annotations = TB_STAGES[-1](TEST_ID).annotations
        numbers = [a.number for a in annotations]
        assert len(numbers) == len(set(numbers))

    def test_pneumonia_all_stages_have_no_annotations(self):
        for stage_fn in PNEUMONIA_STAGES:
            assert stage_fn(TEST_ID).annotations == []


# ── Overall diagnosis context ──────────────────────────────────────────────────

class TestDiagnosisContext:
    def test_tb_early_stages_have_empty_context(self):
        for stage_fn in TB_STAGES[:-1]:
            assert stage_fn(TEST_ID).overall_diagnosis_context == ""

    def test_tb_final_stage_context_non_empty(self):
        ctx = TB_STAGES[-1](TEST_ID).overall_diagnosis_context
        assert len(ctx) > 20

    def test_tb_final_context_mentions_positive(self):
        ctx = TB_STAGES[-1](TEST_ID).overall_diagnosis_context.lower()
        assert "positive" in ctx or "tb" in ctx

    def test_pneumonia_early_stages_have_empty_context(self):
        for stage_fn in PNEUMONIA_STAGES[:-1]:
            assert stage_fn(TEST_ID).overall_diagnosis_context == ""

    def test_pneumonia_final_context_non_empty(self):
        ctx = PNEUMONIA_STAGES[-1](TEST_ID).overall_diagnosis_context
        assert len(ctx) > 20

    def test_pneumonia_final_context_mentions_negative(self):
        ctx = PNEUMONIA_STAGES[-1](TEST_ID).overall_diagnosis_context.lower()
        assert "negative" in ctx or "no " in ctx


# ── Patient counter alternation ────────────────────────────────────────────────

class TestCounterAlternation:
    @patch("orchestrator.main.FirebaseDatabase")
    @patch("orchestrator.main.time.sleep")
    def test_first_call_uses_tb_stages(self, mock_sleep, mock_db_class):
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        _run_pipeline(TEST_ID, 0)

        first_call_state = mock_db.set_rl_data.call_args_list[0][0][1]
        assert first_call_state.percent_completion == 0.0

        last_call_state = mock_db.set_rl_data.call_args_list[-1][0][1]
        assert last_call_state.percent_completion == 1.0
        assert len(last_call_state.annotations) == 2  # TB has annotations

    @patch("orchestrator.main.FirebaseDatabase")
    @patch("orchestrator.main.time.sleep")
    def test_second_call_uses_pneumonia_stages(self, mock_sleep, mock_db_class):
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        _run_pipeline(TEST_ID, 1)

        last_call_state = mock_db.set_rl_data.call_args_list[-1][0][1]
        assert last_call_state.percent_completion == 1.0
        assert last_call_state.annotations == []  # Pneumonia has no annotations

    def test_api_counter_increments_on_each_request(self):
        with patch("orchestrator.main.threading.Thread") as mock_thread:
            mock_thread.return_value = MagicMock()
            client.post("/register", json=VALID_PAYLOAD)
            client.post("/register", json=VALID_PAYLOAD)
        assert orch_module._call_counter == 2

    def test_api_alternates_patient_index(self):
        patient_indices = []

        original_run = orch_module._run_pipeline

        def capture_index(image_id, patient_index):
            patient_indices.append(patient_index)

        with patch("orchestrator.main._run_pipeline", side_effect=capture_index), \
             patch("orchestrator.main.threading.Thread") as mock_thread:
            # Make the thread call the target immediately (synchronous)
            def fake_thread_init(target, args, daemon):
                target(*args)
                t = MagicMock()
                t.start = MagicMock()
                return t
            mock_thread.side_effect = fake_thread_init

            client.post("/register", json=VALID_PAYLOAD)
            client.post("/register", json=VALID_PAYLOAD)
            client.post("/register", json=VALID_PAYLOAD)

        assert patient_indices == [0, 1, 0]


# ── Pipeline execution ─────────────────────────────────────────────────────────

class TestPipelineExecution:
    @patch("orchestrator.main.FirebaseDatabase")
    @patch("orchestrator.main.time.sleep")
    def test_pipeline_calls_set_rl_data_five_times(self, mock_sleep, mock_db_class):
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        _run_pipeline(TEST_ID, 0)

        assert mock_db.set_rl_data.call_count == 5

    @patch("orchestrator.main.FirebaseDatabase")
    @patch("orchestrator.main.time.sleep")
    def test_pipeline_always_writes_to_diagnosis_path(self, mock_sleep, mock_db_class):
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        _run_pipeline(TEST_ID, 0)

        for c in mock_db.set_rl_data.call_args_list:
            path_arg = c[0][0]
            assert path_arg == "diagnosis"

    @patch("orchestrator.main.FirebaseDatabase")
    @patch("orchestrator.main.time.sleep")
    def test_pipeline_stages_written_in_completion_order(self, mock_sleep, mock_db_class):
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        _run_pipeline(TEST_ID, 0)

        pct_values = [
            c[0][1].percent_completion
            for c in mock_db.set_rl_data.call_args_list
        ]
        assert pct_values == sorted(pct_values), f"Out of order: {pct_values}"

    @patch("orchestrator.main.FirebaseDatabase")
    @patch("orchestrator.main.time.sleep")
    def test_pipeline_sleeps_between_stages(self, mock_sleep, mock_db_class):
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        _run_pipeline(TEST_ID, 0)

        # Should sleep once per stage (including 0s first sleep)
        assert mock_sleep.call_count == 5
        # First sleep is 0 seconds
        assert mock_sleep.call_args_list[0] == call(0)
        # All subsequent sleeps are 1.5 seconds
        for c in mock_sleep.call_args_list[1:]:
            assert c == call(1.5)

    @patch("orchestrator.main.FirebaseDatabase")
    @patch("orchestrator.main.time.sleep")
    def test_pipeline_final_state_is_complete(self, mock_sleep, mock_db_class):
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        _run_pipeline(TEST_ID, 0)

        final_state: DiagnosisState = mock_db.set_rl_data.call_args_list[-1][0][1]
        assert final_state.percent_completion == 1.0
        assert final_state.overall_diagnosis_context != ""


# ── FastAPI endpoint ───────────────────────────────────────────────────────────

class TestAPIEndpoint:
    @patch("orchestrator.main.threading.Thread")
    def test_register_returns_200(self, mock_thread):
        mock_thread.return_value = MagicMock()
        response = client.post("/register", json=VALID_PAYLOAD)
        assert response.status_code == 200

    @patch("orchestrator.main.threading.Thread")
    def test_register_returns_accepted_status(self, mock_thread):
        mock_thread.return_value = MagicMock()
        response = client.post("/register", json=VALID_PAYLOAD)
        assert response.json()["status"] == "accepted"

    @patch("orchestrator.main.threading.Thread")
    def test_register_echoes_image_id(self, mock_thread):
        mock_thread.return_value = MagicMock()
        response = client.post("/register", json=VALID_PAYLOAD)
        assert response.json()["image_id"] == TEST_ID

    @patch("orchestrator.main.threading.Thread")
    def test_register_starts_one_background_thread(self, mock_thread):
        mock_instance = MagicMock()
        mock_thread.return_value = mock_instance
        client.post("/register", json=VALID_PAYLOAD)
        mock_instance.start.assert_called_once()

    def test_register_with_missing_body_returns_422(self):
        response = client.post("/register", json={})
        assert response.status_code == 422

    def test_health_check(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


# ── DiagnosisState pydantic validation ────────────────────────────────────────

class TestDiagnosisStateValidation:
    """Ensure every stage produces a valid DiagnosisState that can round-trip
    through model_dump / model_validate without errors."""

    @pytest.mark.parametrize("stage_fn", TB_STAGES + PNEUMONIA_STAGES)
    def test_stage_serialises_cleanly(self, stage_fn):
        state = stage_fn(TEST_ID)
        dumped = state.model_dump(mode="json")
        # Must be a dict with the expected top-level keys
        assert "id" in dumped
        assert "image_id" in dumped
        assert "progress_tree" in dumped
        assert "percent_completion" in dumped
        assert "annotations" in dumped
        assert "overall_diagnosis_context" in dumped

    @pytest.mark.parametrize("stage_fn", TB_STAGES + PNEUMONIA_STAGES)
    def test_stage_round_trips_through_validate(self, stage_fn):
        state = stage_fn(TEST_ID)
        dumped = state.model_dump(mode="json")
        restored = DiagnosisState.model_validate(dumped)
        assert restored.id == state.id
        assert restored.percent_completion == state.percent_completion
