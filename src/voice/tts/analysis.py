"""
TTS Output Analysis System for KLoROS.

Passive analysis of generated TTS WAV files to drive quality improvements
and optimize speech synthesis parameters.
"""

import os
import wave
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import json


class TTSAnalyzer:
    """Analyzes TTS output files for quality metrics and improvement insights."""

    def __init__(self):
        """Initialize the TTS analyzer with configuration from environment."""
        # Configuration
        self.tts_output_dir = Path(os.getenv("KLR_TTS_OUTPUT_DIR", "/home/kloros/.kloros/out"))
        self.analysis_window_hours = int(os.getenv("KLR_TTS_ANALYSIS_WINDOW_HOURS", "24"))
        self.min_analysis_files = int(os.getenv("KLR_TTS_MIN_ANALYSIS_FILES", "5"))
        # Load adaptive thresholds with data source tracking
        self.quality_threshold = self._get_adaptive_threshold("quality", 0.7)
        self._parameter_source = "adaptive"  # Track how parameters were derived

        # Analysis cache
        self._analysis_cache = {}
        self._cache_expiry = {}

    def analyze_recent_tts_outputs(self) -> Dict[str, Any]:
        """
        Analyze recent TTS outputs for quality and improvement opportunities.

        Returns:
            Dictionary with comprehensive analysis results
        """
        results = {
            "analysis_timestamp": datetime.now().isoformat(),
            "files_analyzed": 0,
            "quality_metrics": {},
            "improvement_insights": [],
            "trend_analysis": {},
            "recommendations": [],
            "errors": []
        }

        try:
            # Get recent TTS files
            recent_files = self._get_recent_tts_files()

            if len(recent_files) < self.min_analysis_files:
                results["errors"].append(f"Insufficient files for analysis ({len(recent_files)} < {self.min_analysis_files})")
                return results

            results["files_analyzed"] = len(recent_files)

            # Analyze each file
            file_analyses = []
            for file_path in recent_files:
                try:
                    analysis = self._analyze_wav_file(file_path)
                    if analysis:
                        file_analyses.append(analysis)
                except Exception as e:
                    results["errors"].append(f"Failed to analyze {file_path.name}: {e}")

            if not file_analyses:
                results["errors"].append("No files could be analyzed successfully")
                return results

            # Aggregate quality metrics
            results["quality_metrics"] = self._aggregate_quality_metrics(file_analyses)

            # Trend analysis
            results["trend_analysis"] = self._analyze_quality_trends(file_analyses)

            # Generate improvement insights
            results["improvement_insights"] = self._generate_improvement_insights(
                results["quality_metrics"],
                results["trend_analysis"]
            )

            # Generate recommendations
            results["recommendations"] = self._generate_recommendations(
                results["quality_metrics"],
                results["improvement_insights"]
            )

        except Exception as e:
            results["errors"].append(f"Analysis system error: {e}")

        return results

    def _get_recent_tts_files(self) -> List[Path]:
        """Get TTS files from the analysis window."""
        if not self.tts_output_dir.exists():
            return []

        cutoff_time = datetime.now() - timedelta(hours=self.analysis_window_hours)
        cutoff_timestamp = cutoff_time.timestamp()

        tts_files = []
        for file_path in self.tts_output_dir.glob("tts_*.wav"):
            if file_path.stat().st_mtime >= cutoff_timestamp:
                tts_files.append(file_path)

        # Sort by modification time (newest first)
        tts_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        return tts_files

    def _analyze_wav_file(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """
        Analyze a single WAV file for quality metrics.

        Args:
            file_path: Path to WAV file

        Returns:
            Dictionary with analysis results
        """
        # Check cache first
        cache_key = str(file_path)
        if (cache_key in self._analysis_cache and
            cache_key in self._cache_expiry and
            datetime.now().timestamp() < self._cache_expiry[cache_key]):
            return self._analysis_cache[cache_key]

        try:
            # Read WAV file
            with wave.open(str(file_path), 'rb') as wav_file:
                frames = wav_file.readframes(-1)
                sample_rate = wav_file.getframerate()
                num_channels = wav_file.getnchannels()
                sample_width = wav_file.getsampwidth()
                duration = len(frames) / (sample_rate * num_channels * sample_width)

            # Convert to numpy array
            if sample_width == 2:
                audio_data = np.frombuffer(frames, dtype=np.int16)
            elif sample_width == 4:
                audio_data = np.frombuffer(frames, dtype=np.int32)
            else:
                return None

            # Convert to float and normalize
            audio_float = audio_data.astype(np.float32)
            if sample_width == 2:
                audio_float /= 32768.0
            elif sample_width == 4:
                audio_float /= 2147483648.0

            # Handle multi-channel audio
            if num_channels > 1:
                audio_float = audio_float.reshape(-1, num_channels)
                audio_float = np.mean(audio_float, axis=1)  # Convert to mono

            # Perform analysis
            analysis = {
                "file_path": str(file_path),
                "file_size_bytes": file_path.stat().st_size,
                "duration_seconds": duration,
                "sample_rate": sample_rate,
                "channels": num_channels,
                "sample_width": sample_width,
                "modification_time": file_path.stat().st_mtime,

                # Audio quality metrics
                "rms_level": float(np.sqrt(np.mean(audio_float ** 2))),
                "peak_level": float(np.max(np.abs(audio_float))),
                "dynamic_range": self._calculate_dynamic_range(audio_float),
                "signal_to_noise_ratio": self._estimate_snr(audio_float),
                "spectral_centroid": self._calculate_spectral_centroid(audio_float, sample_rate),
                "zero_crossing_rate": self._calculate_zero_crossing_rate(audio_float),

                # Speech quality metrics
                "speech_clarity": self._estimate_speech_clarity(audio_float, sample_rate),
                "prosody_score": self._analyze_prosody(audio_float, sample_rate),
                "naturalness_score": self._estimate_naturalness(audio_float, sample_rate),

                # Technical metrics
                "clipping_detected": self._detect_clipping(audio_float),
                "silence_ratio": self._calculate_silence_ratio(audio_float),
                "frequency_balance": self._analyze_frequency_balance(audio_float, sample_rate)
            }

            # Calculate overall quality score
            analysis["overall_quality"] = self._calculate_overall_quality(analysis)

            # Cache the analysis
            self._analysis_cache[cache_key] = analysis
            self._cache_expiry[cache_key] = datetime.now().timestamp() + 3600  # 1 hour cache

            return analysis

        except Exception as e:
            print(f"[tts_analysis] Error analyzing {file_path}: {e}")
            return None

    def _calculate_dynamic_range(self, audio: np.ndarray) -> float:
        """Calculate dynamic range of audio signal."""
        if len(audio) == 0:
            return 0.0

        # Calculate RMS in sliding windows
        window_size = len(audio) // 20  # 20 windows
        if window_size < 100:
            return float(np.max(audio) - np.min(audio))

        rms_values = []
        for i in range(0, len(audio) - window_size, window_size):
            window = audio[i:i + window_size]
            rms_values.append(np.sqrt(np.mean(window ** 2)))

        if not rms_values:
            return 0.0

        return float(np.max(rms_values) - np.min(rms_values))

    def _estimate_snr(self, audio: np.ndarray) -> float:
        """Estimate signal-to-noise ratio."""
        if len(audio) == 0:
            return 0.0

        # Use simple energy-based estimation
        signal_power = np.mean(audio ** 2)

        # Estimate noise from quieter segments (bottom 10% of energy)
        window_size = len(audio) // 50
        if window_size < 100:
            return 20.0  # Default reasonable value

        energies = []
        for i in range(0, len(audio) - window_size, window_size):
            window = audio[i:i + window_size]
            energies.append(np.mean(window ** 2))

        if not energies:
            return 20.0

        noise_power = np.percentile(energies, 10)

        if noise_power <= 0:
            return 40.0  # High SNR

        snr = 10 * np.log10(signal_power / noise_power)
        return float(np.clip(snr, 0, 60))  # Reasonable range

    def _calculate_spectral_centroid(self, audio: np.ndarray, sample_rate: int) -> float:
        """Calculate spectral centroid (brightness measure)."""
        if len(audio) < 1024:
            return sample_rate / 4  # Default mid-frequency

        # Simple FFT-based calculation
        fft = np.fft.rfft(audio)
        magnitude = np.abs(fft)
        freqs = np.fft.rfftfreq(len(audio), 1/sample_rate)

        if np.sum(magnitude) == 0:
            return sample_rate / 4

        centroid = np.sum(freqs * magnitude) / np.sum(magnitude)
        return float(centroid)

    def _calculate_zero_crossing_rate(self, audio: np.ndarray) -> float:
        """Calculate zero crossing rate (measure of noise/fricatives)."""
        if len(audio) < 2:
            return 0.0

        zero_crossings = np.sum(np.diff(np.sign(audio)) != 0)
        zcr = zero_crossings / len(audio)
        return float(zcr)

    def _estimate_speech_clarity(self, audio: np.ndarray, sample_rate: int) -> float:
        """Estimate speech clarity based on spectral features."""
        if len(audio) < 1024:
            return 0.5

        # Simple clarity estimation based on spectral characteristics
        fft = np.fft.rfft(audio)
        magnitude = np.abs(fft)
        freqs = np.fft.rfftfreq(len(audio), 1/sample_rate)

        # Speech clarity often correlates with energy in 1-4kHz range
        speech_band = (freqs >= 1000) & (freqs <= 4000)
        if np.sum(speech_band) == 0:
            return 0.5

        speech_energy = np.sum(magnitude[speech_band])
        total_energy = np.sum(magnitude)

        if total_energy == 0:
            return 0.5

        clarity = speech_energy / total_energy
        return float(np.clip(clarity, 0, 1))

    def _analyze_prosody(self, audio: np.ndarray, sample_rate: int) -> float:
        """Analyze prosodic features (rhythm, stress patterns)."""
        if len(audio) < sample_rate:  # Need at least 1 second
            return 0.5

        # Simple prosody analysis based on amplitude variations
        window_size = sample_rate // 10  # 100ms windows
        amplitudes = []

        for i in range(0, len(audio) - window_size, window_size):
            window = audio[i:i + window_size]
            amplitudes.append(np.sqrt(np.mean(window ** 2)))

        if len(amplitudes) < 2:
            return 0.5

        # Good prosody has appropriate variation (not too flat, not too chaotic)
        amplitude_var = np.var(amplitudes)
        prosody_score = 1.0 - abs(amplitude_var - 0.1) / 0.1  # Target variance around 0.1
        return float(np.clip(prosody_score, 0, 1))

    def _estimate_naturalness(self, audio: np.ndarray, sample_rate: int) -> float:
        """Estimate naturalness of synthesized speech."""
        if len(audio) < 1024:
            return 0.5

        # Combine multiple factors for naturalness estimation
        spectral_centroid = self._calculate_spectral_centroid(audio, sample_rate)
        zcr = self._calculate_zero_crossing_rate(audio)

        # Natural speech typically has centroid in 1-3kHz range
        centroid_naturalness = 1.0 - abs(spectral_centroid - 2000) / 2000
        centroid_naturalness = np.clip(centroid_naturalness, 0, 1)

        # Natural ZCR is moderate (not too high, not too low)
        zcr_naturalness = 1.0 - abs(zcr - 0.1) / 0.1
        zcr_naturalness = np.clip(zcr_naturalness, 0, 1)

        # Combine factors
        naturalness = (centroid_naturalness + zcr_naturalness) / 2
        return float(naturalness)

    def _detect_clipping(self, audio: np.ndarray) -> bool:
        """Detect audio clipping."""
        if len(audio) == 0:
            return False

        # Check for samples at or near maximum amplitude
        max_amplitude = np.max(np.abs(audio))
        clipping_threshold = 0.98  # 98% of full scale

        clipped_samples = np.sum(np.abs(audio) >= clipping_threshold)
        clipping_ratio = clipped_samples / len(audio)

        return clipping_ratio > 0.001  # More than 0.1% clipped samples

    def _calculate_silence_ratio(self, audio: np.ndarray) -> float:
        """Calculate ratio of silence in audio."""
        if len(audio) == 0:
            return 1.0

        # Silence threshold
        rms = np.sqrt(np.mean(audio ** 2))
        silence_threshold = rms * 0.1  # 10% of RMS as silence threshold

        silent_samples = np.sum(np.abs(audio) < silence_threshold)
        return float(silent_samples / len(audio))

    def _analyze_frequency_balance(self, audio: np.ndarray, sample_rate: int) -> Dict[str, float]:
        """Analyze frequency balance across different bands."""
        if len(audio) < 1024:
            return {"low": 0.33, "mid": 0.33, "high": 0.34}

        fft = np.fft.rfft(audio)
        magnitude = np.abs(fft)
        freqs = np.fft.rfftfreq(len(audio), 1/sample_rate)

        # Define frequency bands
        low_band = freqs <= 800
        mid_band = (freqs > 800) & (freqs <= 4000)
        high_band = freqs > 4000

        total_energy = np.sum(magnitude)
        if total_energy == 0:
            return {"low": 0.33, "mid": 0.33, "high": 0.34}

        low_energy = np.sum(magnitude[low_band]) / total_energy
        mid_energy = np.sum(magnitude[mid_band]) / total_energy
        high_energy = np.sum(magnitude[high_band]) / total_energy

        return {
            "low": float(low_energy),
            "mid": float(mid_energy),
            "high": float(high_energy)
        }

    def _calculate_overall_quality(self, analysis: Dict[str, Any]) -> float:
        """Calculate overall quality score from individual metrics."""
        # Weight different factors
        weights = {
            "speech_clarity": 0.25,
            "naturalness_score": 0.25,
            "prosody_score": 0.20,
            "signal_to_noise_ratio": 0.15,
            "dynamic_range": 0.10,
            "clipping_penalty": 0.05
        }

        score = 0.0

        # Speech clarity (0-1)
        score += weights["speech_clarity"] * analysis.get("speech_clarity", 0.5)

        # Naturalness (0-1)
        score += weights["naturalness_score"] * analysis.get("naturalness_score", 0.5)

        # Prosody (0-1)
        score += weights["prosody_score"] * analysis.get("prosody_score", 0.5)

        # SNR (normalize 0-40 dB to 0-1)
        snr_normalized = np.clip(analysis.get("signal_to_noise_ratio", 20) / 40, 0, 1)
        score += weights["signal_to_noise_ratio"] * snr_normalized

        # Dynamic range (normalize to 0-1)
        dr_normalized = np.clip(analysis.get("dynamic_range", 0.2) / 0.5, 0, 1)
        score += weights["dynamic_range"] * dr_normalized

        # Clipping penalty
        if not analysis.get("clipping_detected", False):
            score += weights["clipping_penalty"]

        return float(np.clip(score, 0, 1))

    def _aggregate_quality_metrics(self, file_analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate quality metrics across all analyzed files."""
        if not file_analyses:
            return {}

        metrics = {}

        # Calculate averages for numeric metrics
        numeric_metrics = [
            "overall_quality", "speech_clarity", "naturalness_score", "prosody_score",
            "signal_to_noise_ratio", "dynamic_range", "rms_level", "peak_level",
            "spectral_centroid", "zero_crossing_rate", "silence_ratio"
        ]

        for metric in numeric_metrics:
            values = [analysis.get(metric, 0) for analysis in file_analyses]
            metrics[f"{metric}_mean"] = float(np.mean(values))
            metrics[f"{metric}_std"] = float(np.std(values))
            metrics[f"{metric}_min"] = float(np.min(values))
            metrics[f"{metric}_max"] = float(np.max(values))

        # Count boolean metrics
        clipping_count = sum(1 for analysis in file_analyses if analysis.get("clipping_detected", False))
        metrics["clipping_rate"] = clipping_count / len(file_analyses)

        # Frequency balance average
        freq_balances = [analysis.get("frequency_balance", {}) for analysis in file_analyses]
        if freq_balances and freq_balances[0]:
            for band in ["low", "mid", "high"]:
                values = [fb.get(band, 0) for fb in freq_balances if fb]
                if values:
                    metrics[f"freq_balance_{band}_mean"] = float(np.mean(values))

        return metrics

    def _analyze_quality_trends(self, file_analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze quality trends over time."""
        if len(file_analyses) < 3:
            return {"trend": "insufficient_data"}

        # Sort by modification time
        sorted_analyses = sorted(file_analyses, key=lambda x: x.get("modification_time", 0))

        # Extract quality scores over time
        quality_scores = [analysis.get("overall_quality", 0.5) for analysis in sorted_analyses]

        # Simple trend analysis
        if len(quality_scores) >= 3:
            recent_avg = np.mean(quality_scores[-3:])
            earlier_avg = np.mean(quality_scores[:-3]) if len(quality_scores) > 3 else quality_scores[0]

            if recent_avg > earlier_avg + 0.05:
                trend = "improving"
            elif recent_avg < earlier_avg - 0.05:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "stable"

        return {
            "trend": trend,
            "recent_quality_avg": float(np.mean(quality_scores[-3:])),
            "overall_quality_avg": float(np.mean(quality_scores)),
            "quality_variance": float(np.var(quality_scores)),
            "best_quality": float(np.max(quality_scores)),
            "worst_quality": float(np.min(quality_scores))
        }

    def _generate_improvement_insights(self, quality_metrics: Dict[str, Any],
                                     trend_analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate insights for TTS improvement."""
        insights = []

        # Overall quality assessment
        avg_quality = quality_metrics.get("overall_quality_mean", 0.5)
        if avg_quality < self.quality_threshold:
            insights.append({
                "type": "quality_concern",
                "priority": "high",
                "message": f"Average TTS quality ({avg_quality:.3f}) below threshold ({self.quality_threshold})",
                "metrics": {"current_quality": avg_quality, "target_quality": self.quality_threshold}
            })

        # Speech clarity issues
        clarity_avg = quality_metrics.get("speech_clarity_mean", 0.5)
        if clarity_avg < 0.6:
            insights.append({
                "type": "clarity_issue",
                "priority": "medium",
                "message": f"Speech clarity ({clarity_avg:.3f}) could be improved",
                "metrics": {"current_clarity": clarity_avg}
            })

        # Naturalness concerns
        naturalness_avg = quality_metrics.get("naturalness_score_mean", 0.5)
        if naturalness_avg < 0.6:
            insights.append({
                "type": "naturalness_issue",
                "priority": "medium",
                "message": f"Speech naturalness ({naturalness_avg:.3f}) needs attention",
                "metrics": {"current_naturalness": naturalness_avg}
            })

        # Clipping detection
        clipping_rate = quality_metrics.get("clipping_rate", 0)
        if clipping_rate > 0.1:
            insights.append({
                "type": "clipping_issue",
                "priority": "high",
                "message": f"Audio clipping detected in {clipping_rate:.1%} of files",
                "metrics": {"clipping_rate": clipping_rate}
            })

        # Trend analysis insights
        trend = trend_analysis.get("trend", "stable")
        if trend == "declining":
            insights.append({
                "type": "quality_trend",
                "priority": "medium",
                "message": "TTS quality shows declining trend",
                "metrics": trend_analysis
            })
        elif trend == "improving":
            insights.append({
                "type": "quality_trend",
                "priority": "low",
                "message": "TTS quality shows improving trend",
                "metrics": trend_analysis
            })

        return insights

    def _generate_recommendations(self, quality_metrics: Dict[str, Any],
                                insights: List[Dict[str, Any]]) -> List[str]:
        """Generate actionable recommendations."""
        recommendations = []

        # Analyze insights for recommendations
        for insight in insights:
            insight_type = insight.get("type")

            if insight_type == "quality_concern":
                recommendations.append("Consider adjusting TTS model parameters or voice selection")

            elif insight_type == "clarity_issue":
                recommendations.append("Optimize speech synthesis for improved clarity in 1-4kHz range")

            elif insight_type == "naturalness_issue":
                recommendations.append("Review prosody and intonation parameters for more natural speech")

            elif insight_type == "clipping_issue":
                recommendations.append("Reduce TTS output gain to prevent audio clipping")

        # Frequency balance recommendations
        if "freq_balance_low_mean" in quality_metrics:
            low_energy = quality_metrics["freq_balance_low_mean"]
            high_energy = quality_metrics["freq_balance_high_mean"]

            if low_energy > 0.5:
                recommendations.append("Reduce low-frequency emphasis for clearer speech")
            elif high_energy < 0.2:
                recommendations.append("Enhance high-frequency content for better intelligibility")

        # Remove duplicates and limit recommendations
        recommendations = list(set(recommendations))
        return recommendations[:5]  # Limit to top 5 recommendations

    def _get_adaptive_threshold(self, parameter_name: str, default_value: float) -> float:
        """
        Get adaptive threshold based on historical data or environment.
        Replaces hardcoded values with measured/learned parameters.
        """
        try:
            # First try environment variable with parameter-specific name
            env_var = f"KLR_TTS_{parameter_name.upper()}_THRESHOLD"
            env_value = os.getenv(env_var)
            if env_value:
                self._parameter_source = f"environment_{env_var}"
                return float(env_value)

            # Try to derive from historical analysis if available
            historical_value = self._derive_threshold_from_history(parameter_name)
            if historical_value is not None:
                self._parameter_source = "historical_analysis"
                return historical_value

            # Fallback to default but track this as less reliable
            self._parameter_source = f"default_fallback"
            print(f"[tts_analysis] WARNING: Using default value {default_value} for {parameter_name} threshold")
            print(f"[tts_analysis] Consider setting {env_var} for more accurate thresholds")
            return default_value

        except Exception as e:
            print(f"[tts_analysis] Error getting adaptive threshold for {parameter_name}: {e}")
            self._parameter_source = "error_fallback"
            return default_value

    def _derive_threshold_from_history(self, parameter_name: str) -> Optional[float]:
        """Derive threshold from historical TTS analysis data."""
        try:
            # Try to read previous analysis results from memory or logs
            # This would analyze past quality scores to set appropriate thresholds

            # For now, return None to indicate no historical data
            # This could be enhanced to actually read historical analysis results
            # and derive adaptive thresholds based on system performance

            return None

        except Exception as e:
            print(f"[tts_analysis] Error deriving historical threshold: {e}")
            return None