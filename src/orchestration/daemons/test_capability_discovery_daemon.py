#!/usr/bin/env python3

import ast
import hashlib
import pickle
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from src.orchestration.daemons.capability_discovery_daemon import CapabilityDiscoveryMonitorDaemon


class TestCapabilityPatternDetection(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.daemon = CapabilityDiscoveryMonitorDaemon(
            watch_path=Path(self.temp_dir),
            state_file=Path(self.temp_dir) / "test_state.pkl"
        )

    def test_detect_class_name_capability_indicators(self):
        test_code = '''
class DataAnalyzer:
    def analyze(self):
        pass

class PerformanceOptimizer:
    def optimize(self):
        pass

class RegularClass:
    def method(self):
        pass
'''
        test_file = Path(self.temp_dir) / "test_analyzers.py"
        test_file.write_text(test_code)

        capabilities = self.daemon._extract_capability_indicators(test_file)

        capability_terms = [c['term'] for c in capabilities]
        self.assertIn('analyzer', capability_terms)
        self.assertIn('optimizer', capability_terms)
        self.assertNotIn('regularclass', capability_terms)

    def test_detect_import_patterns(self):
        test_code = '''
from tools import MissingTool
from skills.analysis import NonExistentAnalyzer
import valid_module
'''
        test_file = Path(self.temp_dir) / "test_imports.py"
        test_file.write_text(test_code)

        capabilities = self.daemon._extract_capability_indicators(test_file)

        capability_terms = [c['term'] for c in capabilities]
        self.assertIn('missingtool', capability_terms)
        self.assertIn('nonexistentanalyzer', capability_terms)

    def test_detect_decorator_patterns(self):
        test_code = '''
@tool_capability
def process_data():
    pass

@skill("optimization")
def optimize():
    pass

@regular_decorator
def normal_function():
    pass
'''
        test_file = Path(self.temp_dir) / "test_decorators.py"
        test_file.write_text(test_code)

        capabilities = self.daemon._extract_capability_indicators(test_file)

        self.assertTrue(len(capabilities) > 0)

    def test_hash_based_change_detection(self):
        test_code = 'class TestClass:\n    pass\n'
        test_file = Path(self.temp_dir) / "test_hash.py"
        test_file.write_text(test_code)

        hash1 = self.daemon._compute_file_hash(test_file)
        self.assertTrue(len(hash1) == 64)

        changed1 = self.daemon._has_file_changed(test_file)
        self.assertTrue(changed1)

        changed2 = self.daemon._has_file_changed(test_file)
        self.assertFalse(changed2)

        test_file.write_text('class TestClass:\n    def new_method(self): pass\n')

        changed3 = self.daemon._has_file_changed(test_file)
        self.assertTrue(changed3)

    def test_skip_unchanged_files(self):
        test_file = Path(self.temp_dir) / "unchanged.py"
        test_file.write_text('class Test: pass')

        self.daemon._has_file_changed(test_file)

        with patch.object(self.daemon, '_extract_capability_indicators') as mock_extract:
            self.daemon.process_file_event('modify', test_file)
            mock_extract.assert_not_called()


class TestSemanticValidationIntegration(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.daemon = CapabilityDiscoveryMonitorDaemon(
            watch_path=Path(self.temp_dir),
            state_file=Path(self.temp_dir) / "test_state.pkl"
        )

    @patch('kloros.daemons.capability_discovery_daemon.ArchitecturalReasoner')
    def test_semantic_validation_filters_phantoms(self, mock_reasoner_class):
        mock_reasoner = Mock()
        mock_reasoner_class.return_value = mock_reasoner

        mock_analysis_phantom = Mock()
        mock_analysis_phantom.is_real_gap = False
        mock_analysis_phantom.pattern = 'DISTRIBUTED_PATTERN'
        mock_analysis_phantom.explanation = 'Distributed across multiple modules'
        mock_analysis_phantom.confidence = 0.05

        mock_analysis_real = Mock()
        mock_analysis_real.is_real_gap = True
        mock_analysis_real.pattern = 'PHANTOM'
        mock_analysis_real.explanation = 'Missing implementation'
        mock_analysis_real.confidence = 0.85

        mock_reasoner.analyze_gap_hypothesis.side_effect = [
            mock_analysis_phantom,
            mock_analysis_real
        ]

        daemon = CapabilityDiscoveryMonitorDaemon(
            watch_path=Path(self.temp_dir),
            state_file=Path(self.temp_dir) / "test_state.pkl"
        )

        indicators = [
            {'term': 'inference', 'type': 'class', 'evidence': ['InferenceEngine class']},
            {'term': 'missingtool', 'type': 'import', 'evidence': ['from tools import MissingTool']}
        ]

        validated = daemon._validate_capabilities_with_semantic_analysis(indicators)

        self.assertEqual(len(validated), 1)
        self.assertEqual(validated[0]['term'], 'missingtool')
        self.assertTrue(validated[0]['is_real_gap'])

    @patch('kloros.daemons.capability_discovery_daemon.ArchitecturalReasoner')
    def test_semantic_reasoner_integration(self, mock_reasoner_class):
        mock_reasoner = Mock()
        mock_reasoner_class.return_value = mock_reasoner

        mock_analysis = Mock()
        mock_analysis.is_real_gap = True
        mock_analysis.confidence = 0.75
        mock_reasoner.analyze_gap_hypothesis.return_value = mock_analysis

        daemon = CapabilityDiscoveryMonitorDaemon(
            watch_path=Path(self.temp_dir),
            state_file=Path(self.temp_dir) / "test_state.pkl"
        )

        self.assertIsNotNone(daemon.semantic_reasoner)

        indicators = [{'term': 'test_capability', 'type': 'class', 'evidence': ['TestClass']}]
        validated = daemon._validate_capabilities_with_semantic_analysis(indicators)

        mock_reasoner.analyze_gap_hypothesis.assert_called_once_with(term='test_capability', max_files=100)


class TestStatePersistence(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = Path(self.temp_dir) / "test_state.pkl"

    def test_save_and_load_state(self):
        daemon = CapabilityDiscoveryMonitorDaemon(
            watch_path=Path(self.temp_dir),
            state_file=self.state_file
        )

        test_file = Path(self.temp_dir) / "test.py"
        test_file.write_text('class Test: pass')

        daemon._has_file_changed(test_file)

        daemon.discovered_capabilities = {
            'analyzer': {
                'term': 'analyzer',
                'type': 'class',
                'evidence': ['DataAnalyzer class'],
                'first_seen': time.time()
            }
        }

        daemon.save_state()

        self.assertTrue(self.state_file.exists())

        new_daemon = CapabilityDiscoveryMonitorDaemon(
            watch_path=Path(self.temp_dir),
            state_file=self.state_file
        )

        self.assertEqual(len(new_daemon.file_hashes), 1)
        self.assertIn('analyzer', new_daemon.discovered_capabilities)

    def test_state_file_creation(self):
        state_dir = Path(self.temp_dir) / "nested" / "dir"
        state_file = state_dir / "state.pkl"

        daemon = CapabilityDiscoveryMonitorDaemon(
            watch_path=Path(self.temp_dir),
            state_file=state_file
        )

        daemon.save_state()

        self.assertTrue(state_file.exists())
        self.assertTrue(state_dir.exists())

    def test_graceful_missing_state(self):
        daemon = CapabilityDiscoveryMonitorDaemon(
            watch_path=Path(self.temp_dir),
            state_file=self.state_file
        )

        self.assertEqual(len(daemon.file_hashes), 0)
        self.assertEqual(len(daemon.discovered_capabilities), 0)


class TestUMNEmission(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    @patch('kloros.daemons.capability_discovery_daemon.UMNPub')
    def test_emit_capability_questions(self, mock_pub_class):
        mock_pub = Mock()
        mock_pub_class.return_value = mock_pub

        daemon = CapabilityDiscoveryMonitorDaemon(
            watch_path=Path(self.temp_dir),
            state_file=Path(self.temp_dir) / "test_state.pkl"
        )

        capabilities = [
            {
                'term': 'analyzer',
                'type': 'class',
                'evidence': ['DataAnalyzer class found'],
                'is_real_gap': True,
                'confidence': 0.75
            }
        ]

        daemon._emit_questions_to_umn(capabilities)

        mock_pub.emit.assert_called_once()
        call_args = mock_pub.emit.call_args
        self.assertEqual(call_args.kwargs['signal'], "curiosity.capability_question")
        self.assertEqual(call_args.kwargs['ecosystem'], "curiosity")

    @patch('kloros.daemons.capability_discovery_daemon.UMNPub')
    def test_umn_message_format(self, mock_pub_class):
        mock_pub = Mock()
        mock_pub_class.return_value = mock_pub

        daemon = CapabilityDiscoveryMonitorDaemon(
            watch_path=Path(self.temp_dir),
            state_file=Path(self.temp_dir) / "test_state.pkl"
        )

        capabilities = [
            {
                'term': 'optimizer',
                'type': 'import',
                'evidence': ['from tools import Optimizer'],
                'is_real_gap': True,
                'confidence': 0.85
            }
        ]

        daemon._emit_questions_to_umn(capabilities)

        # Verify emit was called with correct keyword arguments
        mock_pub.emit.assert_called_once()
        call_kwargs = mock_pub.emit.call_args.kwargs

        self.assertEqual(call_kwargs['signal'], "curiosity.capability_question")
        self.assertEqual(call_kwargs['ecosystem'], "curiosity")
        self.assertIn('facts', call_kwargs)

        facts = call_kwargs['facts']
        self.assertIn('question_id', facts)
        self.assertIn('hypothesis', facts)
        self.assertIn('question', facts)
        self.assertIn('evidence', facts)
        self.assertIn('severity', facts)
        self.assertIn('category', facts)

    @patch('kloros.daemons.capability_discovery_daemon.UMNPub', None)
    def test_graceful_no_umn(self):
        daemon = CapabilityDiscoveryMonitorDaemon(
            watch_path=Path(self.temp_dir),
            state_file=Path(self.temp_dir) / "test_state.pkl"
        )

        capabilities = [{'term': 'test', 'type': 'class', 'evidence': ['Test']}]

        # Should not raise exception when UMNPub is None
        daemon._emit_questions_to_umn(capabilities)


class TestMemoryBounds(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def test_capability_cache_bounded(self):
        daemon = CapabilityDiscoveryMonitorDaemon(
            watch_path=Path(self.temp_dir),
            state_file=Path(self.temp_dir) / "test_state.pkl",
            max_cache_size=10
        )

        for i in range(20):
            daemon.discovered_capabilities[f'capability_{i}'] = {
                'term': f'capability_{i}',
                'evidence': [f'evidence_{i}']
            }

        daemon._evict_capability_cache_if_needed()

        self.assertLessEqual(len(daemon.discovered_capabilities), 10)

    def test_file_hash_cache_bounded(self):
        daemon = CapabilityDiscoveryMonitorDaemon(
            watch_path=Path(self.temp_dir),
            state_file=Path(self.temp_dir) / "test_state.pkl",
            max_cache_size=5
        )

        for i in range(10):
            test_file = Path(self.temp_dir) / f"test_{i}.py"
            test_file.write_text(f'class Test{i}: pass')
            daemon._has_file_changed(test_file)

        daemon._evict_file_hash_cache_if_needed()

        self.assertLessEqual(len(daemon.file_hashes), 5)

    @patch('kloros.daemons.capability_discovery_daemon.ArchitecturalReasoner')
    def test_no_unbounded_data_structures(self, mock_reasoner_class):
        mock_reasoner = Mock()
        mock_reasoner_class.return_value = mock_reasoner

        daemon = CapabilityDiscoveryMonitorDaemon(
            watch_path=Path(self.temp_dir),
            state_file=Path(self.temp_dir) / "test_state.pkl",
            max_cache_size=100
        )

        for i in range(200):
            test_file = Path(self.temp_dir) / f"test_{i}.py"
            test_file.write_text(f'class Analyzer{i}: pass')

            daemon._has_file_changed(test_file)

        daemon._evict_file_hash_cache_if_needed()

        self.assertLessEqual(len(daemon.file_hashes), 100)


if __name__ == '__main__':
    unittest.main()
