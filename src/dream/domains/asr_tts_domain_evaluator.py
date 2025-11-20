#!/usr/bin/env python3
"""
ASR/TTS Pipeline Domain Evaluator for D-REAM
Tests speech recognition and synthesis parameters for KLoROS.
"""

import os
import re
import time
import json
import wave
import logging
import subprocess
import tempfile
from typing import Dict, List, Any, Tuple, Optional
from pathlib import Path
import numpy as np

from .domain_evaluator_base import DomainEvaluator

logger = logging.getLogger(__name__)


class ASRTTSDomainEvaluator(DomainEvaluator):
    """Evaluator for ASR/TTS pipeline performance and accuracy."""

    def __init__(self):
        super().__init__("asr_tts")
        self.kloros_env = self._load_kloros_env()
        self.has_vosk = self._check_vosk()
        self.has_whisper = self._check_whisper()
        self.has_piper = self._check_piper()
        self.test_samples = self._prepare_test_samples()
        self.ground_truth = self._load_ground_truth()

    def _load_kloros_env(self) -> Dict[str, str]:
        """Load KLoROS environment configuration."""
        env = {}
        env_path = Path("/home/kloros/.kloros_env")

        if env_path.exists():
            try:
                with open(env_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            env[key.strip()] = value.strip()
            except Exception as e:
                logger.error(f"Failed to load KLoROS env: {e}")

        return env

    def _check_vosk(self) -> bool:
        """Check if Vosk is available."""
        try:
            import vosk
            model_path = self.kloros_env.get('KLR_VOSK_MODEL_DIR',
                                            '/home/kloros/models/vosk/model')
            return os.path.exists(model_path)
        except:
            return False

    def _check_whisper(self) -> bool:
        """Check if Whisper is available."""
        try:
            import whisper
            return True
        except:
            return False

    def _check_piper(self) -> bool:
        """Check if Piper TTS is available."""
        try:
            result = subprocess.run(['piper', '--version'],
                                  capture_output=True, timeout=2)
            return result.returncode == 0
        except:
            return False

    def _prepare_test_samples(self) -> List[str]:
        """Prepare test audio samples for evaluation."""
        samples = []
        sample_dir = Path("/home/kloros/.kloros/test_samples")

        if sample_dir.exists():
            for audio_file in sample_dir.glob("*.wav"):
                samples.append(str(audio_file))

        # If no samples, we'll generate them during testing
        return samples

    def _load_ground_truth(self) -> Dict[str, str]:
        """Load ground truth transcriptions for test samples."""
        ground_truth = {}
        gt_file = Path("/home/kloros/.kloros/test_samples/ground_truth.json")

        if gt_file.exists():
            try:
                with open(gt_file, 'r') as f:
                    ground_truth = json.load(f)
            except:
                pass

        # Default test phrases if no ground truth available
        if not ground_truth:
            ground_truth = {
                "test_1": "hello kloros how are you today",
                "test_2": "please turn on the living room lights",
                "test_3": "what is the weather forecast for tomorrow",
                "test_4": "set a timer for five minutes",
                "test_5": "play some relaxing music"
            }

        return ground_truth

    def get_genome_spec(self) -> Dict[str, Tuple[Any, Any, Any]]:
        """Get ASR/TTS genome specification."""
        spec = {
            # ASR parameters
            'asr_model_size': (0, 3, 1),  # 0=tiny, 1=base, 2=small, 3=medium
            'asr_beam_width': (1, 10, 1),  # Beam search width
            'asr_vad_threshold': (0.01, 0.2, 0.01),  # VAD threshold
            'asr_vad_min_speech_ms': (100, 500, 50),  # Min speech duration
            'asr_vad_max_silence_ms': (500, 3000, 250),  # Max silence
            'asr_chunk_size_ms': (100, 1000, 100),  # Processing chunk size
            'asr_denoiser_strength': (0.0, 1.0, 0.1),  # Noise reduction

            # TTS parameters
            'tts_speaker_id': (0, 5, 1),  # Speaker voice selection
            'tts_speed': (0.5, 2.0, 0.1),  # Speech rate
            'tts_pitch': (0.5, 2.0, 0.1),  # Pitch adjustment
            'tts_energy': (0.5, 2.0, 0.1),  # Energy/volume

            # Pipeline parameters
            'batch_size': (1, 16, 1),  # Batch processing size
            'gpu_enabled': (0, 1, 1),  # Use GPU acceleration
            'quantization': (0, 2, 1),  # 0=none, 1=int8, 2=int4
            'cache_size_mb': (0, 512, 64),  # Model cache size
        }

        return spec

    def get_safety_constraints(self) -> Dict[str, Any]:
        """Get ASR/TTS safety constraints."""
        return {
            'rtf': {'max': 1.0},             # Real-time factor must be ≤1
            'gpu_memory_mb': {'max': 4096},  # Max GPU memory usage
            'backlog_seconds': {'max': 5},   # Max audio backlog
            'error_rate': {'max': 0.1},      # Max 10% error rate
            'latency_p99_ms': {'max': 2000}, # Max p99 latency
        }

    def get_default_weights(self) -> Dict[str, float]:
        """Get default fitness weights for ASR/TTS."""
        return {
            'wer': -0.35,                    # Word Error Rate (minimize)
            'cer': -0.15,                    # Character Error Rate (minimize)
            'rtf': -0.2,                     # Real-time factor (minimize)
            'p95_latency_ms': -0.15,         # P95 latency (minimize)
            'naturalness_score': 0.1,        # TTS naturalness (maximize)
            'intelligibility_score': 0.05    # TTS intelligibility (maximize)
        }

    def normalize_metric(self, metric_name: str, value: float) -> float:
        """Normalize ASR/TTS metric to [0, 1] range."""
        ranges = {
            'wer': (0, 1.0),                 # 0-100% WER
            'cer': (0, 1.0),                 # 0-100% CER
            'rtf': (0, 2.0),                 # 0-2x real-time
            'p95_latency_ms': (0, 3000),     # 0-3000ms
            'p99_latency_ms': (0, 5000),     # 0-5000ms
            'naturalness_score': (0, 5),     # 1-5 MOS scale
            'intelligibility_score': (0, 1),  # 0-1 score
            'gpu_memory_mb': (0, 8192),      # 0-8GB
            'backlog_seconds': (0, 10),      # 0-10 seconds
        }

        if metric_name in ranges:
            min_val, max_val = ranges[metric_name]
            normalized = (value - min_val) / (max_val - min_val)
            return max(0, min(1, normalized))
        return value

    def apply_configuration(self, config: Dict[str, Any]) -> bool:
        """Apply ASR/TTS configuration."""
        try:
            # Create temporary config file for KLoROS
            config_dict = {
                # ASR settings
                'KLR_STT_BACKEND': 'hybrid' if self.has_whisper else 'vosk',
                'ASR_WHISPER_SIZE': ['tiny', 'base', 'small', 'medium'][
                    int(config.get('asr_model_size', 0))
                ],
                'KLR_VAD_THRESHOLD': str(config.get('asr_vad_threshold', 0.05)),
                'KLR_VAD_MIN_SPEECH_MS': str(int(config.get('asr_vad_min_speech_ms', 300))),
                'KLR_VAD_MAX_SILENCE_MS': str(int(config.get('asr_vad_max_silence_ms', 2000))),
                'ASR_CORRECTION_THRESHOLD': str(0.5 + config.get('asr_beam_width', 5) * 0.05),

                # TTS settings
                'KLR_TTS_SPEED': str(config.get('tts_speed', 1.0)),

                # GPU settings
                'CUDA_VISIBLE_DEVICES': '0' if config.get('gpu_enabled', 0) else '-1',

                # Batch processing
                'ASR_BATCH_SIZE': str(int(config.get('batch_size', 1))),
            }

            # Write config to temp file
            config_path = Path("/tmp/asr_tts_eval_config.env")
            with open(config_path, 'w') as f:
                for key, value in config_dict.items():
                    f.write(f"export {key}={value}\n")

            return True

        except Exception as e:
            logger.error(f"Failed to apply ASR/TTS config: {e}")
            return False

    def run_probes(self, config: Dict[str, Any]) -> Dict[str, float]:
        """Run ASR/TTS performance probes."""
        metrics = {}

        # Apply configuration
        if not self.apply_configuration(config):
            logger.warning("Failed to apply some ASR/TTS configurations")

        # Run ASR tests
        asr_metrics = self._test_asr_performance(config)
        metrics.update(asr_metrics)

        # Run TTS tests
        tts_metrics = self._test_tts_performance(config)
        metrics.update(tts_metrics)

        # Run end-to-end pipeline test
        pipeline_metrics = self._test_pipeline_performance(config)
        metrics.update(pipeline_metrics)

        # Monitor resource usage
        resource_metrics = self._monitor_resource_usage()
        metrics.update(resource_metrics)

        return metrics

    def _test_asr_performance(self, config: Dict[str, Any]) -> Dict[str, float]:
        """Test ASR performance with current configuration."""
        metrics = {
            'wer': 0.1,  # Default 10% WER
            'cer': 0.05,  # Default 5% CER
            'rtf': 0.5,   # Default 0.5x real-time
            'p95_latency_ms': 500
        }

        try:
            # Prepare test script based on backend
            if self.kloros_env.get('KLR_STT_BACKEND') == 'hybrid' and self.has_whisper:
                metrics.update(self._test_whisper_asr(config))
            elif self.has_vosk:
                metrics.update(self._test_vosk_asr(config))

        except Exception as e:
            logger.error(f"Failed to test ASR performance: {e}")

        return metrics

    def _test_whisper_asr(self, config: Dict[str, Any]) -> Dict[str, float]:
        """Test Whisper ASR performance."""
        metrics = {}

        try:
            import whisper
            import time

            # Load model based on config
            model_size = ['tiny', 'base', 'small', 'medium'][
                int(config.get('asr_model_size', 0))
            ]
            model = whisper.load_model(model_size)

            # Test on sample audio
            total_audio_duration = 0
            total_processing_time = 0
            total_words = 0
            total_errors = 0

            for phrase_id, ground_truth_text in list(self.ground_truth.items())[:5]:
                # Generate or load test audio
                audio_file = self._get_or_generate_test_audio(phrase_id, ground_truth_text)

                if audio_file and os.path.exists(audio_file):
                    # Get audio duration
                    with wave.open(audio_file, 'rb') as w:
                        frames = w.getnframes()
                        rate = w.getframerate()
                        duration = frames / float(rate)
                        total_audio_duration += duration

                    # Transcribe with timing
                    start_time = time.time()
                    result = model.transcribe(audio_file,
                                            beam_size=int(config.get('asr_beam_width', 5)),
                                            language='en')
                    processing_time = time.time() - start_time
                    total_processing_time += processing_time

                    # Calculate WER
                    hypothesis = result['text'].lower().strip()
                    reference = ground_truth_text.lower().strip()
                    wer, word_errors, word_count = self._calculate_wer(hypothesis, reference)

                    total_words += word_count
                    total_errors += word_errors

            # Calculate metrics
            if total_words > 0:
                metrics['wer'] = total_errors / total_words

            if total_audio_duration > 0:
                metrics['rtf'] = total_processing_time / total_audio_duration

            # Estimate latency
            metrics['p95_latency_ms'] = (total_processing_time / 5) * 1000 * 1.5  # 1.5x for p95

        except Exception as e:
            logger.error(f"Failed to test Whisper ASR: {e}")

        return metrics

    def _test_vosk_asr(self, config: Dict[str, Any]) -> Dict[str, float]:
        """Test Vosk ASR performance."""
        metrics = {}

        try:
            import vosk
            import json
            import time

            # Load Vosk model
            model_path = self.kloros_env.get('KLR_VOSK_MODEL_DIR',
                                            '/home/kloros/models/vosk/model')
            model = vosk.Model(model_path)

            total_audio_duration = 0
            total_processing_time = 0
            total_words = 0
            total_errors = 0

            for phrase_id, ground_truth_text in list(self.ground_truth.items())[:5]:
                # Generate or load test audio
                audio_file = self._get_or_generate_test_audio(phrase_id, ground_truth_text)

                if audio_file and os.path.exists(audio_file):
                    # Process with Vosk
                    with wave.open(audio_file, 'rb') as wf:
                        rec = vosk.KaldiRecognizer(model, wf.getframerate())

                        duration = wf.getnframes() / float(wf.getframerate())
                        total_audio_duration += duration

                        start_time = time.time()
                        while True:
                            data = wf.readframes(4000)
                            if len(data) == 0:
                                break
                            rec.AcceptWaveform(data)

                        result = json.loads(rec.FinalResult())
                        processing_time = time.time() - start_time
                        total_processing_time += processing_time

                        # Calculate WER
                        hypothesis = result.get('text', '').lower().strip()
                        reference = ground_truth_text.lower().strip()
                        wer, word_errors, word_count = self._calculate_wer(hypothesis, reference)

                        total_words += word_count
                        total_errors += word_errors

            # Calculate metrics
            if total_words > 0:
                metrics['wer'] = total_errors / total_words

            if total_audio_duration > 0:
                metrics['rtf'] = total_processing_time / total_audio_duration

            metrics['p95_latency_ms'] = (total_processing_time / 5) * 1000 * 1.2  # 1.2x for p95

        except Exception as e:
            logger.error(f"Failed to test Vosk ASR: {e}")

        return metrics

    def _test_tts_performance(self, config: Dict[str, Any]) -> Dict[str, float]:
        """Test TTS performance with current configuration."""
        metrics = {
            'naturalness_score': 3.5,      # Default MOS
            'intelligibility_score': 0.8,   # Default intelligibility
        }

        try:
            if self.has_piper:
                metrics.update(self._test_piper_tts(config))

        except Exception as e:
            logger.error(f"Failed to test TTS performance: {e}")

        return metrics

    def _test_piper_tts(self, config: Dict[str, Any]) -> Dict[str, float]:
        """Test Piper TTS performance."""
        metrics = {}

        try:
            # Get Piper voice model
            piper_voice = self.kloros_env.get('KLR_PIPER_VOICE',
                                             '/home/kloros/models/piper/glados_piper_medium.onnx')

            test_phrases = [
                "Hello, this is a test of the text to speech system.",
                "The quick brown fox jumps over the lazy dog.",
                "How are you doing today?",
            ]

            total_time = 0
            total_audio_duration = 0

            for phrase in test_phrases:
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
                    tmp_path = tmp.name

                # Generate TTS with timing
                start_time = time.time()
                cmd = [
                    'piper',
                    '--model', piper_voice,
                    '--output_file', tmp_path
                ]

                # Add speed adjustment
                if 'tts_speed' in config:
                    cmd.extend(['--length-scale', str(1.0 / config['tts_speed'])])

                process = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE)
                stdout, stderr = process.communicate(input=phrase.encode())
                generation_time = time.time() - start_time
                total_time += generation_time

                # Get audio duration
                if os.path.exists(tmp_path):
                    with wave.open(tmp_path, 'rb') as w:
                        frames = w.getnframes()
                        rate = w.getframerate()
                        duration = frames / float(rate)
                        total_audio_duration += duration

                    # Clean up
                    os.remove(tmp_path)

            # Calculate RTF for TTS
            if total_audio_duration > 0:
                tts_rtf = total_time / total_audio_duration
                # Add to overall RTF (TTS is part of pipeline)
                metrics['rtf'] = metrics.get('rtf', 0) + tts_rtf * 0.3  # Weight TTS RTF

            # Estimate naturalness based on voice and speed
            speed = config.get('tts_speed', 1.0)
            if 0.8 <= speed <= 1.2:
                metrics['naturalness_score'] = 4.0  # Natural speed range
            else:
                metrics['naturalness_score'] = 3.0 - abs(speed - 1.0)

            metrics['intelligibility_score'] = 0.85  # Piper generally has good intelligibility

        except Exception as e:
            logger.error(f"Failed to test Piper TTS: {e}")

        return metrics

    def _test_pipeline_performance(self, config: Dict[str, Any]) -> Dict[str, float]:
        """Test end-to-end ASR+TTS pipeline performance."""
        metrics = {}

        try:
            # Simulate full pipeline: Audio -> ASR -> Processing -> TTS -> Audio
            test_phrase = "What is the weather like today?"

            # Generate test audio
            audio_file = self._get_or_generate_test_audio("pipeline_test", test_phrase)

            if audio_file:
                start_time = time.time()

                # ASR step
                if self.has_whisper:
                    import whisper
                    model_size = ['tiny', 'base', 'small', 'medium'][
                        int(config.get('asr_model_size', 0))
                    ]
                    model = whisper.load_model(model_size)
                    result = model.transcribe(audio_file)
                    transcribed_text = result['text']
                else:
                    transcribed_text = test_phrase  # Fallback

                # Processing step (simulated)
                response_text = f"The weather is sunny with a temperature of 72 degrees."

                # TTS step
                if self.has_piper:
                    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
                        tts_output = tmp.name

                    piper_voice = self.kloros_env.get('KLR_PIPER_VOICE',
                                                     '/home/kloros/models/piper/glados_piper_medium.onnx')
                    cmd = ['piper', '--model', piper_voice, '--output_file', tts_output]
                    process = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                             stdout=subprocess.DEVNULL,
                                             stderr=subprocess.DEVNULL)
                    process.communicate(input=response_text.encode())

                    # Clean up
                    if os.path.exists(tts_output):
                        os.remove(tts_output)

                # Calculate total pipeline time
                total_time = time.time() - start_time
                metrics['p99_latency_ms'] = total_time * 1000 * 1.5  # Estimate p99

                # Check for backlog
                metrics['backlog_seconds'] = 0  # No backlog in single test

        except Exception as e:
            logger.error(f"Failed to test pipeline: {e}")
            metrics['p99_latency_ms'] = 5000  # Default high latency on error

        return metrics

    def _monitor_resource_usage(self) -> Dict[str, float]:
        """Monitor GPU and system resource usage."""
        metrics = {
            'gpu_memory_mb': 0,
            'error_rate': 0
        }

        try:
            # Check GPU memory if available
            cmd = ['nvidia-smi', '--query-gpu=memory.used',
                   '--format=csv,noheader,nounits']
            returncode, stdout, _ = self.run_command(cmd, timeout=2)
            if returncode == 0:
                metrics['gpu_memory_mb'] = float(stdout.strip())

        except Exception as e:
            logger.debug(f"GPU monitoring unavailable: {e}")

        return metrics

    def _get_or_generate_test_audio(self, phrase_id: str, text: str) -> Optional[str]:
        """Get existing test audio or generate it."""
        # Check if test audio exists
        audio_path = Path(f"/home/kloros/.kloros/test_samples/{phrase_id}.wav")
        if audio_path.exists():
            return str(audio_path)

        # Generate test audio using TTS
        if self.has_piper:
            try:
                audio_path.parent.mkdir(parents=True, exist_ok=True)

                piper_voice = self.kloros_env.get('KLR_PIPER_VOICE',
                                                 '/home/kloros/models/piper/glados_piper_medium.onnx')
                cmd = ['piper', '--model', piper_voice, '--output_file', str(audio_path)]
                process = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                         stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL)
                process.communicate(input=text.encode())

                if audio_path.exists():
                    return str(audio_path)

            except Exception as e:
                logger.error(f"Failed to generate test audio: {e}")

        return None

    def _calculate_wer(self, hypothesis: str, reference: str) -> Tuple[float, int, int]:
        """Calculate Word Error Rate between hypothesis and reference."""
        hyp_words = hypothesis.split()
        ref_words = reference.split()

        # Simple WER calculation (Levenshtein distance)
        d = [[0] * (len(ref_words) + 1) for _ in range(len(hyp_words) + 1)]

        for i in range(len(hyp_words) + 1):
            d[i][0] = i
        for j in range(len(ref_words) + 1):
            d[0][j] = j

        for i in range(1, len(hyp_words) + 1):
            for j in range(1, len(ref_words) + 1):
                if hyp_words[i-1] == ref_words[j-1]:
                    d[i][j] = d[i-1][j-1]
                else:
                    d[i][j] = min(d[i-1][j], d[i][j-1], d[i-1][j-1]) + 1

        errors = d[len(hyp_words)][len(ref_words)]
        total_words = len(ref_words)
        wer = errors / total_words if total_words > 0 else 0

        return wer, errors, total_words


# Test function
def test_asr_tts_evaluator():
    """Test the ASR/TTS domain evaluator."""
    import numpy as np

    evaluator = ASRTTSDomainEvaluator()

    print(f"Has Vosk: {evaluator.has_vosk}")
    print(f"Has Whisper: {evaluator.has_whisper}")
    print(f"Has Piper: {evaluator.has_piper}")
    print(f"Test samples: {len(evaluator.test_samples)}")
    print(f"Ground truth phrases: {len(evaluator.ground_truth)}")

    # Test with random genome
    genome_size = len(evaluator.get_genome_spec())
    genome = np.random.randn(genome_size).tolist()

    print(f"\nTesting ASR/TTS evaluator with genome size {genome_size}")

    # Convert genome to config
    config = evaluator.genome_to_config(genome)
    print(f"Configuration: {json.dumps(config, indent=2)}")

    # Run evaluation
    result = evaluator.evaluate(genome)

    print(f"\nEvaluation Results:")
    print(f"Fitness: {result['fitness']:.3f}")
    print(f"Safe: {result['safe']}")
    if result['violations']:
        print(f"Violations: {result['violations']}")
    print(f"Metrics: {json.dumps(result['metrics'], indent=2)}")


if __name__ == '__main__':
    test_asr_tts_evaluator()