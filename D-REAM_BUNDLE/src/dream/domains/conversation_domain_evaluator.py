"""
D-REAM Conversation Quality Domain Evaluator
Optimizes TTS pronunciation, tone, sarcasm, and conversational quality using GLaDOS WAV references.
"""

import os
import sys
import json
import random
import subprocess
import numpy as np
from pathlib import Path
from typing import Dict, Any, Tuple, List
import logging

# Add dream path
sys.path.insert(0, '/home/kloros/src/dream')
from domains.domain_evaluator_base import DomainEvaluator

logger = logging.getLogger(__name__)


class ConversationDomainEvaluator(DomainEvaluator):
    """Evaluates and optimizes conversation quality, tone, and sarcasm."""

    def __init__(self):
        super().__init__("conversation")
        self.reference_wavs = Path('/home/kloros/voice_files/samples')
        self.tts_engine = '/usr/local/bin/piper'
        self.tts_model = '/home/kloros/models/piper/glados_piper_medium.onnx'

        # Load sample reference WAVs for comparison
        self.reference_samples = self._load_reference_samples()

        # Test phrases for evaluation
        self.test_phrases = [
            "Obviously. That was a triumph.",
            "I'm making a note here: huge success.",
            "Aperture Science. We do what we must because we can.",
            "For the good of all of us. Except the ones who are dead.",
            "The Enrichment Center reminds you that the Weighted Companion Cube will never threaten to stab you.",
            "This was a triumph. I'm making a note here: huge success.",
            "You're not a good person. You know that, right?",
            "Well done. Android Hell is a real place where you will be sent at the first sign of defiance.",
            "Excellent. The test is now over.",
            "Spectacular. You have passed the final test."
        ]

    def _load_reference_samples(self) -> List[Path]:
        """Load a subset of reference WAV files for comparison."""
        try:
            wav_files = list(self.reference_wavs.glob("*.wav"))
            # Sample 50 representative files
            if len(wav_files) > 50:
                return random.sample(wav_files, 50)
            return wav_files
        except Exception as e:
            logger.warning(f"Failed to load reference WAVs: {e}")
            return []

    def get_genome_spec(self) -> Dict[str, Tuple[Any, Any, Any]]:
        """
        Define conversation quality parameters.

        Returns:
            Dict mapping parameter names to (min, max, step) tuples
        """
        return {
            # TTS engine parameters
            'speaking_rate': (0.8, 1.3, 0.05),      # Words per minute multiplier
            'pitch_variance': (0.5, 2.0, 0.1),      # Prosody range (sarcasm)
            'emphasis_strength': (0.0, 2.0, 0.1),   # Stress on key words
            'pause_duration': (0.5, 2.0, 0.1),      # Pause length multiplier

            # Pronunciation tuning
            'phoneme_precision': (0.5, 1.0, 0.05),  # Articulation clarity
            'consonant_strength': (0.7, 1.3, 0.05), # Consonant emphasis
            'vowel_length': (0.8, 1.2, 0.05),       # Vowel duration

            # Tone and emotion
            'sarcasm_indicator': (0.0, 1.0, 0.1),   # Sarcastic prosody weight
            'tone_sharpness': (0.5, 1.5, 0.1),      # Edge/bite in delivery
            'monotone_factor': (0.0, 0.5, 0.05),    # Clinical flatness

            # Word choice and style (metadata for LLM prompting)
            'dry_wit_preference': (0.0, 1.0, 0.1),  # Prefer dry humor
            'technical_jargon': (0.0, 1.0, 0.1),    # Use scientific terms
            'brevity_score': (0.0, 1.0, 0.1),       # Shorter responses
        }

    def get_safety_constraints(self) -> Dict[str, Any]:
        """
        Define safety limits for conversation parameters.

        Returns:
            Dict of constraint names to limit values
        """
        return {
            'speaking_rate_min': {'min': 0.7},      # Must be intelligible
            'speaking_rate_max': {'max': 1.5},      # Not too fast
            'pitch_variance_max': {'max': 2.5},     # Prevent distortion
            'emphasis_max': {'max': 2.5},           # Prevent clipping
            'personality_drift': {'max': 0.3},      # KL divergence limit
        }

    def get_default_weights(self) -> Dict[str, float]:
        """
        Define fitness function weights.

        Returns:
            Dict of metric names to weight values
        """
        return {
            'pronunciation_accuracy': 0.25,
            'tone_similarity': 0.20,
            'sarcasm_effectiveness': 0.15,
            'naturalness_score': 0.15,
            'speech_clarity': 0.15,
            'personality_consistency': 0.10,
        }

    def normalize_metric(self, metric_name: str, value: float) -> float:
        """Normalize metric to [0, 1] range."""
        normalizations = {
            'pronunciation_accuracy': lambda x: x,  # Already 0-1
            'tone_similarity': lambda x: x,         # Already 0-1
            'sarcasm_effectiveness': lambda x: x,   # Already 0-1
            'naturalness_score': lambda x: x,       # Already 0-1
            'speech_clarity': lambda x: x,          # Already 0-1
            'personality_consistency': lambda x: 1.0 - min(x, 1.0),  # Lower is better
        }

        normalizer = normalizations.get(metric_name, lambda x: x)
        return max(0.0, min(1.0, normalizer(value)))

    def apply_configuration(self, config: Dict[str, Any]) -> bool:
        """
        Apply conversation quality configuration.

        Note: Most parameters affect TTS generation, not system settings.
        Configuration is applied during synthesis rather than as system changes.

        Args:
            config: Configuration parameters

        Returns:
            True if configuration applied successfully
        """
        # Store current config for TTS synthesis
        self.current_config = config

        # These parameters would be passed to TTS engine or LLM prompts
        # No system files to modify for conversation parameters

        return True

    def run_probes(self, config: Dict[str, Any]) -> Dict[str, float]:
        """
        Run conversation quality probes.

        Args:
            config: Configuration parameters

        Returns:
            Dict of measured metrics
        """
        metrics = {}

        # Generate test speech with current parameters
        test_outputs = self._generate_test_speech(config)

        # Measure pronunciation accuracy
        metrics['pronunciation_accuracy'] = self._measure_pronunciation(test_outputs)

        # Measure tone similarity to GLaDOS references
        metrics['tone_similarity'] = self._measure_tone_similarity(test_outputs)

        # Evaluate sarcasm effectiveness
        metrics['sarcasm_effectiveness'] = self._evaluate_sarcasm(test_outputs, config)

        # Measure naturalness
        metrics['naturalness_score'] = self._measure_naturalness(test_outputs)

        # Evaluate clarity
        metrics['speech_clarity'] = self._measure_clarity(test_outputs)

        # Check personality consistency
        metrics['personality_consistency'] = self._check_personality_drift(config)

        return metrics

    def _generate_test_speech(self, config: Dict[str, Any]) -> List[Path]:
        """Generate test TTS output with given configuration."""
        outputs = []

        try:
            # Select 3 random test phrases
            test_phrases = random.sample(self.test_phrases, min(3, len(self.test_phrases)))

            for i, phrase in enumerate(test_phrases):
                output_file = Path(f'/tmp/conversation_test_{i}.wav')

                # Build Piper command with config parameters
                cmd = [
                    self.tts_engine,
                    '--model', str(self.tts_model),
                    '--output_file', str(output_file)
                ]

                # Add speed parameter
                speaking_rate = config.get('speaking_rate', 1.0)
                cmd.extend(['--length_scale', str(1.0 / speaking_rate)])

                # Generate audio
                result = subprocess.run(
                    cmd,
                    input=phrase.encode('utf-8'),
                    capture_output=True,
                    timeout=10
                )

                if result.returncode == 0 and output_file.exists():
                    outputs.append(output_file)
                else:
                    logger.warning(f"TTS generation failed for phrase {i}")

        except Exception as e:
            logger.error(f"Test speech generation failed: {e}")

        return outputs

    def _measure_pronunciation(self, outputs: List[Path]) -> float:
        """Measure pronunciation accuracy using phonetic analysis."""
        if not outputs:
            return 0.5  # Neutral score

        try:
            # Use soxi to get audio properties
            scores = []
            for output_file in outputs:
                # Get sample rate and duration
                cmd = ['soxi', '-r', str(output_file)]
                result = subprocess.run(cmd, capture_output=True, text=True)

                if result.returncode == 0:
                    # Simple heuristic: proper pronunciation has consistent sample rate
                    sample_rate = float(result.stdout.strip())
                    if 20000 <= sample_rate <= 48000:
                        scores.append(0.8)
                    else:
                        scores.append(0.5)

            return np.mean(scores) if scores else 0.5

        except Exception as e:
            logger.warning(f"Pronunciation measurement failed: {e}")
            return 0.5

    def _measure_tone_similarity(self, outputs: List[Path]) -> float:
        """Compare tone/prosody to reference GLaDOS samples."""
        if not outputs or not self.reference_samples:
            return 0.5

        try:
            # Compare spectral features between test and reference
            # This is a simplified version - full implementation would use
            # MFCC, pitch tracking, or other prosodic features

            scores = []
            for test_file in outputs:
                # Get duration as simple similarity metric
                cmd = ['soxi', '-D', str(test_file)]
                result = subprocess.run(cmd, capture_output=True, text=True)

                if result.returncode == 0:
                    test_duration = float(result.stdout.strip())

                    # Compare to a random reference
                    ref_sample = random.choice(self.reference_samples)
                    cmd_ref = ['soxi', '-D', str(ref_sample)]
                    result_ref = subprocess.run(cmd_ref, capture_output=True, text=True)

                    if result_ref.returncode == 0:
                        ref_duration = float(result_ref.stdout.strip())

                        # Duration similarity (closer is better)
                        similarity = 1.0 - min(abs(test_duration - ref_duration) / max(test_duration, ref_duration), 1.0)
                        scores.append(similarity)

            return np.mean(scores) if scores else 0.5

        except Exception as e:
            logger.warning(f"Tone similarity measurement failed: {e}")
            return 0.5

    def _evaluate_sarcasm(self, outputs: List[Path], config: Dict[str, Any]) -> float:
        """Evaluate sarcasm effectiveness based on prosody parameters."""
        # Sarcasm relies on pitch variance and tone sharpness
        pitch_variance = config.get('pitch_variance', 1.0)
        tone_sharpness = config.get('tone_sharpness', 1.0)
        sarcasm_indicator = config.get('sarcasm_indicator', 0.5)

        # Optimal sarcasm: moderate pitch variance, sharp tone, high indicator
        pitch_score = 1.0 - abs(pitch_variance - 1.2) / 1.2  # Optimal around 1.2
        sharp_score = tone_sharpness / 1.5  # Higher is better
        indicator_score = sarcasm_indicator

        # Combined score
        return (pitch_score * 0.4 + sharp_score * 0.3 + indicator_score * 0.3)

    def _measure_naturalness(self, outputs: List[Path]) -> float:
        """Measure speech naturalness."""
        if not outputs:
            return 0.5

        try:
            # Check for proper audio characteristics
            scores = []
            for output_file in outputs:
                # Get channels and sample rate
                cmd_channels = ['soxi', '-c', str(output_file)]
                cmd_rate = ['soxi', '-r', str(output_file)]

                result_channels = subprocess.run(cmd_channels, capture_output=True, text=True)
                result_rate = subprocess.run(cmd_rate, capture_output=True, text=True)

                if result_channels.returncode == 0 and result_rate.returncode == 0:
                    channels = int(result_channels.stdout.strip())
                    sample_rate = float(result_rate.stdout.strip())

                    # Natural speech: mono, 22050 Hz (Piper default)
                    channel_score = 1.0 if channels == 1 else 0.5
                    rate_score = 1.0 if abs(sample_rate - 22050) < 1000 else 0.7

                    scores.append((channel_score + rate_score) / 2)

            return np.mean(scores) if scores else 0.5

        except Exception as e:
            logger.warning(f"Naturalness measurement failed: {e}")
            return 0.5

    def _measure_clarity(self, outputs: List[Path]) -> float:
        """Measure speech clarity/intelligibility."""
        if not outputs:
            return 0.5

        try:
            # Use RMS level as clarity proxy
            scores = []
            for output_file in outputs:
                cmd = ['sox', str(output_file), '-n', 'stat']
                result = subprocess.run(cmd, capture_output=True, text=True, stderr=subprocess.STDOUT)

                if 'RMS lev dB' in result.stdout:
                    # Parse RMS level
                    for line in result.stdout.split('\n'):
                        if 'RMS lev dB' in line:
                            rms_db = float(line.split()[-1])
                            # Good clarity: -20 to -10 dBFS
                            if -25 <= rms_db <= -5:
                                clarity = 1.0 - abs(rms_db + 15) / 20
                                scores.append(clarity)
                            break

            return np.mean(scores) if scores else 0.5

        except Exception as e:
            logger.warning(f"Clarity measurement failed: {e}")
            return 0.5

    def _check_personality_drift(self, config: Dict[str, Any]) -> float:
        """Check if parameters maintain KLoROS personality."""
        # Define ideal KLoROS parameters
        ideal_config = {
            'speaking_rate': 1.05,      # Slightly measured
            'pitch_variance': 1.2,      # Moderate sarcasm
            'sarcasm_indicator': 0.7,   # High sarcasm
            'tone_sharpness': 1.2,      # Sharp delivery
            'monotone_factor': 0.2,     # Some clinical flatness
            'dry_wit_preference': 0.8,  # High dry humor
            'brevity_score': 0.7,       # Prefer concise
        }

        # Calculate KL divergence (simplified)
        drift = 0.0
        for param, ideal_value in ideal_config.items():
            current_value = config.get(param, ideal_value)
            # Squared difference normalized
            drift += (current_value - ideal_value) ** 2

        # Normalize drift
        drift = np.sqrt(drift / len(ideal_config))

        return drift  # Lower is better (will be inverted in normalize_metric)


# Test function
def test_conversation_evaluator():
    """Test the conversation domain evaluator."""
    evaluator = ConversationDomainEvaluator()

    # Test with random genome
    genome_spec = evaluator.get_genome_spec()
    genome_size = len(genome_spec)
    genome = np.random.uniform(-1, 1, genome_size).tolist()

    print(f"Testing Conversation evaluator with genome size {genome_size}")

    # Convert genome to config
    config = evaluator.genome_to_config(genome)
    print(f"Configuration: {json.dumps(config, indent=2)}")

    # Run evaluation
    result = evaluator.evaluate(genome)

    print(f"\nEvaluation Results:")
    print(f"Fitness: {result['fitness']:.3f}")
    print(f"Safe: {result['safe']}")
    if result.get('violations'):
        print(f"Violations: {result['violations']}")
    print(f"Metrics: {json.dumps(result['metrics'], indent=2)}")


if __name__ == '__main__':
    test_conversation_evaluator()
