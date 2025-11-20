"""
TTS SPICA Regression Tests

Quick regression tests you'll actually feel:
1. Determinism under low temp: same (variant, seed) ⇒ high consistency
2. Exploration under high temp: diversity bonus > 0 with param jitter
"""
import sys
from pathlib import Path
import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.phase.domains.spica_tts import TTSEvaluator, TTSVariant, _sanitize_variant


def test_low_temp_consistency():
    """Low temperature should produce consistent outputs."""
    print("TEST: Low-temp consistency")

    ev = TTSEvaluator()
    v = TTSVariant(backend="piper", voice="test_voice", speed=1.0, pitch=0.0,
                   prosody=0.4, seed=42, anneal_temp=0.1)

    sr = 22050
    t = np.linspace(0, 1, sr)
    audio_f32 = np.sin(2 * np.pi * 440 * t) * 0.5
    audio_i16 = (audio_f32 * 32767).astype(np.int16)
    audio_bytes = audio_i16.tobytes()

    r1 = ev.evaluate("Consistency check.", v, audio_bytes,
                     latency_ms=500.0, cpu_pct=25.0, mem_mb=512.0, repeats=2)
    r2 = ev.evaluate("Consistency check.", v, audio_bytes,
                     latency_ms=500.0, cpu_pct=25.0, mem_mb=512.0, repeats=2)

    consistency = r2["raw_scores"]["consistency"]
    print(f"  Consistency: {consistency:.3f} (expect > 0.5)")
    assert consistency > 0.5, f"Low-temp consistency too low: {consistency:.3f}"
    print("  ✓ PASS")


def test_high_temp_diversity_bonus():
    """High temperature should enable exploration."""
    print("\nTEST: High-temp diversity bonus")

    ev = TTSEvaluator()
    v = TTSVariant(backend="piper", voice="test_voice", speed=1.0, pitch=2.0,
                   prosody=0.8, seed=42, anneal_temp=0.9)

    sr = 22050
    for freq in [440, 450, 460]:
        t = np.linspace(0, 1, sr)
        audio_f32 = np.sin(2 * np.pi * freq * t) * 0.5
        audio_i16 = (audio_f32 * 32767).astype(np.int16)
        audio_bytes = audio_i16.tobytes()
        r = ev.evaluate("Diversity check.", v, audio_bytes,
                        latency_ms=500.0, cpu_pct=25.0, mem_mb=512.0, repeats=2)

    diversity_bonus = r["components"]["diversity_bonus"]
    print(f"  Diversity bonus: {diversity_bonus:.4f} (expect >= 0.0)")
    assert diversity_bonus >= 0.0, f"Diversity bonus negative: {diversity_bonus:.4f}"
    print("  ✓ PASS")


def test_safety_clamps():
    """Safety clamps should prevent out-of-range parameters."""
    print("\nTEST: Safety clamps")

    v = TTSVariant(backend="piper", voice="test", speed=10.0, pitch=-20.0,
                   prosody=5.0, anneal_temp=2.0)
    v_safe = _sanitize_variant(v)

    print(f"  Original: speed={v.speed}, pitch={v.pitch}, prosody={v.prosody}, temp={v.anneal_temp}")
    print(f"  Clamped:  speed={v_safe.speed}, pitch={v_safe.pitch}, prosody={v_safe.prosody}, temp={v_safe.anneal_temp}")

    assert 0.6 <= v_safe.speed <= 1.5, f"Speed not clamped: {v_safe.speed}"
    assert -6.0 <= v_safe.pitch <= 6.0, f"Pitch not clamped: {v_safe.pitch}"
    assert 0.0 <= v_safe.prosody <= 1.5, f"Prosody not clamped: {v_safe.prosody}"
    assert 0.0 <= v_safe.anneal_temp <= 1.0, f"Temp not clamped: {v_safe.anneal_temp}"
    print("  ✓ PASS")


def test_annealed_latency_targets():
    """Latency targets should tighten over epochs."""
    print("\nTEST: Annealed latency targets")

    from src.phase.domains.spica_tts import _annealed_latency_targets

    T_first_0, T_total_0 = _annealed_latency_targets(epoch=0)
    T_first_20, T_total_20 = _annealed_latency_targets(epoch=20)
    T_first_40, T_total_40 = _annealed_latency_targets(epoch=40)

    print(f"  Epoch 0:  first={T_first_0:.1f}ms, total={T_total_0:.1f}ms")
    print(f"  Epoch 20: first={T_first_20:.1f}ms, total={T_total_20:.1f}ms")
    print(f"  Epoch 40: first={T_first_40:.1f}ms, total={T_total_40:.1f}ms")

    assert T_first_0 > T_first_20 > T_first_40, "First-token targets not tightening"
    assert T_total_0 > T_total_20 > T_total_40, "Total targets not tightening"
    assert T_first_40 >= 90.0, f"First-token below floor: {T_first_40}"
    assert T_total_40 >= 500.0, f"Total latency below floor: {T_total_40}"
    print("  ✓ PASS")


if __name__ == "__main__":
    print("=" * 60)
    print("SPICA TTS Regression Tests")
    print("=" * 60)

    try:
        test_low_temp_consistency()
        test_high_temp_diversity_bonus()
        test_safety_clamps()
        test_annealed_latency_targets()

        print("\n" + "=" * 60)
        print("✓ All regression tests passed")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
